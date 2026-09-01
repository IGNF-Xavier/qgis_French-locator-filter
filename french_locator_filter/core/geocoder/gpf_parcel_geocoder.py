# standard library
import json
from typing import Dict, List, Optional

# PyQGIS
from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsFeature,
    QgsGeocoderResult,
    QgsGeometry,
    QgsPointXY,
)
from qgis.PyQt.QtCore import QMetaType

# project
from french_locator_filter.core.geocoder.gpf_rest_api_geocoder import (
    GpfRestApiGeocoder,
)
from french_locator_filter.toolbelt.network_manager import NetworkRequestsManager


class GpfParcelGeocoder(GpfRestApiGeocoder):
    """Geocoder for the cadastral parcel index of the Géoplateforme API"""

    def __init__(self):
        super().__init__()
        # real parcel polygons (truegeometry) from the last search, keyed by
        # the parcel's "id": kept as an opt-in cache rather than the result's
        # own geometry, since QgsBatchGeocodeAlgorithm always creates a
        # Point-typed output sink regardless of a geocoder's declared
        # wkbType() (verified live) and silently drops any non-Point result -
        # used by geometry_for_result() to load the real shape on demand
        self._geometry_cache: Dict[str, QgsGeometry] = {}

    def geometry_for_result(self, result: QgsGeocoderResult) -> Optional[QgsGeometry]:
        """Get the real parcel polygon behind a result, if it was resolved
        during the last search (see __init__)

        :param result: a result previously returned by this geocoder
        :type result: QgsGeocoderResult
        :return: real polygon geometry, None if not available
        :rtype: Optional[QgsGeometry]
        """
        parcel_id = result.additionalAttributes().get("id")
        return self._geometry_cache.get(parcel_id) if parcel_id else None

    @property
    def _attributes(self) -> Dict[str, QMetaType.Type]:
        """Get attributes to read from REST API properties.

        Returns:
            Dict[str, QMetaType.Type]: dict of attribute with expected data type
        """
        return {
            "id": QMetaType.Type.QString,
            "departmentcode": QMetaType.Type.QString,
            "municipalitycode": QMetaType.Type.QString,
            "city": QMetaType.Type.QString,
            "oldmunicipalitycode": QMetaType.Type.QString,
            "districtcode": QMetaType.Type.QString,
            "section": QMetaType.Type.QString,
            "number": QMetaType.Type.QString,
            "sheet": QMetaType.Type.QString,
            "_score": QMetaType.Type.Double,
        }

    def request_url(self, reverse: bool = False) -> str:
        """Define request url

        :param reverse: True for reverse geocoding, False otherwise, defaults to False
        :type reverse: bool, optional
        :return: request url for geocoding
        :rtype: str
        """
        url_service = self.plg_settings.gpf_url
        if reverse:
            return f"{url_service}reverse"
        return f"{url_service}search"

    @property
    def request_url_query(self):
        """Define default request url query

        Returns:
            str: request url query
        """
        # returntruegeometry=true asks the API to include the parcel's real
        # polygon (as "truegeometry") in the response properties, at no extra
        # request cost - used as the result's own geometry, not just its viewport
        return f"{self.plg_settings.request_url_query}&index=parcel&returntruegeometry=true"

    def get_reverse_geocode_query(self, feature: QgsFeature) -> Optional[str]:
        """Get query for reverse geocode
        For point we use &lon&lat
        For polygon we use searchgeom associated with centroid
        For all other geometry type centroid is used as point

        :param feature: input feature
        :type feature: QgsFeature
        :return: reverse geocode query, None if feature geometry is None
        :rtype: Optional[str]
        """
        geometry = feature.geometry()
        if geometry:
            center = geometry.centroid().asPoint()
            # a point almost always falls within a single cadastral parcel: without
            # an explicit limit, the API defaults to 10 results within its default
            # search radius, which returns many unrelated nearby parcels
            limit = f"&limit={self.maximum_result_for_inverse_geocoding()}"
            index_and_geometry = "&index=parcel&returntruegeometry=true"
            if geometry.type() == Qgis.GeometryType.Point:
                point = geometry.asPoint()
                query = f"&lon={point.x()}&lat={point.y()}{index_and_geometry}{limit}"
            elif geometry.type() == Qgis.GeometryType.Polygon:
                query = (
                    f"searchgeom={geometry.asJson()}&lon={center.x()}"
                    f"&lat={center.y()}{index_and_geometry}{limit}"
                )
            else:
                query = f"&lon={center.x()}&lat={center.y()}{index_and_geometry}{limit}"
            return query
        return None

    def _result_from_json(self, response: dict) -> QgsGeocoderResult:
        """Create a QgsGeocoderResult from json content

        Args:
            response (dict): json response content

        Returns:
            QgsGeocoderResult: geocoder result
        """
        x = response["geometry"]["coordinates"][0]
        y = response["geometry"]["coordinates"][1]

        properties = response.get("properties")
        section = properties.get("section")
        number = properties.get("number")
        city = properties.get("city")
        departmentcode = properties.get("departmentcode")
        municipalitycode = properties.get("municipalitycode")

        label = f"{number} {section} - {city} ({departmentcode}{municipalitycode})"

        geom = QgsGeometry.fromPointXY(QgsPointXY(x, y))
        crs = QgsCoordinateReferenceSystem("EPSG:4326")
        res = QgsGeocoderResult(
            label,
            geom,
            crs,
        )
        attributes = {}
        for attribute, _ in self._attributes.items():
            attributes[attribute] = properties.get(attribute, None)

        # the real parcel polygon, when the API returned one (returntruegeometry=true):
        # used for the viewport (a tight fit on the actual shape rather than a
        # generic square) and cached for on-demand loading as its own layer -
        # not as this result's own geometry, since QgsBatchGeocodeAlgorithm
        # always creates a Point-typed output sink regardless of wkbType()
        # and silently drops any non-Point result (verified live)
        true_geom = self.geometry_from_geojson(properties.get("truegeometry"))
        if true_geom:
            true_geom.convertToMultiType()
            parcel_id = attributes.get("id")
            if parcel_id:
                self._geometry_cache[parcel_id] = true_geom

        viewport = true_geom.boundingBox() if true_geom else None
        if viewport is None:
            viewport = self.create_rectangle_around_point(crs, QgsPointXY(x, y), 200, 200)
        res.setViewport(viewport)

        res.setGroup("parcel")
        res.setAdditionalAttributes(attributes)
        return res

    def search_structured(
        self,
        departmentcode: str,
        municipalitycode: str,
        section: Optional[str] = None,
        number: Optional[str] = None,
        sheet: Optional[str] = None,
    ) -> List[QgsGeocoderResult]:
        """Search parcels using the structured search available for the parcel index
        (department, municipality, section, number, sheet) instead of a free-text query.

        :param departmentcode: department code
        :type departmentcode: str
        :param municipalitycode: municipality (INSEE) code
        :type municipalitycode: str
        :param section: cadastral section, defaults to None
        :type section: Optional[str], optional
        :param number: cadastral parcel number, defaults to None
        :type number: Optional[str], optional
        :param sheet: cadastral sheet, defaults to None
        :type sheet: Optional[str], optional
        :return: list of matching parcels
        :rtype: List[QgsGeocoderResult]
        """
        query = (
            "q=&index=parcel&returntruegeometry=true"
            f"&departmentcode={departmentcode}&municipalitycode={municipalitycode}"
        )
        if section:
            query += f"&section={section}"
        if number:
            # cadastral parcel numbers are zero-padded to 4 digits (e.g. "183" -> "0183")
            if number.isdigit():
                number = number.zfill(4)
            query += f"&number={number}"
        if sheet:
            query += f"&sheet={sheet}"

        try:
            qntwk = NetworkRequestsManager()
            qurl = qntwk.build_url(
                request_url=self.request_url(reverse=False),
                request_url_query=self.plg_settings.request_url_query,
                additional_query=f"&{query}",
            )
            response_content = qntwk.get_url(url=qurl)
            responses = json.loads(str(response_content, "UTF8"))
            return [
                self._result_from_json(response)
                for response in responses.get(self.result_container_name)
            ]
        except Exception as err:
            self.log(
                message=self.tr(
                    "Erreur lors de la recherche structurée de parcelle : {}".format(
                        err
                    )
                ),
                log_level=1,
            )
            return []
