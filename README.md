# French Locator Filter

> ⚠️ **Fork expérimental / version test.** Ce dépôt part du plugin officiel [French Locator Filter d'Oslandia](https://gitlab.com/Oslandia/qgis/french_locator_filter) et y ajoute plusieurs sources et fonctionnalités de géocodage non présentes dans la version officielle (parcelle cadastrale, bâtiments RNB, "fiche complète", chargement des géométries réelles...). Ces ajouts n'ont pas été revus/validés par Oslandia, peuvent contenir des bugs, et l'API interne peut encore changer sans préavis. À utiliser en connaissance de cause, pas en production critique.

## À quoi sert ce plugin ?

Retrouver, pour une adresse, une parcelle cadastrale ou un bâtiment en France, sa localisation et les objets qui lui sont liés — sans quitter QGIS et sans appel manuel à une API. Concrètement, le plugin permet de :

- **Chercher du texte** ("12 rue de la Paix, 75002 Paris", un numéro de parcelle, un identifiant RNB...) dans la barre de recherche universelle de QGIS et zoomer directement dessus.
- **Cliquer un point sur la carte** et obtenir l'adresse, la parcelle ou le bâtiment à cet endroit (géocodage inversé), via un dock dédié.
- **Enchaîner adresse → parcelle → bâtiment(s)** en une seule recherche ("Fiche complète"), plutôt que de chercher chaque objet séparément et de les recouper à la main.
- **Charger les résultats sous forme de couche** QGIS (points, ou géométrie réelle des parcelles/bâtiments quand elle est disponible) pour les visualiser, les exporter ou les réutiliser dans une analyse.
- **Géocoder un fichier entier en lot** (adresses ou coordonnées dans un tableur/couche) via les traitements Processing, avec les mêmes règles que la recherche interactive — donc utilisable aussi en ModelBuilder.

## Les six sources disponibles

| Source                              | Préfixe locator | Direct | Inversé | À quoi elle sert |
|--------------------------------------|:---:|:---:|:---:|---|
| Adresse — Base Adresse Nationale (BAN) | `fra` | ✅ | ✅ | La source d'adresses officielle française |
| Photon (OpenStreetMap)                | `pho` | ✅ | ✅ | Alternative à la BAN, utile si une adresse n'y est pas référencée |
| Parcelle cadastrale                   | `par` | ✅ | ✅ | Retrouver une parcelle par son identifiant, ou par département/commune/section/numéro via un formulaire dédié |
| Bâtiment — Référentiel National du Bâti (RNB) | `rnb` | ✅ | ✅ | Retrouver un bâtiment et l'adresse qui lui est associée |
| Géoplateforme (index configurables)   | `gpf` | ✅ | ✅ | Recherche multi-index (adresse, POI, parcelle) en un seul appel, au choix dans les réglages |
| **Fiche complète** (adresse + parcelle + bâtiment) | `fic` | ✅ | ✅ | Le "tout-en-un" : adresse, parcelle(s) et bâtiment(s) liés, en une recherche |

## Utilisation

### Recherche directe (barre d'outils)

Tapez du texte dans le Localisateur (barre de recherche QGIS, en bas à gauche) précédé du préfixe de la source voulue (ex. `fic 12 rue de la Paix Paris`), ou laissez QGIS proposer toutes les sources actives. Un résultat sélectionné zoome/centre la carte dessus.

### Géocodage inversé (dock)

Menu **Géocodage → Géocodage inversé** : choisissez une source, cliquez un point sur la carte (ou saisissez des coordonnées), lancez la recherche. Les résultats s'affichent en tableau (une colonne par attribut, colonnes réordonnables par glisser-déposer). Trois boutons permettent d'exporter :

- **Charger** : les résultats en couche ponctuelle.
- **Charger la géométrie réelle** *(parcelle, RNB)* : le contour réel de la parcelle ou du bâtiment plutôt qu'un simple point, quand la donnée est disponible.
- **Charger les géométries par provenance** *(Fiche complète)* : cinq couches distinctes et dédupliquées — Adresse, Parcelle, Bâtiment RNB, Bâtiment BDTOPO, Bâti cadastral (PCI) — pour visualiser tous les objets liés à une recherche, avec de quoi retrouver quelle ligne du tableau correspond à quelle géométrie.

### Recherche structurée de parcelle

Menu **Géocodage → Recherche de parcelle** : formulaire département → commune → section → numéro, pour les cas où on connaît la référence cadastrale plutôt qu'une adresse.

### Traitements par lot (Processing)

Dans la boîte à outils Processing, catégorie du plugin : un traitement par source et par sens (direct/inversé), pour géocoder une couche entière (ex. une liste d'adresses dans un tableur) en une seule opération. Les mêmes règles que la recherche interactive s'appliquent (limites de résultats, filtres, etc.), donc un traitement se comporte de façon identique en usage manuel ou dans un modèle ModelBuilder.

## Limitations connues

- Les traitements par lot renvoient toujours un point (jamais la géométrie réelle d'une parcelle/bâtiment), même quand la source la fournit : c'est une limitation de l'algorithme QGIS sous-jacent (`QgsBatchGeocodeAlgorithm`), pas un choix du plugin. Utilisez le bouton "Charger la géométrie réelle" dans le dock pour l'obtenir en recherche interactive.
- La "Fiche complète" dépend de plusieurs services (BAN, RNB, WFS Géoplateforme/PCI/BDTOPO) : une recherche peut donc être plus lente que les autres sources, et échouer partiellement si l'un des services est indisponible.

## Détails techniques

<details>
<summary>Ce que fait chaque source lors d'une recherche par texte (direct) ou par point cliqué (inversé)</summary>

### Adresse — BAN (`fra`)

- **Direct** : appel `GET /search` de l'API Géoplateforme (données de la Base Adresse Nationale), avec le texte saisi comme requête libre.
- **Inversé** : appel `GET /reverse` avec les coordonnées du point cliqué et `limit=1` explicite, pour ne remonter que l'adresse la plus proche (l'API renvoie jusqu'à 10 résultats par défaut si `limit` n'est pas précisé).

### Photon — OpenStreetMap (`pho`)

- **Direct** : appel `GET /api` de l'instance Photon (recherche libre, hors Géoplateforme, basée sur les données OpenStreetMap).
- **Inversé** : appel `GET /reverse` de la même API avec les coordonnées du point cliqué.

### Parcelle cadastrale (`par`)

- **Direct**, deux modes :
  - recherche libre depuis la barre de recherche : `GET /search?index=parcel` avec le texte saisi ;
  - recherche structurée depuis le widget dédié (département → commune, la liste des communes étant récupérée via `geo.api.gouv.fr` → section → numéro) : appel du même index mais avec des paramètres structurés (`departmentcode`, `municipalitycode`, `section`, `number`) plutôt qu'une requête libre ; le numéro de parcelle est complété à 4 chiffres (`"183"` → `"0183"`) et le code commune est utilisé sans son préfixe département, conformément au format attendu par l'API.
- **Inversé** : `GET /reverse?index=parcel` avec `limit=1`, pour ne renvoyer que la parcelle contenant le point cliqué (et non toutes les parcelles voisines dans le rayon de recherche par défaut).
- La vraie géométrie de la parcelle (`returntruegeometry=true`, propriété `truegeometry`) sert à calculer un viewport précis et est mise en cache pour le bouton "Charger la géométrie réelle" — jamais comme géométrie du résultat lui-même (voir Limitations connues).

### Bâtiment — RNB (`rnb`)

Le RNB n'offre ni recherche libre ni recherche point+rayon : ce géocodeur combine donc deux API indépendantes.

- **Direct** : le texte saisi est d'abord résolu en adresse via l'index adresse de la Géoplateforme (`/search`), puis l'identifiant BAN de cette adresse (`cle_interop_ban`) sert à interroger `GET /buildings/` du RNB pour récupérer le ou les bâtiments à cette adresse.
- **Inversé** : `GET /buildings/` du RNB est interrogé avec une petite emprise (`bbox`, ~40 m) autour du point cliqué ; les bâtiments candidats sont ensuite triés — ceux dont l'empreinte contient le point d'abord, les autres par distance croissante. Chaque bâtiment RNB embarque déjà l'adresse à laquelle il est rattaché : elle est utilisée directement pour enrichir le résultat, sans requête supplémentaire vers la BAN.
- La forme réelle du bâtiment (`shape`, quand RNB en a une) suit la même logique que la parcelle : viewport + cache pour "Charger la géométrie réelle", jamais géométrie du résultat.

### Géoplateforme — index configurables (`gpf`)

- **Direct** : un seul appel `GET /search?index=...` avec la liste des index actifs choisis dans les réglages (adresse, POI, parcelle) ; chaque résultat est typé par le champ `_type` de la réponse, exposé dans la colonne `result_index` (utile pour les index parcelle/POI, qui n'ont pas de colonne "type" native contrairement à l'index adresse).
- **Inversé** : `GET /reverse?index=...` avec `limit` égal au nombre d'index actifs (au moins 1), pour obtenir un résultat pertinent par index sans être noyé par le rayon de recherche par défaut de l'API.

### Fiche complète (`fic`)

Chaîne adresse → parcelle cadastrale → bâtiment RNB en une seule recherche, en s'appuyant sur les couches WFS `BAN-PLUS` de la Géoplateforme (liens précalculés adresse↔parcelle et bâtiment↔parcelle) et sur la couche PCI `parcellaire express`, plutôt que sur une reconstruction heuristique par recherche géométrique. Comme une adresse peut être liée à plusieurs parcelles, et une parcelle à plusieurs bâtiments, le géocodeur retourne un résultat distinct par combinaison (adresse, parcelle, bâtiment) — l'équivalent d'une jointure SQL — plutôt que de compresser des listes dans un seul attribut.

- **Direct** :
  1. l'adresse est résolue via la BAN (`/search`) ;
  2. son identifiant (`id_adr`) est recherché dans la couche WFS `lien_adresse_parcelle` pour obtenir la ou les parcelle(s) liée(s), avec le niveau de confiance du lien (`type_lien` : `BAN` = lien déclaré fiable, `GEO` = inféré géométriquement — exposé en colonne `parcel_type_lien`) ;
  3. pour chaque parcelle : récupération de sa géométrie réelle (WFS PCI `parcelle`), des bâtiments RNB dessus (`GET /buildings/plot/{idu}/`), des identifiants BDTOPO liés via la couche WFS `lien_bati_parcelle` (colonne `building_ext_bdtopo_id_wfs`) et via les `ext_ids` propres à chaque bâtiment RNB (colonne `building_ext_bdtopo_id_rnb`, indépendante de la précédente), ainsi que des bâtiments PCI ("bâti parcellaire", couche WFS `batiment`) qui intersectent réellement la parcelle.
- **Inversé** :
  1. les parcelles candidates sont recherchées directement par géométrie autour du point cliqué (bbox sur la couche WFS PCI `parcelle`), triées par containment puis distance, et seule(s) celle(s) contenant réellement le point sont conservées (repli sur la plus proche si aucune ne le contient) ;
  2. l'adresse au point cliqué est résolue via la BAN inversée (`limit=1`) ;
  3. pour chaque parcelle retenue, les mêmes étapes bâtiment RNB / BDTOPO / bâti cadastral que pour la recherche directe sont exécutées ; `parcel_type_lien` reste vide, la parcelle étant trouvée par géométrie et non via le lien adresse↔parcelle.
- Les recherches par attribut seul sur les grandes couches WFS (parcelle par `idu`, bâtiment BDTOPO par `cleabs`) n'étant pas indexées côté serveur, elles sont systématiquement combinées à une contrainte spatiale (bbox ou `INTERSECTS`) pour rester rapides.

</details>

## Code source

[Code officiel à l'origine Gitlab Oslandia](https://gitlab.com/Oslandia/qgis/french_locator_filter)
