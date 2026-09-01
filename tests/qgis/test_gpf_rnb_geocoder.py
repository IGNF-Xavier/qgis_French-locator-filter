#! python3  # noqa E265

"""
Usage from the repo root folder:

.. code-block:: bash

    # for whole tests
    python -m unittest tests.qgis.test_gpf_rnb_geocoder
"""

# standard library
import unittest

# project
from french_locator_filter.core.geocoder.gpf_rnb_geocoder import GpfRnbGeocoder

# ############################################################################
# ########## Classes #############
# ################################

BUILDING_WITH_SHAPE = {
    "rnb_id": "RSJ5HEMCP3D3",
    "status": "constructed",
    "point": {"type": "Point", "coordinates": [2.354352867209375, 48.85210190224262]},
    "shape": {
        "type": "MultiPolygon",
        "coordinates": [
            [
                [
                    [2.354, 48.852],
                    [2.355, 48.852],
                    [2.355, 48.853],
                    [2.354, 48.853],
                    [2.354, 48.852],
                ]
            ]
        ],
    },
    "addresses": [],
}

BUILDING_WITHOUT_SHAPE = {
    "rnb_id": "S65V7NJE3NKS",
    "status": "constructed",
    "point": {"type": "Point", "coordinates": [2.354010816155664, 48.85229519541175]},
    "shape": None,
    "addresses": [],
}


class TestGpfRnbGeocoder(unittest.TestCase):
    def test_result_geometry_stays_point(self):
        """QgsBatchGeocodeAlgorithm always creates a Point-typed output sink
        regardless of a geocoder's declared wkbType() and silently drops any
        non-Point result (verified live against a real QGIS instance) - the
        result's own geometry must stay a point even when a real building
        shape is available."""
        geocoder = GpfRnbGeocoder()

        result = geocoder._result_from_building(BUILDING_WITH_SHAPE)

        point = result.geometry().asPoint()
        self.assertAlmostEqual(point.x(), 2.354352867209375)
        self.assertAlmostEqual(point.y(), 48.85210190224262)

    def test_geometry_for_result_returns_cached_shape(self):
        geocoder = GpfRnbGeocoder()

        result = geocoder._result_from_building(BUILDING_WITH_SHAPE)
        geometry = geocoder.geometry_for_result(result)

        self.assertIsNotNone(geometry)
        self.assertTrue(geometry.isMultipart())
        bbox = geometry.boundingBox()
        self.assertAlmostEqual(bbox.xMinimum(), 2.354)
        self.assertAlmostEqual(bbox.xMaximum(), 2.355)

    def test_geometry_for_result_none_without_shape(self):
        geocoder = GpfRnbGeocoder()

        result = geocoder._result_from_building(BUILDING_WITHOUT_SHAPE)

        self.assertIsNone(geocoder.geometry_for_result(result))


# ############################################################################
# ####### Stand-alone run ########
# ################################
if __name__ == "__main__":
    unittest.main()
