# EVENTSKG: Reproducible and Interoperable Linked Data on Top-Ranked Computer Science Events

[![License: CC BY 4.0](https://img.shields.io/badge/License-CC%20BY%204.0-blue.svg)](https://creativecommons.org/licenses/by/4.0/)
[![FAIR Principles](https://img.shields.io/badge/FAIR-Data%20Findable%20Accessible%20Interoperable%20Reusable-blueviolet.svg)](https://www.go-fair.org/fair-principles/)
[![5-Star Open Data](https://img.shields.io/badge/Open%20Data-5%E2%98%85-gold.svg)](https://5stardata.info/en/)
[![Release](https://img.shields.io/badge/Release-3.0-green.svg)](#whats-new-in-release-30)
[![DOI](https://img.shields.io/badge/DOI-10%2E5281%2Fzenodo%2E23806362-blue.svg)](https://doi.org/10.5281/zenodo.23806362)

<!-- Academic & Citation -->
[![DOI: 10.1007/978-3-030-21348-0_28](https://img.shields.io/badge/DOI-10.1007%2F978--3--030--21348--0__28-blue.svg)](https://doi.org/10.1007/978-3-030-21348-0_28)
[![Paper: ESWC 2019](https://img.shields.io/badge/Paper-ESWC%202019-red.svg)](https://link.springer.com/chapter/10.1007/978-3-030-21348-0_28)

<!-- Repository Maintenance & Health -->
[![GitHub Last Commit](https://img.shields.io/github/last-commit/saidfathalla/EVENTSKG-Dataset.svg)](https://github.com/saidfathalla/EVENTSKG-Dataset/commits/master)
[![Maintenance API](https://img.shields.io/badge/API-EVENTSKG__API-informational.svg)](https://github.com/saidfathalla/EVENTSKG_API)

EVENTSKG (formerly EVENTS) is a 5-star Linked Open Dataset of top-ranked computer science events. For **2,531 editions of 75 event series** from **eight communities (1969–2026)** it records titles and acronyms, dates, cities, states and countries (linked to DBpedia and Wikidata), submitted and accepted papers, acceptance rates, publishers, sponsors, homepages, and the attendance mode and status of each edition.

**Documentation:** <https://saidfathalla.github.io/EVENTSKG-Dataset/docs/> · **SPARQL explorer:** <https://saidfathalla.github.io/EVENTSKG-Dataset/docs/sparql.html> · **Namespace:** `http://w3id.org/EVENTSKG-Dataset/ekg#`

---

## What's New in Release 3.0

* **Extended coverage.** 561 editions held from 2019 to 2026 were added, including the announced editions of 2026, and 44 missing historical editions were filled in: 2,531 events instead of 1,929 (+31%).
* **Corrected and completed data.** More than 2,500 documented corrections fix wrong series, titles, homepages, places and dates inherited from earlier releases. Titles are now complete for all events and publishers for 99.5% of them.
* **Attendance mode and status.** Two schema.org properties are new:
  * `schema:eventAttendanceMode`: online or mixed editions (129 events), which makes the move to virtual events during the COVID-19 pandemic visible;
  * `schema:eventStatus`: scheduled, cancelled or postponed editions.
* **Reproducible generation.** The knowledge graph is generated from one curated CSV file by a declarative [SSSOM](https://mapping-commons.github.io/sssom/) mapping, with constraint checks and SHACL validation. Anyone can rebuild a release from the files in this repository (see [Reproducing the release](#reproducing-the-release)).
* **Enrichment.** After generation, every place link is checked against DBpedia (existence, redirects, DBpedia language chapters, kind of place), every resource gets an `rdf:type` and an `rdfs:label`, and every place gets an `owl:sameAs` link to its Wikidata item. No volatile facts (populations, areas …) are copied.
* **Two editions.**
  * **Generated** (`EVENTSKG.ttl`, 39,479 triples): exactly the curated facts, the reference for reproducing the release.
  * **Enriched** (`EVENTSKG-enriched.ttl`, 44,173 triples): adds verified, typed and labelled places and the Wikidata links. Recommended for querying and integration.
* **Self-describing.** Each edition contains a dataset description: title, creators, licence, version, issue date, VoID statistics, and a `prov:wasRevisionOf` link to the previous release.
* **Fully compatible.** All IRIs and properties of release 2 are kept (`seo:`, `conference-ontology:`, `dbpedia-owl:state`), so existing queries keep working.
* **HTML documentation and SPARQL explorer.** A documentation page with statistics and downloads, and a SPARQL 1.1 explorer that runs in the browser without any installation.

### Effect of the enrichment

| | Generated | Enriched |
|---|---:|---:|
| Resources with an `rdf:type` | 78.4% | 98.9% |
| Resources with an `rdfs:label` | 0% | 98.2% |
| Classes | 17 | 35 |
| Links to DBpedia and Wikidata | 6,020 | 6,676 |
| `owl:sameAs` links to Wikidata | – | 656 |
| Places checked against DBpedia (confirmed / typed from role / other kind / not found) | – | 665 (580 / 37 / 41 / 7) |
| Redirecting DBpedia IRIs replaced | – | 13 |
| Triples | 39,479 | 44,173 |

### Communities covered

1. Artificial Intelligence (AI)
2. Software and its Engineering (SE)
3. World Wide Web (WEB)
4. Security and Privacy (SEC)
5. Information Systems (IS)
6. Computer Systems Organization (CSO)
7. Human-Centered Computing (HCC)
8. Theory of Computation (TOC)

### Earlier releases

* **Release 2.1**: the last version of release 2: 75 event series, 1,929 events up to 2018, 26,626 triples. Archived in [`archive/R2.1/`](archive/R2.1/).
* **Release 2.0** (ESWC 2019): 73 event series, 1,951 events, 29,255 triples. It added HCC and TOC, full alignment with the **Scientific Events Ontology (SEO)** (`https://w3id.org/seo#`), and unified rankings from CORE, QUALIS, ERA and GGS through the Scientific Events Ranking (SER) weighted framework.
* **Release 1**: the first release (as EVENTS), with six communities.

---

## Repository Layout

| Path | Content |
|---|---|
| `EVENTSKG.ttl` | Release 3.0, generated edition (Turtle) |
| `EVENTSKG-enriched.ttl` | Release 3.0, enriched edition (Turtle) |
| `VoID.ttl` | Dataset description with VoID statistics |
| `serializations/` | Both editions as N-Triples (`.nt`), JSON-LD (`.jsonld`), RDF/XML (`.rdf`) and N3 (`.n3`) |
| `data/EVENTSKG_data.csv` | The curated record: one row per event with its series (2,531 rows, 75 series) |
| `data/dbpedia_places.csv` | Place names and their DBpedia IRIs (`place_type`, `name`, `state`, `country`, `iri`) |
| `data/eventskg.sssom.tsv`, `data/eventskg.sssom.yml` | The SSSOM mapping set: which property each column becomes, and the dataset description (`dataset_*` keys) |
| `scripts/csv2rdf.py` | Generation: CSV + mapping → RDF |
| `scripts/enrich.py`, `scripts/enrich.yml` | Enrichment and its configuration |
| `shapes/` | SHACL shapes |
| `stats/` | Statistics pages of the generated and the enriched edition |
| `.enrich_cache.json` | Cached DBpedia and Wikidata answers, so the enrichment can be repeated offline |
| `archive/` | Earlier releases |
| `docs/` | Documentation website (`index.html`) and SPARQL explorer (`sparql.html`), published with GitHub Pages |

---

## Reproducing the Release

Every release is generated from the curated CSV; nothing is edited by hand in the RDF. Two steps rebuild both editions:

```bash
git clone https://github.com/saidfathalla/EVENTSKG-Dataset.git
cd EVENTSKG-Dataset
pip install rdflib pyyaml pyshacl

# 1. Generate: CSV + SSSOM mapping -> all RDF serializations, VoID description, statistics
python3 scripts/csv2rdf.py data/EVENTSKG_data.csv data/eventskg.sssom.tsv \
        --places data/dbpedia_places.csv --include data/eventskg-metadata.ttl \
        -o release/EVENTSKG --void release/VoID --stats release/stats.html \
        --compare archive/R2.1/EVENTSKG.ttl
python3 -m pyshacl -s shapes/shapes.ttl -df turtle release/EVENTSKG.ttl

# 2. Enrich: check places against DBpedia, add types, labels and Wikidata links
python3 scripts/enrich.py release/EVENTSKG.ttl -c scripts/enrich.yml \
        -o release/EVENTSKG-enriched --stats release/stats-enriched.html
```

Result of step 1: 2,531 events, 75 series, 39,479 triples, `0 errors, 0 warnings`, SHACL `Conforms: True`.
Step 2 uses the answers in `.enrich_cache.json` and gives the same 44,173 triples; add `--offline` to make sure no external service is asked, or `--refresh` to ask DBpedia and Wikidata again.

### Generation: `csv2rdf.py`

`csv2rdf.py` is a generic converter: it turns *any* CSV file into RDF, and what each column becomes is written in the SSSOM mapping. Nothing in the tool is EVENTSKG-specific.

| Option | What it does |
|---|---|
| `-o BASE` | Base name of the output. Writes `BASE.ttl`, `.nt`, `.jsonld`, `.rdf` and `.n3`. The default is the data file name. |
| `--formats ttl,nt` | Writes only the formats listed (default: all). |
| `--places FILE` | DBpedia places file used to link cities, states and countries. |
| `--void BASE` | Writes the dataset description with VoID counts to `BASE.ttl`, `.nt` … |
| `--stats FILE.html` | Writes a statistics page: classes, completeness of each property, events per year, paper counts, most frequent places, fields and series. |
| `--compare FILE` | Prints the counts of an earlier release next to the new ones; it does not change the output. |
| `--report FILE` | Where problems are written (default `report.csv` next to the output, written only when there are errors or warnings). |
| `--date`, `--dataset`, `--include` | Set `dcterms:modified`, override the dataset IRI, and merge extra Turtle files. |

The converter checks the data while converting: required and unique values, ISO dates, start date not after end date, accepted papers not more than submitted papers, acceptance rate between 0 and 1 (computed if empty), controlled values, the same series data on every edition of a series, and places missing from the places file. A bad cell is reported with its CSV line and skipped; the rest of the row is still converted. The exit code is 1 when there are errors.

### Enrichment: `enrich.py`

| Option | What it does |
|---|---|
| `-c FILE.yml` | Configuration: which properties hold places and the class each requires, labels, value types (default `enrich.yml`). |
| `-o BASE` | Output base name; writes all formats (default: input name + `-enriched`). |
| `--stats FILE.html` | Statistics page comparing the graph before and after enrichment. |
| `--untyped FILE.csv` | Resources left without a type, with their name, the reason and the events that use them. |
| `--report FILE`, `--warnings` | Errors (and, with `--warnings`, notes) found while checking the places. |
| `--changes FILE` | List of replaced (redirecting) IRIs. |
| `--keep-redirects` | Only report redirecting IRIs instead of replacing them. |
| `--chapters de,fr,…` | DBpedia language chapters to look in for places missing from the English DBpedia. |
| `--types expected\|all\|none` | Types added to places: the class of their role (default), all DBpedia types, or none. |
| `--cache FILE`, `--offline`, `--refresh` | Answer cache; use only cached answers; ignore the cache. |
| `--no-check` | Do not query DBpedia; only update the VoID counts. |

### How IRIs are made

* **Series**: `eventskg:{series_acronym}`, e.g. `eventskg:CVPR` (the same IRIs as release 2).
* **Event**: `eventskg:{series_acronym}{year}`, e.g. `eventskg:CVPR2026`. The `event_id` column is filled only for the 24 release 2 events whose IRI does not follow this rule (e.g. `TheWeb1994_2`).

### Curating

* **New edition**: add a row to `data/EVENTSKG_data.csv` and leave `event_id` empty.
* **Correct a value**: edit the cell. Several values in one cell are separated by `|`.
* **New place**: add its DBpedia IRI to `data/dbpedia_places.csv`. The enrichment checks it and lists problems in its report and in the untyped file.
* **New release**: edit the dataset block in `data/eventskg.sssom.yml` (`dataset_version`, `dataset_issued`, `dataset_previous_version`), then run both steps.
* **Map a new column**: add a row to `data/eventskg.sssom.tsv`. Columns without a mapping (e.g. `notes`) stay in the CSV only.

---

## Automation & Quality Control

This repository uses **GitHub Actions** workflows to maintain data quality, syntax correctness, and link stability:

* **RDF Syntax Validation (`validate-rdf.yml`)**: on every push and pull request, the RDF files are parsed with `RDFLib` to catch syntax errors.
* **Link Checking (`link-check.yml`)**: a weekly check that external links, dataset dumps and persistent IRIs are online.
* **Pages Deployment (`pages-build-deployment.yml`)**: deploys the documentation in `docs/` to GitHub Pages.

Each release is also validated against the SHACL shapes (see [Reproducing the release](#reproducing-the-release)).

---

## Access

| Resource | Address |
|---|---|
| Namespace (content negotiation: HTML for browsers, RDF for clients) | <http://w3id.org/EVENTSKG-Dataset/ekg#> |
| Documentation | <https://saidfathalla.github.io/EVENTSKG-Dataset/docs/> |
| SPARQL explorer (SPARQL 1.1, runs in the browser) | <https://saidfathalla.github.io/EVENTSKG-Dataset/docs/sparql.html> |
| Generated edition | [Turtle](https://raw.githubusercontent.com/saidfathalla/EVENTSKG-Dataset/refs/heads/master/EVENTSKG.ttl); other formats in [`serializations/`](serializations/) |
| Enriched edition | [Turtle](https://raw.githubusercontent.com/saidfathalla/EVENTSKG-Dataset/refs/heads/master/EVENTSKG-enriched.ttl); other formats in [`serializations/`](serializations/) |
| Dataset description (VoID) | [VoID.ttl](https://raw.githubusercontent.com/saidfathalla/EVENTSKG-Dataset/refs/heads/master/VoID.ttl) |
| Curated record, mapping, shapes | [EVENTSKG_data.csv](data/EVENTSKG_data.csv), [eventskg.sssom.tsv](data/eventskg.sssom.tsv), [shapes/](shapes/) |
| Release 2.1 | [`archive/R2.1/`](archive/R2.1/) |

Short persistent addresses are being registered at w3id.org: `w3id.org/EVENTSKG-Dataset/` (documentation), `/sparql`, `/ttl`, `/nt`, `/jsonld`, `/rdf`, `/n3`, `/enriched`, `/enriched/nt` …, `/void`, `/data`, `/mapping`, `/shapes` and `/R2.1`.

To get the data with content negotiation:

```bash
curl -L -H "Accept: text/turtle" http://w3id.org/EVENTSKG-Dataset/ekg
```

---

## Example SPARQL Queries

All queries run in the [SPARQL explorer](https://saidfathalla.github.io/EVENTSKG-Dataset/docs/sparql.html) (which predeclares the prefixes) or in any SPARQL engine loaded with the dataset.

### Query 1: The top 5 countries that hosted the most Security and Privacy events since 2009
```sparql
PREFIX seo: <https://w3id.org/seo#>
PREFIX conference-ontology: <https://w3id.org/scholarlydata/ontology/conference-ontology.owl#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?country (COUNT(?e) AS ?numOfEvents)
WHERE {
  ?e seo:heldInCountry ?country ;
     seo:ResearchField seo:SecurityAndPrivacy ;
     conference-ontology:startDate ?sd .
  FILTER (?sd >= "2009-01-01T00:00:00+00:00"^^xsd:dateTime)
}
GROUP BY ?country
ORDER BY DESC(?numOfEvents)
LIMIT 5
```

### Query 2: Comparing the popularity of the CS communities (submissions since 2009)
```sparql
PREFIX seo: <https://w3id.org/seo#>
PREFIX conference-ontology: <https://w3id.org/scholarlydata/ontology/conference-ontology.owl#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?field (SUM(?sub) AS ?numOfSubmissions)
WHERE {
  ?e seo:ResearchField ?field ;
     conference-ontology:startDate ?d ;
     seo:submittedPapers ?sub .
  FILTER (?d >= "2009-01-01T00:00:00+00:00"^^xsd:dateTime)
}
GROUP BY ?field
ORDER BY DESC(?numOfSubmissions)
```

### Query 3: Attendance mode of the editions held from 2019 to 2023 (new in 3.0)
```sparql
PREFIX schema: <http://schema.org/>
PREFIX conference-ontology: <https://w3id.org/scholarlydata/ontology/conference-ontology.owl#>

SELECT ?year ?mode (COUNT(?e) AS ?events)
WHERE {
  ?e conference-ontology:startDate ?sd .
  BIND (YEAR(?sd) AS ?year)
  FILTER (?year >= 2019 && ?year <= 2023)
  OPTIONAL { ?e schema:eventAttendanceMode ?m . }
  BIND (COALESCE(STRAFTER(STR(?m), "schema.org/"), "not recorded") AS ?mode)
}
GROUP BY ?year ?mode
ORDER BY ?year ?mode
```

### Query 4: Host cities with their names and Wikidata items (enriched edition)
```sparql
PREFIX seo: <https://w3id.org/seo#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX owl: <http://www.w3.org/2002/07/owl#>
PREFIX conference-ontology: <https://w3id.org/scholarlydata/ontology/conference-ontology.owl#>

SELECT ?acronym ?cityName ?wikidata
WHERE {
  ?e conference-ontology:acronym ?acronym ;
     seo:city ?city .
  ?city rdfs:label ?cityName ;
        owl:sameAs ?wikidata .
}
LIMIT 20
```

---

## Contribution & Support

If you encounter any issues, find bugs, or wish to request new features, please submit an issue via our Issue Tracker:

* 🐛 [Report a Bug](https://github.com/saidfathalla/EVENTSKG-Dataset/issues/new?template=bug_report.md)
* 💡 [Request a Feature](https://github.com/saidfathalla/EVENTSKG-Dataset/issues/new?template=feature_request.md)

Corrections to the data are best made in `data/EVENTSKG_data.csv` (see [Curating](#curating)). For questions, feedback, or collaboration inquiries, feel free to create an issue.

## License

This dataset and its associated metadata are licensed under the Creative Commons Attribution 4.0 International License (CC BY 4.0).

You are free to share (copy and redistribute the material in any medium or format) and adapt (remix, transform, and build upon the material for any purpose, even commercially) under the condition that you give appropriate credit to the authors and provide a link to the license.

For the full legal text, see the LICENSE file in this repository or visit https://creativecommons.org/licenses/by/4.0/.

## Citation

If you use EVENTSKG in your research or project, please cite the dataset:

```bibtex
@dataset{fathalla2026eventskg_data,
  author    = {Fathalla, Said and Mohamed, Heba and Auer, S{\"o}ren},
  title     = "{EVENTSKG} 3.0: Reproducible and Interoperable Linked Data on Top-Ranked Computer Science Events",
  version   = {3.0},
  publisher = {Zenodo},
  year      = {2026},
  doi       = {10.5281/zenodo.23806362},
  url       = {https://doi.org/10.5281/zenodo.23806362}
}
```

and the paper describing release 2:

```bibtex
@inproceedings{fathalla2019eventskg,
  author    = {Fathalla, Said and Lange, Christoph and Auer, S{\"o}ren},
  title     = "{EVENTSKG}: A 5-Star Dataset of Top-Ranked Events in Eight Computer Science Communities",
  booktitle = {The Semantic Web -- 16th International Conference, ESWC 2019, Portoro{\v z}, Slovenia, Proceedings},
  series    = {Lecture Notes in Computer Science},
  volume    = {11503},
  pages     = {427--442},
  publisher = {Springer},
  year      = {2019},
  doi       = {10.1007/978-3-030-21348-0_28}
}
```

The paper describing release 3.0, *EVENTSKG 3.0: Reproducible and Interoperable Linked Data on Top-Ranked Computer Science Events* (Fathalla and Mohamed), is under review at the Semantic Web Journal.
