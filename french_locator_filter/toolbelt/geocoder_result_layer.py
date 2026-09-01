#! python3  # noqa: E265

"""
Helper to materialize QgsGeocoderResult lists as a memory vector layer,
shared between the reverse geocoding widget and the structured parcel
search widget.
"""

# standard library
from typing import List, Optional

# PyQGIS
from qgis.core import (
    QgsFeature,
    QgsGeocoderInterface,
    QgsGeocoderResult,
    QgsProject,
    QgsVectorLayer,
)


def results_to_memory_layer(
    geocoder: QgsGeocoderInterface,
    results: List[QgsGeocoderResult],
    layer_name: str,
) -> Optional[QgsVectorLayer]:
    """Build a memory point vector layer from a list of geocoder results.

    :param geocoder: geocoder used to produce the results (defines appended fields)
    :type geocoder: QgsGeocoderInterface
    :param results: geocoder results to materialize
    :type results: List[QgsGeocoderResult]
    :param layer_name: name of the created layer
    :type layer_name: str
    :return: memory layer, None if results is empty
    :rtype: Optional[QgsVectorLayer]
    """
    if not results:
        return None

    appended_fields = geocoder.appendedFields()

    feature_list = []
    for result in results:
        f = QgsFeature()
        additional_attributes = result.additionalAttributes()
        f.setAttributes(
            [additional_attributes.get(field.name()) for field in appended_fields]
        )
        f.setGeometry(result.geometry())
        feature_list.append(f)

    layer = QgsVectorLayer("Point", layer_name, "memory")
    layer.setCrs(results[0].crs())
    provider = layer.dataProvider()
    provider.addAttributes(appended_fields)
    layer.updateFields()

    layer.startEditing()
    for f in feature_list:
        layer.addFeature(f)
    layer.commitChanges()

    return layer


def results_to_real_geometry_layer(
    geocoder: QgsGeocoderInterface,
    results: List[QgsGeocoderResult],
    layer_name: str,
) -> Optional[QgsVectorLayer]:
    """Build a memory polygon layer from a geocoder's cached real geometries
    (parcel/building shape) behind a list of results, for a geocoder exposing
    a `geometry_for_result(result)` method (GpfParcelGeocoder, GpfRnbGeocoder).

    Results are still Point-geometried themselves (see those geocoders'
    docstrings: QgsBatchGeocodeAlgorithm always creates a Point-typed output
    sink regardless of a geocoder's declared wkbType(), verified live, so the
    real shape is only ever the *result's own* geometry for these two - it is
    kept in an opt-in cache instead, read here explicitly on demand).

    :param geocoder: geocoder that produced the results, exposing
        `geometry_for_result(result) -> Optional[QgsGeometry]`
    :type geocoder: QgsGeocoderInterface
    :param results: geocoder results to materialize
    :type results: List[QgsGeocoderResult]
    :param layer_name: name of the created layer
    :type layer_name: str
    :return: memory layer, None if no result had a cached real geometry
    :rtype: Optional[QgsVectorLayer]
    """
    if not results:
        return None

    appended_fields = geocoder.appendedFields()

    feature_list = []
    for result in results:
        geometry = geocoder.geometry_for_result(result)
        if not geometry:
            continue
        f = QgsFeature()
        additional_attributes = result.additionalAttributes()
        f.setAttributes(
            [additional_attributes.get(field.name()) for field in appended_fields]
        )
        f.setGeometry(geometry)
        feature_list.append(f)

    if not feature_list:
        return None

    layer = QgsVectorLayer("MultiPolygon", layer_name, "memory")
    layer.setCrs(results[0].crs())
    provider = layer.dataProvider()
    provider.addAttributes(appended_fields)
    layer.updateFields()

    layer.startEditing()
    for f in feature_list:
        layer.addFeature(f)
    layer.commitChanges()

    return layer


def add_results_as_layer(
    geocoder: QgsGeocoderInterface,
    results: List[QgsGeocoderResult],
    layer_name: str,
) -> Optional[QgsVectorLayer]:
    """Build a memory layer from geocoder results and add it to the current project.

    :param geocoder: geocoder used to produce the results (defines appended fields)
    :type geocoder: QgsGeocoderInterface
    :param results: geocoder results to materialize
    :type results: List[QgsGeocoderResult]
    :param layer_name: name of the created layer
    :type layer_name: str
    :return: the added layer, None if results is empty
    :rtype: Optional[QgsVectorLayer]
    """
    layer = results_to_memory_layer(geocoder, results, layer_name)
    if layer is not None:
        QgsProject.instance().addMapLayer(layer)
    return layer


def add_real_geometry_layer(
    geocoder: QgsGeocoderInterface,
    results: List[QgsGeocoderResult],
    layer_name: str,
) -> Optional[QgsVectorLayer]:
    """Build a memory layer from a geocoder's cached real geometries and add
    it to the current project. See results_to_real_geometry_layer().

    :param geocoder: geocoder that produced the results, exposing
        `geometry_for_result(result) -> Optional[QgsGeometry]`
    :type geocoder: QgsGeocoderInterface
    :param results: geocoder results to materialize
    :type results: List[QgsGeocoderResult]
    :param layer_name: name of the created layer
    :type layer_name: str
    :return: the added layer, None if no result had a cached real geometry
    :rtype: Optional[QgsVectorLayer]
    """
    layer = results_to_real_geometry_layer(geocoder, results, layer_name)
    if layer is not None:
        QgsProject.instance().addMapLayer(layer)
    return layer
