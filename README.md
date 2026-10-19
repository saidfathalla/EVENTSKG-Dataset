# EVENTSKG: A 5-Star Dataset of Top-Ranked Events in Eight Computer Science Communities

[![License: CC BY 4.0](https://img.shields.io/badge/License-CC%20BY%204.0-blue.svg)](https://creativecommons.org/licenses/by/4.0/)
[![FAIR Principles](https://img.shields.io/badge/FAIR-Data%20Findable%20Accessible%20Interoperable%20Reusable-blueviolet.svg)](https://www.go-fair.org/fair-principles/)
[![Format: RDF/Turtle/JSON-LD](https://img.shields.io/badge/Format-RDF%20%7C%20Turtle%20%7C%20JSON--LD-orange.svg)](http://kddste.sda.tech/EVENTSKG-Dataset/)
[![5-Star Open Data](https://img.shields.io/badge/Open%20Data-5%E2%9B%85-gold.svg)](https://5stardata.info/en/)

<!-- Academic & Citation -->
[![DOI: 10.1007/978-3-030-21348-0_28](https://img.shields.io/badge/DOI-10.1007%2F978--3--030--21348--0__28-blue.svg)](https://doi.org/10.1007/978-3-030-21348-0_28)
[![Paper: ESWC 2019](https://img.shields.io/badge/Paper-ESWC%202019-red.svg)](https://link.springer.com/chapter/10.1007/978-3-030-21348-0_28)

<!-- Repository Maintenance & Health -->
[![GitHub Last Commit](https://img.shields.io/github/last-commit/saidfathalla/EVENTSKG-Dataset.svg)](https://github.com/saidfathalla/EVENTSKG-Dataset/commits/master)
[![Maintenance API](https://img.shields.io/badge/API-EVENTSKG__API-informational.svg)](https://github.com/saidfathalla/EVENTSKG_API)

EVENTSKG (formerly EVENTS) is a 5-star Linked Open Dataset representing comprehensive semantic descriptions of scientific events. It covers historical metadata about top-ranked event series, individual editions, publications, submissions, acceptance rates, start/end dates, locations, and official homepages across prestigious Computer Science conferences.

---

## 🚀 Key Features & What's New in Release 2 (R2)

We are pleased to present the second release (**R2**) of EVENTSKG as a Linked Open Dataset:

* **Expanded Community Coverage**: Covers **73 top-ranked event series** (representing **1,951 events** established over the last five decades with **29,255 triples**) across **8 Computer Science communities**:
  1. Artificial Intelligence (AI)
  2. Software and its Engineering (SE)
  3. World Wide Web (WEB)
  4. Security and Privacy (SEC)
  5. Information Systems (IS)
  6. Computer Systems Organization (CSO)
  7. Human-Centered Computing (HCC) *(New in R2)*
  8. Theory of Computation (TOC) *(New in R2)*
* **Reference Ontology**: Full alignment with the updated **Scientific Events Ontology (SEO)** (`https://w3id.org/seo#`).
* **Unified Ranking**: Integrates rankings from CORE, QUALIS, ERA, and GGS through the Scientific Events Ranking (SER) weighted framework.
* **Linked Data (5-Star LOD)**: Entities are linked to DBpedia (for countries/cities) and SEO terms, featuring dereferenceable IRIs under persistent URLs (`w3id.org`).
* **Multi-Format Availability**: Publicly available in Turtle, JSON-LD, RDF/XML, and CSV formats.
* **SPARQL Endpoint & Maintenance API**: Queryable via a Virtuoso SPARQL endpoint and coupled with a Java API for easy data maintenance.
---
## Automation & Quality Control

This repository uses **GitHub Actions** workflows to automatically maintain data quality, syntax correctness, and link stability:

* **RDF Syntax Validation (`validate-rdf.yml`)**: On every push and pull request, RDF files (`.ttl`, `.rdf`) are automatically parsed and validated using `RDFLib` to catch syntax or formatting errors.
* **Link Checking (`link-check.yml`)**: A weekly automated check verifies that all external links, dataset dumps, SPARQL endpoints, and PURL IRIs remain online and accessible.
* **Pages Deployment (`pages-build-deployment.yml`)**: Automatically deploys the latest version of the repository documentation to GitHub Pages.

---

## Dataset Access & Dumps

The complete dataset dumps can be directly downloaded in your preferred format:

| Format | Direct Download Link |
| :--- | :--- |
| **RDF / Turtle (`.ttl`)** | [Download EVENTKG_R2.ttl](EVENTSKG.ttl) |
| **JSON-LD (`.json`)** | [Download EVENTKG_R2.json](docs/EVENTKG_R2.json) |
| **RDF / XML (`.rdf`)** | [Download EVENTKG_R2.rdf](docs/EVENTKG_R2.rdf) |

---

## Linked Data Resources & Links

Explore and validate the dataset using the following linked data endpoints and documentation:

* **Persistent URI (PURL)**: [http://w3id.org/EVENTSKG-Dataset/ekg#](http://w3id.org/EVENTSKG-Dataset/ekg#)
* **VoID Statistics**: [VoID Metadata Description (N-Triples)](VoID.nt)
* **Documentation**: [EVENTSKG R2 Documentation](https://saidfathalla.github.io/EVENTSKG-Dataset/docs/EVENTSKG_R2.html)
* **Datahub Entry**: [datahub.ckan.io/dataset/eventskg](https://datahub.ckan.io/dataset/eventskg)
---

## Example SPARQL Queries

You can query the dataset using standard SPARQL endpoints. Below are basic examples to help you get started:

### Query 1: Get  the top 5 countries that hosted the most Security and Privacy events in the past decade.
```sparql
PREFIX seo: [https://w3id.org/seo#](https://w3id.org/seo#)
PREFIX rdfs: [http://www.w3.org/2000/01/rdf-schema#](http://www.w3.org/2000/01/rdf-schema#)

SELECT ?country (count(?country) as ?numOfEvents)
WHERE{
  ?e seo:heldInCountry ?country.
  ?e seo:field <https://w3id.org/seo#SecurityAndPrivacy>.
  ?e conference-ontology:startDate ?sd.
  FILTER(?sd >="2009-01-01T00:00:00.0000000+00:00"^^xsd:dateTime)
}
GROUP BY(?country)
ORDER BY DESC(?numOfEvents)
LIMIT 5
```

### Query 2: Comparing the popularity of the CS communities.
```sparql
SELECT ?field (SUM(?sub) AS ?numOfSubmissions)
WHERE{
  ?e seo:field ?field.
  ?e conference-ontology:startDate ?d.
  FILTER (?d >="2009-01-01T00:00:00.0000000+00:00"^^xsd:dateTime)
  ?e seo:submittedPapers ?sub.
}
ORDER BY DESC(?numOfSubmissions)
```



## Contribution & Support

If you encounter any issues, find bugs, or wish to request new features, please submit an issue via our Issue Tracker:

* 🐛 [Report a Bug](https://github.com/saidfathalla/EVENTSKG-Dataset/issues/new?template=bug_report.md)
* 💡 [Request a Feature](https://github.com/saidfathalla/EVENTSKG-Dataset/issues/new?template=feature_request.md)

For questions, feedback, or collaboration inquiries, feel free to create an issue.

## License
This dataset and its associated metadata are licensed under the Creative Commons Attribution 4.0 International License (CC BY 4.0).

You are free to share (copy and redistribute the material in any medium or format) and adapt (remix, transform, and build upon the material for any purpose, even commercially) under the condition that you give appropriate credit to the authors and provide a link to the license.

For the full legal text, see the LICENSE file in this repository or visit https://creativecommons.org/licenses/by/4.0/.

##  Citation
If you use EVENTSKG in your research or project, please cite the paper as follows:

```bibtex
@inproceedings{fathalla2020eventskg,
  title     = {EVENTSKG: A Knowledge Graph of Scientific Events},
  author    = {Fathalla, Said and Vahdati, Sahar and Lange, Christoph and Auer, S{\"o}ren},
  booktitle = {International Conference on Web Engineering (ICWE)},
  pages     = {315--323},
  year      = {2020},
  publisher = {Springer},
  doi       = {10.1007/978-3-030-21348-0_28}
}
```
