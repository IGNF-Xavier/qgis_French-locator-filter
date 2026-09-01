"""Widget for reverse geocoding"""

# standard
from pathlib import Path
from typing import Optional

# PyQGIS
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsCoordinateTransformContext,
    QgsFeature,
    QgsGeocoderContext,
    QgsGeometry,
)
from qgis.PyQt import uic
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor, QIcon
from qgis.PyQt.QtWidgets import QHeaderView, QWidget

# project
from french_locator_filter.__about__ import DIR_PLUGIN_ROOT
from french_locator_filter.core.geocoder.addok_ban_fr_geocoder import FrenchBanGeocoder
from french_locator_filter.core.geocoder.gpf_chained_geocoder import GpfChainedGeocoder
from french_locator_filter.core.geocoder.gpf_dynamic_geocoder import GpfDynamicGeocoder
from french_locator_filter.core.geocoder.gpf_parcel_geocoder import GpfParcelGeocoder
from french_locator_filter.core.geocoder.gpf_rnb_geocoder import GpfRnbGeocoder
from french_locator_filter.core.geocoder.photon_geocoder import PhotonGeocoder
from french_locator_filter.gui.mdl_geocoder_result import QgsGeocoderResultModel
from french_locator_filter.toolbelt.chained_provenance_layers import (
    add_provenance_layers,
)
from french_locator_filter.toolbelt.geocoder_result_layer import (
    add_real_geometry_layer,
    add_results_as_layer,
)
from french_locator_filter.toolbelt.rnb_tile_layer import add_rnb_vector_tile_layer


class ReverseGeocodingWidget(QWidget):
    """QWidget to ask geoplateforme for reverse geocoding

    :param parent: dialog parent, defaults to None
    :type parent: Optional[QWidget], optional
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        ui_path = Path(__file__).resolve(True).parent / "wdg_reverse_geocoding.ui"
        uic.loadUi(ui_path, self)

        self.setWindowIcon(
            QIcon(str(DIR_PLUGIN_ROOT / "resources/images/gpf-geocodage.png"))
        )

        self.btn_run.setIcon(QIcon(":images/themes/default/mActionStart.svg"))
        self.btn_run.clicked.connect(self._reverse_geocoding)

        self.btn_load.setIcon(QIcon(":/images/themes/default/mActionCreateMemory.svg"))
        self.btn_load.clicked.connect(self._load_results)

        self.btn_load_provenance.setIcon(
            QIcon(":/images/themes/default/mActionCreateMemory.svg")
        )
        self.btn_load_provenance.clicked.connect(self._load_provenance_layers)
        self.btn_load_provenance.setEnabled(False)

        self.btn_load_real_geometry.setIcon(
            QIcon(":/images/themes/default/mActionCreateMemory.svg")
        )
        self.btn_load_real_geometry.clicked.connect(self._load_real_geometry_layer)
        self.btn_load_real_geometry.setEnabled(False)

        self.cbx_geocoder.currentIndexChanged.connect(self._update_provenance_button)
        self.cbx_geocoder.currentIndexChanged.connect(self._update_real_geometry_button)

        self.wdg_selection.set_marker_color(QColor("green"))

        self.mdl_result = QgsGeocoderResultModel(self)
        self.tbv_geocoder_result.setModel(self.mdl_result)

        self.tbv_geocoder_result.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.tbv_geocoder_result.horizontalHeader().setSectionsMovable(True)

        self._result_geocoder = None
        self.cbx_geocoder.addItem(
            self.tr("French Adress geocoder"), FrenchBanGeocoder()
        )
        self.cbx_geocoder.addItem(self.tr("Photon Adress geocoder"), PhotonGeocoder())
        self.cbx_geocoder.addItem(
            self.tr("Parcelle cadastrale (Géoplateforme)"), GpfParcelGeocoder()
        )
        self.cbx_geocoder.addItem(self.tr("RNB - bâtiment"), GpfRnbGeocoder())
        self.cbx_geocoder.addItem(
            self.tr("Géoplateforme (index configurables)"), GpfDynamicGeocoder()
        )
        self.cbx_geocoder.addItem(
            self.tr("Fiche complète (adresse + bâtiment + parcelle)"),
            GpfChainedGeocoder(),
        )
        self._update_provenance_button()
        self._update_real_geometry_button()

    def _update_provenance_button(self) -> None:
        """Enable "Charger les géométries par provenance" only for the chained
        geocoder - the only one with several distinct entities (address,
        parcel, buildings) to visualize per result"""
        self.btn_load_provenance.setEnabled(
            isinstance(self.cbx_geocoder.currentData(), GpfChainedGeocoder)
        )

    def _update_real_geometry_button(self) -> None:
        """Enable "Charger la géométrie réelle" only for geocoders exposing a
        cached real (parcel/building) geometry - their results stay
        Point-geometried themselves (QgsBatchGeocodeAlgorithm always creates
        a Point-typed output sink regardless of a geocoder's declared
        wkbType() and silently drops any non-Point result, verified live)"""
        geocoder = self.cbx_geocoder.currentData()
        self.btn_load_real_geometry.setEnabled(
            isinstance(geocoder, (GpfParcelGeocoder, GpfRnbGeocoder))
        )

    def _reverse_geocoding(self) -> None:
        """Ask for a reverse geocoding"""
        selected_point = self.wdg_selection.get_referenced_displayed_point()

        feature = QgsFeature()
        geometry = QgsGeometry.fromPointXY(selected_point)
        transform_context = QgsCoordinateTransformContext()
        transform = None
        if self.wdg_selection.get_crs() != QgsCoordinateReferenceSystem("EPSG:4326"):
            transform = QgsCoordinateTransform(
                self.wdg_selection.get_crs(),
                QgsCoordinateReferenceSystem("EPSG:4326"),
                transform_context,
            )
            geometry.transform(transform)
        feature.setGeometry(geometry)

        context = QgsGeocoderContext(transform_context)
        self._result_geocoder = self.cbx_geocoder.currentData()
        if isinstance(self._result_geocoder, GpfRnbGeocoder):
            add_rnb_vector_tile_layer()
        results = self._result_geocoder.geocodeFeature(feature, context)

        # Rebuild columns for this geocoder's fields (also clears current results)
        self.mdl_result.set_fields(self._result_geocoder.appendedFields())

        # Add available results
        for result in results:
            self.mdl_result.add_geocoder_result(result)

        self.tbv_geocoder_result.resizeColumnsToContents()

    def _load_results(self) -> None:
        """Load result as QgsVectorLayer from current search"""
        if self._result_geocoder is None:
            return

        results = []
        for row in range(0, self.mdl_result.rowCount()):
            geocoder_result = self.mdl_result.data(
                self.mdl_result.index(row, self.mdl_result.IDENTIFIER_COL),
                Qt.ItemDataRole.UserRole,
            )
            if geocoder_result:
                results.append(geocoder_result)

        add_results_as_layer(
            self._result_geocoder, results, self.tr("Résultats géocodage inversé")
        )

    def _load_provenance_layers(self) -> None:
        """Load the currently displayed chained geocoder results as separate,
        deduplicated layers per provenance (address, parcel, buildings)"""
        if not isinstance(self._result_geocoder, GpfChainedGeocoder):
            return

        rows = []
        for row in range(0, self.mdl_result.rowCount()):
            geocoder_result = self.mdl_result.data(
                self.mdl_result.index(row, self.mdl_result.IDENTIFIER_COL),
                Qt.ItemDataRole.UserRole,
            )
            if geocoder_result:
                rows.append((row + 1, geocoder_result))

        add_provenance_layers(
            self._result_geocoder, rows, self.tr("Fiche complète - géométries")
        )

    def _load_real_geometry_layer(self) -> None:
        """Load the currently displayed parcel/RNB building results as a
        polygon layer, using each geocoder's cached real geometry"""
        if not isinstance(self._result_geocoder, (GpfParcelGeocoder, GpfRnbGeocoder)):
            return

        results = []
        for row in range(0, self.mdl_result.rowCount()):
            geocoder_result = self.mdl_result.data(
                self.mdl_result.index(row, self.mdl_result.IDENTIFIER_COL),
                Qt.ItemDataRole.UserRole,
            )
            if geocoder_result:
                results.append(geocoder_result)

        add_real_geometry_layer(
            self._result_geocoder, results, self.tr("Géométrie réelle")
        )
