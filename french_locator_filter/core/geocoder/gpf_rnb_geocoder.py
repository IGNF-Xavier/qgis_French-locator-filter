# standard library
import json
import time
from typing import Dict, List, Optional

# PyQGIS
from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsFeature,
    QgsFeedback,
    QgsGeocoderContext,
    QgsGeocoderResult,
    QgsGeometry,
    QgsJsonUtils,
    QgsPointXY,
)
from qgis.PyQt.QtCore import QDateTime, QMetaType

# project
from french_locator_filter.core.geocoder.addok_ban_fr_geocoder import FrenchBanGeocoder
from french_locator_filter.core.geocoder.rest_api_geocoder import RestAPIGeocoder
from french_locator_filter.toolbelt.network_manager import NetworkRequestsManager


class GpfRnbGeocoder(RestAPIGeocoder):
    """Geocoder for the Référentiel National du Bâti (RNB) API.

    Unlike the other geocoders, RNB offers no free-text search nor a
    point+radius search, so this geocoder composes two independent HTTP
    APIs instead of relying on the single-call template implemented by
    RestAPIGeocoder.geocodeString/geocodeFeature:

    - direct search: resolve the input string to an address via the
      Géoplateforme address index, then query RNB buildings for that
      address' BAN key (``cle_interop_ban``).
    - reverse search: query RNB buildings in a small bounding box around
      the clicked point, and pick the building containing the point (or
      the closest one). RNB already embeds address information for each
      building, which is used directly to enrich the reverse result.
    """

    _last_request_timestamp: int = 0

    # bounding box half-size (in meters) used around a point for reverse search
    REVERSE_BBOX_WIDTH_METERS = 40

    def __init__(self):
        super().__init__()
        self.max_request_per_second = 10
        self._address_geocoder = FrenchBanGeocoder()
        # real building footprints (RNB "shape") from the last search, keyed
        # by rnb_id: kept as an opt-in cache rather than the result's own
        # geometry, since QgsBatchGeocodeAlgorithm always creates a
        # Point-typed output sink regardless of a geocoder's declared
        # wkbType() (verified live) and silently drops any non-Point result -
        # used by geometry_for_result() to load the real shape on demand
        self._geometry_cache: Dict[str, QgsGeometry] = {}

    def geometry_for_result(self, result: QgsGeocoderResult) -> Optional[QgsGeometry]:
        """Get the real building footprint behind a result, if it had one
        recorded (see __init__)

        :param result: a result previously returned by this geocoder
        :type result: QgsGeocoderResult
        :return: real polygon geometry, None if not available
        :rtype: Optional[QgsGeometry]
        """
        rnb_id = result.additionalAttributes().get("rnb_id")
        return self._geometry_cache.get(rnb_id) if rnb_id else None

    def set_last_request_timestamp(self, timestamp: int) -> None:
        """Define timestamp for last request

        :param timestamp: request timestamp
        :type timestamp: int
        """
        GpfRnbGeocoder._last_request_timestamp = timestamp

    def last_request_timestamp(self) -> int:
        """Get last request timestamp

        :return: last request timestamp
        :rtype: int
        """
        return GpfRnbGeocoder._last_request_timestamp

    @property
    def _attributes(self) -> Dict[str, QMetaType.Type]:
        """Get attributes to read from REST API properties.

        Returns:
            Dict[str, QMetaType.Type]: dict of attribute with expected data type
        """
        return {
            "rnb_id": QMetaType.Type.QString,
            "status": QMetaType.Type.QString,
            "ban_id": QMetaType.Type.QString,
            "street_number": QMetaType.Type.QString,
            "street": QMetaType.Type.QString,
            "city_name": QMetaType.Type.QString,
            "city_zipcode": QMetaType.Type.QString,
            "city_insee_code": QMetaType.Type.QString,
            "address_label": QMetaType.Type.QString,
        }

    def maximum_result_for_inverse_geocoding(self) -> int:
        """Maximum result for an inverse geocoding

        :return: maximum result
        :rtype: int
        """
        return 10

    def _wait_for_rate_limit(self, feedback: Optional[QgsFeedback]) -> bool:
        """Wait until the rate limit allows a new request

        :param feedback: feedback, used to detect cancellation
        :type feedback: Optional[QgsFeedback]
        :return: True if canceled while waiting, False otherwise
        :rtype: bool
        """
        while (
            QDateTime.currentMSecsSinceEpoch() - self.last_request_timestamp()
            < 1000 / self.max_request_per_second
        ):
            time.sleep(0.05)
            if feedback and feedback.isCanceled():
                return True
        return False

    def _fetch_rnb_buildings(self, query: str) -> List[dict]:
        """Query the RNB buildings endpoint and return the raw list of buildings

        :param query: url query string (without leading '?')
        :type query: str
        :return: list of buildings (json dict) matching the query
        :rtype: List[dict]
        """
        try:
            qntwk = NetworkRequestsManager()
            qurl = qntwk.build_url(
                request_url=f"{self.plg_settings.rnb_url}buildings/",
                request_url_query=query,
            )
            response_content = qntwk.get_url(url=qurl)
            data = json.loads(str(response_content, "UTF8"))
            return data.get("results", [])
        except Exception as err:
            self.log(
                message=self.tr(
                    "Erreur lors de la demande au RNB : {}".format(err)
                ),
                log_level=1,
            )
            return []

    def _fetch_rnb_buildings_on_plot(self, idu: str) -> List[dict]:
        """Query the RNB buildings-on-plot endpoint and return the raw list of
        buildings intersecting a given cadastral parcel.

        :param idu: cadastral parcel identifier (e.g. "75104000AV0117")
        :type idu: str
        :return: list of buildings (json dict) on the parcel
        :rtype: List[dict]
        """
        try:
            qntwk = NetworkRequestsManager()
            qurl = qntwk.build_url(
                request_url=f"{self.plg_settings.rnb_url}buildings/plot/{idu}/",
                request_url_query="format=json",
            )
            response_content = qntwk.get_url(url=qurl)
            data = json.loads(str(response_content, "UTF8"))
            return data.get("results", [])
        except Exception as err:
            self.log(
                message=self.tr(
                    "Erreur lors de la demande au RNB (parcelle {}) : {}".format(
                        idu, err
                    )
                ),
                log_level=1,
            )
            return []

    def _fetch_rnb_building_detail(self, rnb_id: str) -> Optional[dict]:
        """Query the RNB single-building endpoint, which already embeds the
        building's real shape (unlike the lightweight point-only attributes
        used elsewhere) - used to visualize a specific building's real
        footprint without redoing a bbox/plot search.

        :param rnb_id: RNB building identifier
        :type rnb_id: str
        :return: building json dict, None if not found
        :rtype: Optional[dict]
        """
        try:
            qntwk = NetworkRequestsManager()
            qurl = qntwk.build_url(
                request_url=f"{self.plg_settings.rnb_url}buildings/{rnb_id}/",
                request_url_query="format=json",
            )
            response_content = qntwk.get_url(url=qurl)
            return json.loads(str(response_content, "UTF8"))
        except Exception as err:
            self.log(
                message=self.tr(
                    "Erreur lors de la demande au RNB (bâtiment {}) : {}".format(
                        rnb_id, err
                    )
                ),
                log_level=1,
            )
            return None

    def geocodeString(
        self,
        string: str,
        context: QgsGeocoderContext,
        feedback: Optional[QgsFeedback] = None,
    ) -> List[QgsGeocoderResult]:
        """Geocode a string by first resolving it to an address (Géoplateforme
        address index), then looking up the building(s) at that address in RNB.

        Args:
            string (str): search string
            context (QgsGeocoderContext): geocoding context
            feedback (QgsFeedback | None, optional): feedback for geocoding. Defaults to None

        Returns:
            List[QgsGeocoderResult]: list of geocoding results
        """
        address_results = self._address_geocoder.geocodeString(string, context, feedback)
        if not address_results:
            return []

        # keep only the best-scored address match to stay responsive in the locator bar
        best_address = address_results[0]
        ban_id = best_address.additionalAttributes().get("id")
        if not ban_id:
            return []

        if self._wait_for_rate_limit(feedback):
            return []
        try:
            buildings = self._fetch_rnb_buildings(
                f"cle_interop_ban={ban_id}&format=json"
            )
            return [self._result_from_building(building) for building in buildings]
        finally:
            self.set_last_request_timestamp(QDateTime.currentMSecsSinceEpoch())

    def geocodeFeature(
        self,
        feature: QgsFeature,
        context: QgsGeocoderContext,
        feedback: Optional[QgsFeedback] = None,
    ) -> List[QgsGeocoderResult]:
        """Geocode a feature by querying RNB buildings in a small bounding box
        around the point, and ordering candidates by containment then distance.

        :param feature: input feature, geometry expected in EPSG:4326
        :type feature: QgsFeature
        :param context: geocoder context
        :type context: QgsGeocoderContext
        :param feedback: feedback, defaults to None
        :type feedback: Optional[QgsFeedback]
        :return: list of result for feature
        :rtype: List[QgsGeocoderResult]
        """
        geometry = feature.geometry()
        if not geometry:
            return []

        point = geometry.centroid().asPoint()
        if geometry.type() == Qgis.GeometryType.Point:
            point = geometry.asPoint()

        if self._wait_for_rate_limit(feedback):
            return []
        try:
            crs = QgsCoordinateReferenceSystem("EPSG:4326")
            rect = self.create_rectangle_around_point(
                crs, point, self.REVERSE_BBOX_WIDTH_METERS, self.REVERSE_BBOX_WIDTH_METERS
            )
            bbox = (
                f"{rect.xMinimum()},{rect.yMinimum()},"
                f"{rect.xMaximum()},{rect.yMaximum()}"
            )
            buildings = self._fetch_rnb_buildings(f"bbox={bbox}&format=json")
            ordered_buildings = self._order_buildings_by_relevance(buildings, point)
            return [
                self._result_from_building(building) for building in ordered_buildings
            ]
        finally:
            self.set_last_request_timestamp(QDateTime.currentMSecsSinceEpoch())

    def _building_geometry(self, building: dict) -> Optional[QgsGeometry]:
        """Build a QgsGeometry from a building's GeoJSON shape

        :param building: building json dict
        :type building: dict
        :return: geometry, None if not available/invalid
        :rtype: Optional[QgsGeometry]
        """
        shape = building.get("shape")
        if not shape:
            return None
        try:
            geojson_feature = json.dumps(
                {"type": "Feature", "geometry": shape, "properties": {}}
            )
            features = QgsJsonUtils.stringToFeatureList(geojson_feature)
            if features and features[0].hasGeometry():
                return features[0].geometry()
        except Exception as err:
            self.log(
                message=self.tr(
                    "Impossible de lire la géométrie du bâtiment : {}".format(err)
                ),
                log_level=Qgis.MessageLevel.NoLevel,
            )
        return None

    def _order_buildings_by_relevance(
        self, buildings: List[dict], point: QgsPointXY
    ) -> List[dict]:
        """Order candidate buildings: those whose shape contains the point first,
        then all others sorted by distance to the point.

        :param buildings: candidate buildings
        :type buildings: List[dict]
        :param point: reference point (EPSG:4326)
        :type point: QgsPointXY
        :return: ordered buildings
        :rtype: List[dict]
        """
        point_geom = QgsGeometry.fromPointXY(point)

        def sort_key(building: dict):
            shape_geom = self._building_geometry(building)
            contains = bool(shape_geom and shape_geom.contains(point_geom))
            coordinates = building.get("point", {}).get("coordinates")
            if coordinates:
                distance = point_geom.distance(
                    QgsGeometry.fromPointXY(QgsPointXY(coordinates[0], coordinates[1]))
                )
            else:
                distance = float("inf")
            return (0 if contains else 1, distance)

        return sorted(buildings, key=sort_key)

    def _result_from_building(self, building: dict) -> QgsGeocoderResult:
        """Create a QgsGeocoderResult from a RNB building json dict, enriching it
        with the address information already embedded in the RNB response.

        :param building: building json dict
        :type building: dict
        :return: geocoder result
        :rtype: QgsGeocoderResult
        """
        coordinates = building.get("point", {}).get("coordinates", [0, 0])
        x, y = coordinates[0], coordinates[1]

        attributes = {attribute: None for attribute in self._attributes}
        attributes["rnb_id"] = building.get("rnb_id")
        attributes["status"] = building.get("status")

        address_label = None
        addresses = building.get("addresses") or []
        if addresses:
            address = addresses[0]
            attributes["ban_id"] = address.get("ban_id") or address.get("id")
            attributes["street_number"] = address.get("street_number")
            attributes["street"] = address.get("street")
            attributes["city_name"] = address.get("city_name")
            attributes["city_zipcode"] = address.get("city_zipcode")
            attributes["city_insee_code"] = address.get("city_insee_code")

            street_part = " ".join(
                part
                for part in [address.get("street_number"), address.get("street")]
                if part
            )
            city_part = " ".join(
                part
                for part in [address.get("city_zipcode"), address.get("city_name")]
                if part
            )
            address_label = ", ".join(part for part in [street_part, city_part] if part)
            attributes["address_label"] = address_label

        label = f"Bâtiment {building.get('rnb_id')}"
        if address_label:
            label += f" - {address_label}"

        geom = QgsGeometry.fromPointXY(QgsPointXY(x, y))
        crs = QgsCoordinateReferenceSystem("EPSG:4326")
        res = QgsGeocoderResult(label, geom, crs)

        # the real building footprint, when RNB returned one (not all buildings
        # have a recorded shape): used for the viewport (a tight fit on the
        # actual shape rather than a generic square) and cached for on-demand
        # loading as its own layer - not as this result's own geometry, since
        # QgsBatchGeocodeAlgorithm always creates a Point-typed output sink
        # regardless of wkbType() and silently drops any non-Point result
        # (verified live)
        shape_geom = self._building_geometry(building)
        if shape_geom:
            shape_geom.convertToMultiType()
            rnb_id = attributes.get("rnb_id")
            if rnb_id:
                self._geometry_cache[rnb_id] = shape_geom
            res.setViewport(shape_geom.boundingBox())
        else:
            res.setViewport(
                self.create_rectangle_around_point(crs, QgsPointXY(x, y), 50, 50)
            )

        res.setGroup("building")
        res.setAdditionalAttributes(attributes)
        return res
