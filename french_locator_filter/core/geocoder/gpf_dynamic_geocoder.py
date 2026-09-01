# standard library
from typing import Dict, Optional

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
from french_locator_filter.toolbelt.geocodage_capabilities import (
    get_index_fields,
    load_capabilities,
)

# some field names documented in the GetCapabilities do not match the actual
# response property name for a given index (known Géoplateforme API quirk)
_INDEX_FIELD_JSON_KEY_OVERRIDES = {
    "poi": {"toponyme": "toponym"},
}


class GpfDynamicGeocoder(GpfRestApiGeocoder):
    """Geocoder for the Géoplateforme API, whose active index(es) (address,
    poi, parcel, ...) are configurable in the plugin settings instead of
    being hardcoded, driven by the service's GetCapabilities schema
    (see toolbelt/geocodage_capabilities.py)."""

    def __init__(self):
        super().__init__()
        self._capabilities = load_capabilities()

    @property
    def active_indexes(self) -> list:
        """Currently active indexes, from plugin settings

        :return: list of active index ids
        :rtype: list
        """
        return self.plg_settings.request_indexes_list

    @property
    def _attributes(self) -> Dict[str, QMetaType.Type]:
        """Get attributes to read from REST API properties: union of the fields
        of every currently active index. All typed as QString: the GetCapabilities
        field types are not reliable enough for finer typing (e.g. numeric fields
        are often declared as "string").

        Returns:
            Dict[str, QMetaType.Type]: dict of attribute with expected data type
        """
        attributes = {}
        for index_id in self.active_indexes:
            for field in get_index_fields(self._capabilities, index_id):
                name = field.get("name")
                if name:
                    attributes[name] = QMetaType.Type.QString
        # synthetic column, always present: which index the result came from.
        # Unlike "type" (only meaningful for the address index: housenumber/
        # street/...), this is populated for every index (address/poi/parcel)
        attributes["result_index"] = QMetaType.Type.QString
        return attributes

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
        indexes = ",".join(self.active_indexes)
        # returntruegeometry=true: needed for viewport_from_truegeometry() below
        # to have anything to read (parcel/poi indexes), at no extra request cost
        return (
            f"{self.plg_settings.request_url_query}"
            f"&index={indexes}&returntruegeometry=true"
        )

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
        if not geometry:
            return None

        active_indexes = self.active_indexes
        indexes = ",".join(active_indexes)
        # without an explicit limit, the API defaults to 10 results within its
        # default search radius, which floods the interactive reverse geocoding
        # dock with unrelated nearby candidates. Request one result per active
        # index instead (at least 1), so e.g. a single active "address" index
        # returns only the closest address.
        limit = f"&limit={max(1, len(active_indexes))}"
        index_and_geometry = f"&index={indexes}&returntruegeometry=true"
        center = geometry.centroid().asPoint()
        if geometry.type() == Qgis.GeometryType.Point:
            point = geometry.asPoint()
            return f"&lon={point.x()}&lat={point.y()}{index_and_geometry}{limit}"
        elif geometry.type() == Qgis.GeometryType.Polygon:
            return (
                f"searchgeom={geometry.asJson()}&lon={center.x()}"
                f"&lat={center.y()}{index_and_geometry}{limit}"
            )
        return f"&lon={center.x()}&lat={center.y()}{index_and_geometry}{limit}"

    def maximum_result_for_inverse_geocoding(self) -> int:
        """Maximum result for an inverse geocoding

        :return: maximum result
        :rtype: int
        """
        return 20

    def _label_from_properties(self, result_type: Optional[str], properties: dict) -> str:
        """Build a display label from a result's properties, depending on which
        index produced it (identified by the "_type" property).

        :param result_type: index id the result belongs to ("_type" property)
        :type result_type: Optional[str]
        :param properties: response properties
        :type properties: dict
        :return: display label
        :rtype: str
        """
        if result_type == "address":
            return properties.get("label", "")
        if result_type == "parcel":
            return (
                f"{properties.get('number')} {properties.get('section')} - "
                f"{properties.get('city')} "
                f"({properties.get('departmentcode')}{properties.get('municipalitycode')})"
            )
        if result_type == "poi":
            toponym = properties.get("toponym")
            if toponym:
                return toponym
            category = properties.get("category")
            if isinstance(category, list):
                return ", ".join(str(c) for c in category)
            return category or ""
        return properties.get("label") or result_type or ""

    def _result_from_json(self, response: dict) -> QgsGeocoderResult:
        """Create a QgsGeocoderResult from json content

        Args:
            response (dict): json response content

        Returns:
            QgsGeocoderResult: geocoder result
        """
        x = response["geometry"]["coordinates"][0]
        y = response["geometry"]["coordinates"][1]

        properties = response.get("properties", {})
        result_type = properties.get("_type")

        geom = QgsGeometry.fromPointXY(QgsPointXY(x, y))
        crs = QgsCoordinateReferenceSystem("EPSG:4326")
        res = QgsGeocoderResult(
            self._label_from_properties(result_type, properties),
            geom,
            crs,
        )

        overrides = _INDEX_FIELD_JSON_KEY_OVERRIDES.get(result_type, {})
        attributes = {}
        for attribute in self._attributes:
            if attribute == "result_index":
                attributes[attribute] = result_type
                continue
            json_key = overrides.get(attribute, attribute)
            value = properties.get(json_key)
            if isinstance(value, list):
                value = ", ".join(str(v) for v in value)
            attributes[attribute] = value

        viewport = self.viewport_from_truegeometry(properties, crs)
        if viewport is None:
            viewport = self.create_rectangle_around_point(crs, QgsPointXY(x, y), 2000, 2000)
        res.setViewport(viewport)

        res.setGroup(result_type)
        res.setAdditionalAttributes(attributes)
        return res
