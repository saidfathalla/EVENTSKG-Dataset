# EVENTSKG: A Knowledge Graph of Scientific Events

[![License: CC BY 4.0](https://img.shields.io/badge/License-CC%20BY%204.0-blue.svg)](https://creativecommons.org/licenses/by/4.0/)
[![Ontology: SEO](https://img.shields.io/badge/Ontology-SEO-green.svg)](http://sda.tech/SEOontology/Documentation/SEO.html)
[![Issue Tracker](https://img.shields.io/badge/Issues-Open-brightgreen.svg)](https://github.com/saidfathalla/EVENTSKG-Dataset/issues)

**EVENTSKG** (formerly *EVENTS*) is a comprehensive Linked Dataset representing historical data about top-tier scientific events. It encompasses detailed information regarding event series, individual editions, publications, submissions, key dates (start and end dates), locations, and official homepages across prestigious Computer Science conferences.

---

## What's New in Release 2 (R2)

We are pleased to announce the second release (**R2**) of EVENTSKG! This version delivers significantly richer, cleaner, and fully harmonized semantic data.

Key updates include:
* **Reference Ontology**: Full alignment with the updated [Scientific Events Ontology (SEO)](http://sda.tech/SEOontology/Documentation/SEO.html) for robust event metadata representation.
* **Scope**: Metadata coverage for **73 top-tier event series** spanning six distinct Computer Science research communities.
* **Multi-Format Availability**: Data is available in multiple serialization formats, including Turtle, JSON-LD, RDF/XML, and CSV.

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

### Query 1: Get all event editions with their location and start/end dates
```sparql
PREFIX seo: [http://sda.tech/SEOontology/SEO/](http://sda.tech/SEOontology/SEO/)
PREFIX rdfs: [http://www.w3.org/2000/01/rdf-schema#](http://www.w3.org/2000/01/rdf-schema#)

SELECT ?eventLabel ?location ?startDate ?endDate WHERE {
  ?event a seo:Event ;
         rdfs:label ?eventLabel ;
         seo:hasLocation ?location ;
         seo:hasStartDate ?startDate ;
         seo:hasEndDate ?endDate .
}
LIMIT 50
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
