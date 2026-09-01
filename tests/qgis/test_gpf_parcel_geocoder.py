#! python3  # noqa E265

"""
Usage from the repo root folder:

.. code-block:: bash

    # for whole tests
    python -m unittest tests.qgis.test_gpf_parcel_geocoder
"""

# standard library
import unittest

# project
from french_locator_filter.core.geocoder.gpf_parcel_geocoder import GpfParcelGeocoder

# ############################################################################
# ########## Classes #############
# ################################

RESPONSE_WITH_TRUEGEOMETRY = {
    "type": "Feature",
    "geometry": {"type": "Point", "coordinates": [2.35461, 48.85234]},
    "properties": {
        "id": "75056104AV0133",
        "departmentcode": "75",
        "municipalitycode": "056",
        "city": "Paris",
        "section": "AV",
        "number": "133",
        "truegeometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [2.354, 48.852],
                    [2.355, 48.852],
                    [2.355, 48.853],
                    [2.354, 48.853],
                    [2.354, 48.852],
                ]
            ],
        },
    },
}

RESPONSE_WITHOUT_TRUEGEOMETRY = {
    "type": "Feature",
    "geometry": {"type": "Point", "coordinates": [2.35461, 48.85234]},
    "properties": {
        "id": "75056104AV0134",
        "departmentcode": "75",
        "municipalitycode": "056",
        "city": "Paris",
        "section": "AV",
        "number": "134",
    },
}


class TestGpfParcelGeocoder(unittest.TestCase):
    def test_result_geometry_stays_point(self):
        """QgsBatchGeocodeAlgorithm always creates a Point-typed output sink
        regardless of a geocoder's declared wkbType() and silently drops any
        non-Point result (verified live against a real QGIS instance) - the
        result's own geometry must stay a point even when a real polygon
        (truegeometry) is available."""
        geocoder = GpfParcelGeocoder()

        result = geocoder._result_from_json(RESPONSE_WITH_TRUEGEOMETRY)

        point = result.geometry().asPoint()
        self.assertAlmostEqual(point.x(), 2.35461)
        self.assertAlmostEqual(point.y(), 48.85234)

    def test_geometry_for_result_returns_cached_polygon(self):
        geocoder = GpfParcelGeocoder()

        result = geocoder._result_from_json(RESPONSE_WITH_TRUEGEOMETRY)
        geometry = geocoder.geometry_for_result(result)

        self.assertIsNotNone(geometry)
        self.assertTrue(geometry.isMultipart())
        bbox = geometry.boundingBox()
        self.assertAlmostEqual(bbox.xMinimum(), 2.354)
        self.assertAlmostEqual(bbox.xMaximum(), 2.355)
        self.assertAlmostEqual(bbox.yMinimum(), 48.852)
        self.assertAlmostEqual(bbox.yMaximum(), 48.853)

    def test_geometry_for_result_none_without_truegeometry(self):
        geocoder = GpfParcelGeocoder()

        result = geocoder._result_from_json(RESPONSE_WITHOUT_TRUEGEOMETRY)

        self.assertIsNone(geocoder.geometry_for_result(result))

    def test_viewport_uses_truegeometry_bbox(self):
        geocoder = GpfParcelGeocoder()

        result = geocoder._result_from_json(RESPONSE_WITH_TRUEGEOMETRY)

        viewport = result.viewport()
        self.assertAlmostEqual(viewport.xMinimum(), 2.354)
        self.assertAlmostEqual(viewport.xMaximum(), 2.355)


# ############################################################################
# ####### Stand-alone run ########
# ################################
if __name__ == "__main__":
    unittest.main()
