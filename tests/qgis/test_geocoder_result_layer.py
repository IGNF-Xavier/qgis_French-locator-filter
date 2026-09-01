#! python3  # noqa E265

"""
Usage from the repo root folder:

.. code-block:: bash

    # for whole tests
    python -m unittest tests.qgis.test_geocoder_result_layer
"""

# standard library
import unittest
from typing import Dict, Optional

# PyQGIS
from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsField,
    QgsFields,
    QgsGeocoderResult,
    QgsGeometry,
    QgsPointXY,
)
from qgis.PyQt.QtCore import QMetaType

# project
from french_locator_filter.toolbelt.geocoder_result_layer import (
    results_to_memory_layer,
    results_to_real_geometry_layer,
)

# ############################################################################
# ########## Classes #############
# ################################

CRS = QgsCoordinateReferenceSystem("EPSG:4326")


class _StubGeocoder:
    """Minimal geocoder stub, like GpfParcelGeocoder/GpfRnbGeocoder: results
    stay Point-geometried (QgsBatchGeocodeAlgorithm always creates a
    Point-typed output sink and silently drops non-Point results, verified
    live), with the real polygon available separately via a cache read
    through geometry_for_result() - avoids depending on real HTTP logic just
    to test the layer-building helpers."""

    def __init__(self):
        self._geometry_cache: Dict[str, QgsGeometry] = {}

    def appendedFields(self) -> QgsFields:
        fields = QgsFields()
        fields.append(QgsField("some_id", QMetaType.Type.QString))
        return fields

    def geometry_for_result(self, result: QgsGeocoderResult) -> Optional[QgsGeometry]:
        some_id = result.additionalAttributes().get("some_id")
        return self._geometry_cache.get(some_id) if some_id else None


def _result_with_cached_polygon(geocoder: _StubGeocoder, some_id: str) -> QgsGeocoderResult:
    point_geometry = QgsGeometry.fromPointXY(QgsPointXY(2.3545, 48.8525))
    result = QgsGeocoderResult("label", point_geometry, CRS)
    result.setAdditionalAttributes({"some_id": some_id})
    geocoder._geometry_cache[some_id] = QgsGeometry.fromWkt(
        "POLYGON((2.354 48.852, 2.355 48.852, 2.355 48.853, 2.354 48.853, 2.354 48.852))"
    )
    return result


def _result_without_cached_polygon(some_id: str) -> QgsGeocoderResult:
    point_geometry = QgsGeometry.fromPointXY(QgsPointXY(2.3545, 48.8525))
    result = QgsGeocoderResult("label", point_geometry, CRS)
    result.setAdditionalAttributes({"some_id": some_id})
    return result


class TestGeocoderResultLayer(unittest.TestCase):
    def test_results_to_memory_layer_is_always_point(self):
        """Results stay Point-geometried (see _StubGeocoder docstring): the
        "Charger comme couche" layer must always be a point layer."""
        geocoder = _StubGeocoder()
        result = _result_without_cached_polygon("A")

        layer = results_to_memory_layer(geocoder, [result], "test layer")

        self.assertIsNotNone(layer)
        self.assertEqual(layer.featureCount(), 1)
        feature = next(layer.getFeatures())
        self.assertFalse(feature.geometry().isNull())
        self.assertEqual(feature.geometry().type(), Qgis.GeometryType.Point)

    def test_real_geometry_layer_uses_cached_polygon(self):
        geocoder = _StubGeocoder()
        result = _result_with_cached_polygon(geocoder, "A")

        layer = results_to_real_geometry_layer(geocoder, [result], "test layer")

        self.assertIsNotNone(layer)
        self.assertEqual(layer.featureCount(), 1)
        feature = next(layer.getFeatures())
        self.assertFalse(feature.geometry().isNull())
        self.assertEqual(feature["some_id"], "A")

    def test_real_geometry_layer_skips_results_without_cached_polygon(self):
        """A result with no cached real geometry (e.g. an RNB building with
        no recorded shape) must simply be left out, rather than added with a
        missing/fallback geometry or breaking the layer."""
        geocoder = _StubGeocoder()
        with_polygon = _result_with_cached_polygon(geocoder, "A")
        without_polygon = _result_without_cached_polygon("B")

        layer = results_to_real_geometry_layer(
            geocoder, [with_polygon, without_polygon], "test layer"
        )

        self.assertEqual(layer.featureCount(), 1)
        feature = next(layer.getFeatures())
        self.assertEqual(feature["some_id"], "A")

    def test_real_geometry_layer_none_when_nothing_cached(self):
        geocoder = _StubGeocoder()
        result = _result_without_cached_polygon("B")

        layer = results_to_real_geometry_layer(geocoder, [result], "test layer")

        self.assertIsNone(layer)


# ############################################################################
# ####### Stand-alone run ########
# ################################
if __name__ == "__main__":
    unittest.main()
