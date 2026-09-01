import copy

import pytest
import pytest_httpserver
from qgis.core import (
    QgsApplication,
    QgsFeature,
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingFeedback,
    QgsVectorLayer,
)

from french_locator_filter.processing.gpf_parcel_geocoder_batch_processing import (
    GpfParcelGeocoderBatchProcessing,
)
from french_locator_filter.processing.provider import FrenchLocatorProcessingProvider

TRUEGEOMETRY = {
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
}

GPF_SRV_MOCK_RESPOND = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [2.35461, 48.85234]},
            "properties": {
                "id": "75056104AV0133",
                "departmentcode": "75",
                "municipalitycode": "056",
                "city": "Paris",
                "oldmunicipalitycode": "000",
                "districtcode": "104",
                "section": "AV",
                "number": "133",
                "sheet": "1",
                "_score": 1,
                "_type": "parcel",
                "truegeometry": TRUEGEOMETRY,
            },
        }
    ],
    "query": "75056104AV0133",
}

GEOCODING_RESULT_ATTRIBUTES = {
    "id": "75056104AV0133",
    "departmentcode": "75",
    "municipalitycode": "056",
    "city": "Paris",
    "oldmunicipalitycode": "000",
    "districtcode": "104",
    "section": "AV",
    "number": "133",
    "sheet": "1",
    "_score": 1,
}


@pytest.fixture()
def alg() -> QgsProcessingAlgorithm:
    """Retrieve algorithm to be tested from processing registry

    :return: algorithm to be tested
    :rtype: QgsProcessingAlgorithm
    """
    algo_str = (
        f"{FrenchLocatorProcessingProvider().id()}:"
        f"{GpfParcelGeocoderBatchProcessing().name()}"
    )
    alg = QgsApplication.processingRegistry().algorithmById(algo_str)
    assert alg is not None
    return alg


def test_geocode_with_input(
    data_geopf_srv: pytest_httpserver.HTTPServer, alg: QgsProcessingAlgorithm
):
    """Test parcel geocoding with a feature

    :param alg: geocoding algorithm
    :type alg: QgsProcessingAlgorithm
    """

    # Respond with mock
    data_geopf_srv.expect_oneshot_request("/search", method="GET").respond_with_json(
        GPF_SRV_MOCK_RESPOND
    )

    input_layer = QgsVectorLayer(
        "NoGeometry?field=parcelle:string",
        "test",
        "memory",
    )

    pr = input_layer.dataProvider()
    feat = QgsFeature()
    feat.setAttributes(["75056104AV0133"])
    pr.addFeatures([feat])

    params = {
        "INPUT": input_layer,
        "FIELD": "parcelle",
        "OUTPUT": "TEMPORARY_OUTPUT",
    }

    context = QgsProcessingContext()
    feedback = QgsProcessingFeedback()

    result, success = alg.run(params, context, feedback, catchExceptions=False)
    assert success

    output_layer = context.getMapLayer(result["OUTPUT"])
    assert output_layer.isValid()
    assert output_layer.featureCount() == input_layer.featureCount()
    assert output_layer.crs().authid() == "EPSG:4326"

    features = [f for f in output_layer.getFeatures()]
    geocoded_point = features[0].geometry().asPoint()

    assert geocoded_point.x() == pytest.approx(2.35461)
    assert geocoded_point.y() == pytest.approx(48.85234)

    expected_attributes = [GEOCODING_RESULT_ATTRIBUTES]
    for i, f in enumerate(output_layer.getFeatures()):
        for key, value in expected_attributes[i].items():
            assert f.attribute(key) == value


def test_geocode_keep_attributes(
    data_geopf_srv: pytest_httpserver.HTTPServer, alg: QgsProcessingAlgorithm
):
    """Test that input attributes are kept

    :param alg: geocoding algorithm
    :type alg: QgsProcessingAlgorithm
    """

    # Respond with mock
    data_geopf_srv.expect_oneshot_request("/search", method="GET").respond_with_json(
        GPF_SRV_MOCK_RESPOND
    )

    input_layer = QgsVectorLayer(
        "NoGeometry?field=parcelle:string&field=other_field:string",
        "test",
        "memory",
    )

    pr = input_layer.dataProvider()
    feat = QgsFeature()
    feat.setAttributes(["75056104AV0133", "Other field value"])
    pr.addFeatures([feat])

    params = {
        "INPUT": input_layer,
        "FIELD": "parcelle",
        "OUTPUT": "TEMPORARY_OUTPUT",
    }

    context = QgsProcessingContext()
    feedback = QgsProcessingFeedback()

    result, success = alg.run(params, context, feedback, catchExceptions=False)
    assert success

    output_layer = context.getMapLayer(result["OUTPUT"])
    assert output_layer.isValid()
    assert output_layer.featureCount() == input_layer.featureCount()

    result = copy.deepcopy(GEOCODING_RESULT_ATTRIBUTES)
    result["other_field"] = "Other field value"
    expected_attributes = [result]
    for i, f in enumerate(output_layer.getFeatures()):
        for key, value in expected_attributes[i].items():
            assert f.attribute(key) == value
