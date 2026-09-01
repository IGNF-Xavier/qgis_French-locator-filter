# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## 1.6.7-exp - 2026-09-01

- fix(geocoder): the chained geocoder's parcel-by-idu WFS lookup (`_results_for_parcel`, used by direct search, and the new provenance layers) used an attribute-only `CQL_FILTER=idu=...` on the PCI `parcelle` layer, which has no index for that field on this ~100M-feature layer - verified live, it hung/timed out - silently degrading direct search results (parcel section/numero/commune/etc. all `None`) and breaking the provenance layers feature entirely. Now combines the idu filter with a `BBOX()` spatial constraint around a nearby known point (address, or the entity's own point), which is fast (verified live, ~0.2-0.7s)
- fix(geocoder): parcel and RNB building results (`GpfParcelGeocoder`, `GpfRnbGeocoder`) no longer use the real polygon as their own result geometry - `QgsBatchGeocodeAlgorithm` always creates a Point-typed output sink regardless of a geocoder's declared `wkbType()` and silently drops any non-Point result (a real QGIS behavior, confirmed live: it produced empty output layers for every batch parcel/RNB geocoding run). The real polygon (parcel `truegeometry`, RNB building `shape`) is still used for a tight viewport, and is now cached and exposed via a new "Charger la géométrie réelle" button in the reverse geocoding dock instead, built the same way as the chained geocoder's provenance layers
- fix(geocoder): request `returntruegeometry=true` on the parcel index (`GpfParcelGeocoder`, `GpfDynamicGeocoder`) - the plugin already had code to use this field for the viewport, but never actually requested it, so it silently never had anything to read

## 1.6.6-exp - 2026-08-14

- feat(ui): add a "Charger les géométries par provenance" button to the reverse geocoding dock (enabled for the chained geocoder only), building 5 deduplicated memory layers - Adresse, Parcelle, Bâtiment RNB, Bâtiment BDTOPO, Bâti PCI - from the currently displayed results, so every geometry behind a "fiche complète" result can be inspected on the map instead of just its single result point. Entities are deduplicated by their natural identifier (e.g. a parcel with 3 buildings is one feature, not 3 overlapping copies), each carrying `result_rows` plus the relevant linked ids (address/parcel/building) to trace it back to its row(s) in the results table. Nothing here runs during a normal search - only on explicit click - and each entity is fetched at most once (parcel WFS lookup, RNB `GET /buildings/{id}/` which already embeds the real shape, BDTOPO/PCI candidates)
- feat(geocoder): fetch BDTOPO (`BDTOPO_V3:batiment`) and PCI "bâti parcellaire" candidates around a parcel using a server-side `INTERSECTS` spatial filter on the parcel's real geometry, instead of a bounding-box query filtered client-side afterwards - avoids over-fetching neighbouring buildings on dense urban blocks, where a parcel's bbox often extends well past its own footprint

## 1.6.5-exp - 2026-08-14

- fix(geocoder): the chained geocoder's reverse search (point → parcel) only ran its per-parcel lookup chain (WFS `lien_bati_parcelle`, WFS `batiment`, RNB `buildings/plot` — 3 extra HTTP calls) on the parcel actually containing the clicked point, instead of on every parcel found in the 40 m search bbox; this caused both a noticeable slowdown and spurious extra parcels/results for a single click (falls back to the single nearest parcel when none contains the point, e.g. exactly on a boundary)

## 1.6.4-exp - 2026-08-14

- fix(geocoder): send an explicit `limit=1` on the base BAN geocoder's reverse geocoding requests (same missing-`limit=` bug already fixed on the parcel and dynamic geocoders, never applied to the plain BAN one), and cap `maximum_result_for_inverse_geocoding()` at 1 accordingly
- feat(geocoder): add a synthetic `result_index` attribute to the dynamic geocoder, always populated with the active index id (`address`/`poi`/`parcel`) regardless of whether the raw API response has a `type` property (parcel and POI results don't), so every row is identifiable
- refactor(geocoder): simplify the chained geocoder's label to `"{adresse} — Parcelle {idu}"`, dropping the RNB building id segment now that it has its own table column
- feat(geocoder): split the chained geocoder's BDTOPO building id into two independent columns instead of one with a fallback — `building_ext_bdtopo_id_wfs` (from the WFS `lien_bati_parcelle` link, as before) and `building_ext_bdtopo_id_rnb` (from the RNB building's own `ext_ids`, available even when the WFS link is missing) — so both sources can be compared
- feat(geocoder): add `parcel_type_lien` to the chained geocoder's direct search results (`"BAN"` = declared reliable link, `"GEO"` = geometrically inferred, less reliable), read from `lien_adresse_parcelle`'s `type_lien` field, to help explain cases where an address unexpectedly resolves to more than one parcel; left `None` on reverse geocoding, where the parcel is found spatially rather than via this link
- feat(ui): make the reverse geocoding dock's and the parcel search widget's result table columns reorderable by drag and drop (`setSectionsMovable(True)`)

## 1.6.3-exp - 2026-08-14

- refactor(geocoder): rebase the chained geocoder on the Géoplateforme WFS `BAN-PLUS` precomputed link layers (`lien_adresse_parcelle`, `lien_bati_parcelle`) and the PCI `parcellaire express` layer, instead of reconstructing the address/building/parcel link via RNB bounding-box search; adds a new `toolbelt/wfs_client.py` and `request_wfs_url` setting. Direct search now uses the authoritative BAN-PLUS link (with declared/inferred confidence); reverse search anchors on the real parcel geometry (WFS `parcelle`, spatial containment/distance ordering) rather than a heuristic RNB bbox. New attributes: `parcel_idu/section/numero/feuille/contenance/commune` (from the PCI, including the real parcel geometry as viewport) and `building_ext_bdtopo_id` (BDTOPO id, informational — the RNB API has no way to query by external id, confirmed by testing; building lookup now goes through the new `GET /buildings/plot/{idu}/` RNB endpoint instead)
- feat(geocoding): add `building_cadastral_ids`, the PCI "bâti parcellaire" identifier(s) (`CADASTRALPARCELS.PARCELLAIRE_EXPRESS:batiment`, a 3rd building dataset distinct from BDTOPO and RNB), found by a bbox query around the parcel geometry filtered to buildings that actually intersect it
- feat(ui): the reverse geocoding dock and the structured parcel search widget now display results as a proper multi-column table (one column per attribute, via the geocoder's `appendedFields()`) instead of a single column with a concatenated label

## 1.6.2-exp - 2026-08-14

- fix(geocoder): send an explicit `limit=` on the dynamic geocoder's reverse geocoding requests (1 per active index, at least 1) instead of letting the API default to `limit=10`, which flooded the interactive reverse geocoding dock with unrelated nearby candidates

## 1.6.1-exp - 2026-08-13

- feat(geocoding): add a chained geocoder (locator filter `fic`, reverse geocoding dock entry, batch Processing algorithms) combining address (BAN), RNB building and cadastral parcel(s) into a single "fiche complète" lookup, using the RNB `withPlots=1` parameter to get the intersecting parcel(s) without an extra API call; since a building can intersect several parcels, one result is emitted per (address, building, parcel) combination rather than squeezing a list into one attribute

## 1.6.0-exp - 2026-08-12

- feat(geocoding): add direct and reverse geocoding for the cadastral parcel index (`index=parcel`) of the Géoplateforme API, including locator filter, reverse geocoding dock entry and batch Processing algorithms
- feat(geocoding): add a structured parcel search widget (department → commune → section → number)
- feat(geocoding): add direct and reverse geocoding for the Référentiel National du Bâti (RNB), including locator filter, reverse geocoding dock entry and batch Processing algorithms; reverse results are enriched with the building's address, embedded directly in the RNB response
- refactor(geocoder): share the Géoplateforme host rate-limit counter between the address and parcel geocoders
- feat(geocoding): add a dynamic Géoplateforme geocoder (locator filter `gpf`, reverse geocoding dock entry, batch Processing algorithms) whose active index(es) — address, poi, parcel — are configurable in the plugin settings instead of hardcoded, driven by the service's GetCapabilities schema (embedded in the plugin package and refreshable from the settings page); resolves [#31](https://gitlab.com/Oslandia/qgis/french_locator_filter/-/issues/31) for the `/search` and `/reverse` routes (CSV batch routes deferred, see #37)
- feat(menu): add "Ajouter la couche RNB (bâtiments)" action and automatic loading of the RNB vector tile layer on first RNB reverse geocoding, to visually check results
- fix(geocoder): send an explicit `limit=1` on parcel reverse geocoding requests (the API otherwise defaults to `limit=10`, returning many unrelated nearby parcels)
- fix(geocoder): zero-pad the parcel number to 4 digits and strip the department prefix from the municipality code in the structured parcel search, matching the API's expected format

## 1.5.0 - 20226-03-09

- New logo by @florentfougeres
- Declare plugin compatible with qgis4 by @geojulien
- update(UI): add menu "Géocodage" for plugin actions by @jmkerloch
- feat(geocoder): define attributes types by @jmkerloch
- feat(reverse geocoding): allow selection of geocoder for reverse geocoding by @jmkerloch
- feat(batch): add batch processing with Photon geocoder by @jmkerloch
- feat(geocoding): add new function to define request param and result content by @jmkerloch
- feat(test): add mock for gpf server to be able to run test without internet connection by @jmkerloch
- fix(geocoding): use settings search_terms_to_ignore to limit search terms by @jmkerloch
- fix(geocoding): remove duplicated slash by @jmkerloch
- update(docs): add hyperlink to official tutorial on adresse.data.gouv.fr by @geojulien
- update(docs): distinguish release from current version by @geojulien
- add(docs): auto generate QDT snippet and use keepachangelog to retrieve latest published version from CHANGELOG.md by @geojulien
- add(docs): ajout section "plugin officiel" by @geojulien

## 1.4.1 - 2025-09-18

- feature: store geocoding result export to a memory layer (see !53)
- fix: no reportError function available for QgsFeedback (misused as QgsProcessingFeedback) !52
- fix: QMenu need a parent in Qt6 for correct use !54

## 1.4.0 - 2025-09-05

- New feature: add reverse geocoding processing and UI !49

## 1.3.0 - 2025-05-16

New implementation of QgsLocatorFilter using QgsGeocoderInterface. Adds a processing for batch geocoding.

- feat(geocoder): implement QgsGeocoderInterface for photon and BAN !30 #21
- feat(batch): add batch processing for FrenchBanGeocoder !37 #17
- feat(gpf): add function create_gpf_plugins_actions to be called by geoplateforme plugin !46
- feat(rest api): limit number of request per seconds (10 for photon, 50 for gpf)  !47 #29

## 1.2.0 - 2025-04-25

- project: set minimal QGIS version to 3.40.4
- feature: make plugin compatible with Qt6 (QGIS 4) #25 !34 !40
- feature: use the new endpoint for French BAN API #20 !41
- ci: modernize workflow !38
- fix: use new way to retrieve QgsLocatorResult._userData() to fix warnings !42
- tooling: bump dependencies !43
- contributors: Landry Breuil, Nicolas Godet, Jean-Marie Kerloch, Julien Moura

## 1.1.1 - 2024-06-12

- ValueError lors du déchargement du plugin #23

## 1.1.0 - 2024-02-09

- Add new locator with Photon API by Jean-Marie KERLOCH #19
- Fix min search length by Rémi Desgrange - !27
- Add help path and key to connect plugin documentation to standard help button in settings view by Julien Moura - !28

## 1.0.4 - 2022-10-20

- Handle special search terms to API - #9
- Reduce cases where a bug that can lead to a QGIS crash because of legacy method
- Add a button to reset settings to factory default
- Clean legacy code

## 1.0.3 - 2022-10-18

- change minimal search length See #8 - !20 by @nicogodet
- map report button to the bug issue template
- prevent Sonar run on forks
- dependencies update

## 1.0.2 - 2022-04-13

- add unit test running on QGIS
- improve settings management
- update dependencies

## 1.0.1 - 2022-01-03

- minor improvments on code quality
- better documentation

## 1.0.0 - 2021-06-17

- minor fix on settings dialog UI
- stable release

## 1.0.0-beta2 - 2021-06-11

- add debug mode
- small typo fixes #5
- minor improvments

## 1.0.0-beta1 - 2021-06-02

- use QGIS 3.16 abilities (especially on networking)
- apply Oslandia code quality standards (development tooling, documentation, CI, etc.)
- add settings: display used values and allow end-user customize some preferences
- fix deprecation warning on QgsCoordinateReferenceSystem

## 0.2.0 - 2020-03-17

- adds insee code display to municipalities

## 0.1.0 - 2019-10-08

- first version
