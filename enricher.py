import argparse
import csv
import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from rdflib import Graph, URIRef, Literal, Namespace
from rdflib.namespace import RDF, RDFS, XSD, FOAF, OWL, DCTERMS
from SPARQLWrapper import SPARQLWrapper, JSON

# -----------------------------------------------------------------------------
# Namespaces
# -----------------------------------------------------------------------------
SEO = Namespace("https://w3id.org/seo#")
CONF = Namespace("https://w3id.org/scholarlydata/ontology/conference-ontology.owl#")
DBPEDIA_OWL = Namespace("http://dbpedia.org/ontology/")
GEO = Namespace("http://www.w3.org/2003/01/geo/wgs84_pos#")
SCHEMA = Namespace("http://schema.org/")
DCAT = Namespace("http://www.w3.org/ns/dcat#")

DBPEDIA_SPARQL_ENDPOINT = "https://dbpedia.org/sparql"
ROR_API_ENDPOINT = "https://api.ror.org/v2/organizations"

# Known entity disambiguations (redirecting historical/wrong URIs to canonical places)
ENTITY_DISAMBIGUATION_MAP = {
    "http://dbpedia.org/resource/County_of_Toulouse": "http://dbpedia.org/resource/Toulouse"
}

# Known canonical Wikidata overrides
CANONICAL_WIKIDATA_OVERRIDES = {
    "http://dbpedia.org/resource/France": "http://www.wikidata.org/entity/Q142",
    "http://dbpedia.org/resource/Toulouse": "http://www.wikidata.org/entity/Q7880",
    "http://dbpedia.org/resource/Germany": "http://www.wikidata.org/entity/Q183",
    "http://dbpedia.org/resource/Italy": "http://www.wikidata.org/entity/Q38",
    "http://dbpedia.org/resource/Spain": "http://www.wikidata.org/entity/Q29",
    "http://dbpedia.org/resource/United_States": "http://www.wikidata.org/entity/Q30",
    "http://dbpedia.org/resource/United_Kingdom": "http://www.wikidata.org/entity/Q145",
}

def query_dbpedia(sparql_query, max_retries=3):
    """Executes SPARQL queries against DBpedia endpoint with retry logic."""
    sparql = SPARQLWrapper(DBPEDIA_SPARQL_ENDPOINT)
    sparql.setReturnFormat(JSON)
    sparql.setQuery(sparql_query)
    
    for attempt in range(max_retries):
        try:
            results = sparql.query().convert()
            return results["results"]["bindings"]
        except Exception as e:
            if attempt == max_retries - 1:
                return []
            time.sleep(1)

def query_ror_api(org_name: str) -> tuple:
    """
    Queries the ROR REST API with a query string.
    Returns (ror_id, label) of the best matching organization, or (None, None).
    """
    clean_query = org_name.strip()
    if not clean_query:
        return None, None
        
    encoded_query = urllib.parse.quote(clean_query)
    url = f"{ROR_API_ENDPOINT}?query={encoded_query}"
    
    req = urllib.request.Request(url, headers={"User-Agent": "EVENTSKG-Enricher/2.0"})
    
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            if response.status == 200:
                data = json.loads(response.read().decode("utf-8"))
                items = data.get("items", [])
                if items:
                    top_match = items[0]
                    ror_id = top_match.get("id")
                    
                    # Extract primary display label
                    names = top_match.get("names", [])
                    pref_label = clean_query
                    for n in names:
                        if "ror_display" in n.get("types", []):
                            pref_label = n.get("value")
                            break
                    return ror_id, pref_label
    except Exception as e:
        pass
    
    return None, None

def count_individuals(graph: Graph) -> int:
    """Counts distinct subjects that have an rdf:type or are owl:NamedIndividual."""
    individuals = set()
    for s in graph.subjects(predicate=RDF.type, object=None):
        if isinstance(s, URIRef):
            individuals.add(s)
    return len(individuals)

def inject_fair_dataset_metadata(g: Graph, dataset_uri: str = "https://w3id.org/eventskg"):
    """Injects dataset-level metadata (DCAT/DCTERMS) to enhance FAIR compliance."""
    ds = URIRef(dataset_uri)
    g.add((ds, RDF.type, DCAT.Dataset))
    g.add((ds, RDF.type, SCHEMA.Dataset))
    g.add((ds, DCTERMS.title, Literal("EVENTSKG: Enriched Knowledge Graph of Scholarly Events", lang="en")))
    g.add((ds, DCTERMS.description, Literal("A FAIR-aligned knowledge graph of scholarly events enriched with DBpedia, Wikidata, and geospatial metadata.", lang="en")))
    g.add((ds, DCTERMS.license, URIRef("https://creativecommons.org/licenses/by/4.0/")))
    g.add((ds, DCTERMS.created, Literal(datetime.now().strftime("%Y-%m-%d"), datatype=XSD.date)))
    g.add((ds, OWL.versionInfo, Literal("2.0.0")))

def fix_entity_disambiguations(g: Graph, change_log: list) -> set:
    """Replaces known mis-mapped entity URIs with their canonical versions."""
    redirected = set()
    for old_uri_str, new_uri_str in ENTITY_DISAMBIGUATION_MAP.items():
        old_uri = URIRef(old_uri_str)
        new_uri = URIRef(new_uri_str)
        
        triples_to_replace = list(g.triples((None, None, old_uri)))
        for s, p, o in triples_to_replace:
            g.remove((s, p, o))
            g.add((s, p, new_uri))
            change_log.append([str(s), str(p), str(new_uri), f"Disambiguated from <{old_uri_str}>"])
            redirected.add(new_uri_str)
    return redirected

def enrich_series_and_organizations(g: Graph, change_log: list):
    """Enriches conference series topology and dynamically resolves string literals to ROR entities."""
    # 1. Series topology enrichment
    for s, p, o in list(g.triples((None, SEO.belongsToSeries, None))):
        if isinstance(o, URIRef):
            if (o, RDF.type, CONF.ConferenceSeries) not in g:
                g.add((o, RDF.type, CONF.ConferenceSeries))
                g.add((o, RDF.type, OWL.NamedIndividual))
                series_name = str(o).split("#")[-1].split("/")[-1]
                g.add((o, RDFS.label, Literal(f"{series_name} Conference Series", lang="en")))
                change_log.append([str(o), "rdf:type", "conference-ontology:ConferenceSeries", "URIRef"])

    # 2. Dynamic Sponsor / Publisher query to ROR API
    ror_cache = {}  # Local cache to prevent redundant API calls
    org_predicates = [SEO.hasPublisher, SEO.hasSponsor]
    
    for pred in org_predicates:
        for s, p, o in list(g.triples((None, pred, None))):
            if isinstance(o, Literal):
                clean_name = str(o).strip()
                if not clean_name:
                    continue

                # Query ROR API (or read from cache)
                if clean_name not in ror_cache:
                    time.sleep(0.1)  # Respect API rate limits
                    ror_id, ror_label = query_ror_api(clean_name)
                    ror_cache[clean_name] = (ror_id, ror_label)
                else:
                    ror_id, ror_label = ror_cache[clean_name]

                # Promote to ROR entity if matched
                if ror_id:
                    ror_uri = URIRef(ror_id)
                    display_label = ror_label if ror_label else clean_name
                    
                    g.remove((s, p, o))
                    g.add((s, p, ror_uri))
                    g.add((ror_uri, RDF.type, SCHEMA.Organization))
                    g.add((ror_uri, RDFS.label, Literal(display_label, lang="en")))
                    change_log.append([str(s), str(p), str(ror_uri), f"Resolved '{clean_name}' via ROR API"])

def write_csv_report(report_file: str, log_data: list):
    """Generates a structured CSV log file of all modifications."""
    with open(report_file, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Entity URI", "Predicate Added", "Value / Object", "Value Type"])
        for row in log_data:
            writer.writerow(row)

def write_html_report(report_file: str, log_data: list, stats: dict):
    """Generates a clean HTML report displaying the enrichment log."""
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>EVENTSKG FAIR Enrichment Report</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; margin: 30px; background-color: #f8f9fa; color: #212529; }}
        h1 {{ color: #0d6efd; margin-bottom: 5px; }}
        .subtitle {{ color: #6c757d; margin-bottom: 25px; }}
        .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 30px; }}
        .card {{ background: #ffffff; padding: 15px 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); border: 1px solid #dee2e6; }}
        .card .number {{ font-size: 1.6em; font-weight: bold; color: #0d6efd; }}
        .card .label {{ font-size: 0.85em; color: #6c757d; text-transform: uppercase; letter-spacing: 0.5px; }}
        table {{ width: 100%; border-collapse: collapse; background: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }}
        th {{ background-color: #0d6efd; color: white; text-align: left; padding: 12px 15px; font-weight: 600; }}
        td {{ padding: 10px 15px; border-bottom: 1px solid #e9ecef; font-size: 0.95em; word-break: break-word; }}
        tr:hover {{ background-color: #f1f3f5; }}
        a {{ color: #0d6efd; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
        .badge {{ background-color: #e7f5ff; color: #1864ab; padding: 3px 8px; border-radius: 4px; font-family: monospace; font-size: 0.85em; }}
    </style>
</head>
<body>
    <h1>EVENTSKG FAIR Enrichment Report</h1>
    <div class="subtitle">Input Dataset: <strong>{stats['input_file']}</strong> &bull; Output File: <strong>{stats['output_file']}</strong></div>

    <div class="stats-grid">
        <div class="card"><div class="number">{stats['entities_eval']:,}</div><div class="label">Target Entities</div></div>
        <div class="card"><div class="number">{stats['entities_added']:,}</div><div class="label">Entities Enriched</div></div>
        <div class="card"><div class="number">+{stats['triples_added']:,}</div><div class="label">Triples Added</div></div>
        <div class="card"><div class="number">{stats['triples_after']:,}</div><div class="label">Total Triples</div></div>
    </div>

    <h2>Detailed Modification Log</h2>
    <table>
        <thead>
            <tr>
                <th>Entity URI</th>
                <th>Predicate Added</th>
                <th>Value / Object</th>
                <th>Type</th>
            </tr>
        </thead>
        <tbody>
"""
    for entity, pred, val, vtype in log_data:
        val_display = f'<a href="{val}" target="_blank">{val}</a>' if val.startswith("http") else val
        html_content += f"""            <tr>
                <td><a href="{entity}" target="_blank"><span class="badge">{entity.split('/')[-1]}</span></a></td>
                <td><code>{pred}</code></td>
                <td>{val_display}</td>
                <td><small>{vtype}</small></td>
            </tr>\n"""

    html_content += """        </tbody>
    </table>
</body>
</html>"""

    with open(report_file, "w", encoding="utf-8") as f:
        f.write(html_content)

def enrich_dataset(input_file: str, output_file: str, report_format: str):
    print(f"[+] Loading graph from: {input_file} ...", end="", flush=True)
    g = Graph()
    
    try:
        fmt = "turtle" if input_file.endswith(".ttl") else "xml"
        g.parse(input_file, format=fmt)
        print(" Done.")
    except Exception as e:
        print(f"\n[Error] Failed to load dataset file '{input_file}': {e}")
        sys.exit(1)

    # Bind canonical namespaces explicitly
    g.bind("seo", SEO)
    g.bind("conference-ontology", CONF)
    g.bind("dbpedia-owl", DBPEDIA_OWL)
    g.bind("geo", GEO)
    g.bind("foaf", FOAF)
    g.bind("owl", OWL)
    g.bind("schema", SCHEMA)
    g.bind("dcat", DCAT)
    g.bind("dcterms", DCTERMS)

    # Pre-stats
    triples_before = len(g)
    individuals_before = count_individuals(g)

    # 1. Inject FAIR Dataset Metadata
    inject_fair_dataset_metadata(g)

    change_log = []

    # 2. Fix entity disambiguations
    fix_entity_disambiguations(g, change_log)

    # 3. Enrich series topology & dynamic ROR API organization promotion
    print("[+] Querying ROR API for sponsors and publishers...", end="", flush=True)
    enrich_series_and_organizations(g, change_log)
    print(" Done.")

    # 4. Target URIs linked via location/state predicates
    target_uris = set()
    target_predicates = [SEO.city, SEO.heldInCountry, DBPEDIA_OWL.state]
    for pred in target_predicates:
        for s, p, o in g.triples((None, pred, None)):
            if isinstance(o, URIRef):
                target_uris.add(o)

    enriched_entities = set()

    print(f"[+] Querying DBpedia & Wikidata for {len(target_uris)} target entities...", end="", flush=True)

    for idx, entity_uri in enumerate(target_uris, 1):
        uri_str = str(entity_uri)

        # A. Assign explicit schema:Place and schema:Country types
        if (entity_uri, RDF.type, SCHEMA.Place) not in g:
            g.add((entity_uri, RDF.type, SCHEMA.Place))
            change_log.append([uri_str, "rdf:type", "schema:Place", "URIRef"])
            enriched_entities.add(uri_str)

        is_country = any(p == SEO.heldInCountry for _, p, _ in g.triples((None, None, entity_uri)))
        if is_country and (entity_uri, RDF.type, SCHEMA.Country) not in g:
            g.add((entity_uri, RDF.type, SCHEMA.Country))
            change_log.append([uri_str, "rdf:type", "schema:Country", "URIRef"])
            enriched_entities.add(uri_str)

        # B. Guaranteed canonical Wikidata override execution
        if uri_str in CANONICAL_WIKIDATA_OVERRIDES:
            wikidata_uri = URIRef(CANONICAL_WIKIDATA_OVERRIDES[uri_str])
            if (entity_uri, OWL.sameAs, wikidata_uri) not in g:
                g.add((entity_uri, OWL.sameAs, wikidata_uri))
                change_log.append([uri_str, "owl:sameAs", str(wikidata_uri), "URIRef (Wikidata Override)"])
                enriched_entities.add(uri_str)

        # C. Query DBpedia for additional properties
        query = f"""
        PREFIX dbpedia-owl: <http://dbpedia.org/ontology/>
        PREFIX geo: <http://www.w3.org/2003/01/geo/wgs84_pos#>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX foaf: <http://xmlns.com/foaf/0.1/>
        PREFIX owl: <http://www.w3.org/2002/07/owl#>

        SELECT ?lat ?long ?abstract ?wikiLink ?sameAs ?countryCode WHERE {{
            OPTIONAL {{ <{uri_str}> geo:lat ?lat ; geo:long ?long . }}
            OPTIONAL {{ <{uri_str}> dbpedia-owl:abstract ?abstract . FILTER (lang(?abstract) = "en") }}
            OPTIONAL {{ <{uri_str}> foaf:isPrimaryTopicOf ?wikiLink . }}
            OPTIONAL {{ 
                <{uri_str}> owl:sameAs ?sameAs . 
                FILTER (STRSTARTS(STR(?sameAs), "http://www.wikidata.org/entity/Q"))
            }}
            OPTIONAL {{ <{uri_str}> dbpedia-owl:countryCode ?countryCode . }}
        }}
        LIMIT 10
        """

        bindings = query_dbpedia(query)

        for row in bindings:
            # Geo-coordinates
            if "lat" in row and "long" in row:
                lat_val = Literal(row["lat"]["value"], datatype=XSD.float)
                long_val = Literal(row["long"]["value"], datatype=XSD.float)
                
                if (entity_uri, GEO.lat, lat_val) not in g:
                    g.add((entity_uri, GEO.lat, lat_val))
                    g.add((entity_uri, GEO.long, long_val))
                    change_log.append([uri_str, "geo:lat", str(lat_val), "xsd:float"])
                    change_log.append([uri_str, "geo:long", str(long_val), "xsd:float"])
                    enriched_entities.add(uri_str)

            # Abstract
            if "abstract" in row:
                abs_str = row["abstract"]["value"]
                abs_val = Literal(abs_str, lang="en")
                if (entity_uri, DBPEDIA_OWL.abstract, abs_val) not in g:
                    g.add((entity_uri, DBPEDIA_OWL.abstract, abs_val))
                    change_log.append([uri_str, "dbpedia-owl:abstract", abs_str[:80] + "...", "rdf:langString (en)"])
                    enriched_entities.add(uri_str)

            # Wikipedia Link
            if "wikiLink" in row:
                wiki_uri = URIRef(row["wikiLink"]["value"])
                if (entity_uri, FOAF.isPrimaryTopicOf, wiki_uri) not in g:
                    g.add((entity_uri, FOAF.isPrimaryTopicOf, wiki_uri))
                    change_log.append([uri_str, "foaf:isPrimaryTopicOf", str(wiki_uri), "URIRef"])
                    enriched_entities.add(uri_str)

            # Wikidata sameAs
            if "sameAs" in row and uri_str not in CANONICAL_WIKIDATA_OVERRIDES:
                wikidata_uri = URIRef(row["sameAs"]["value"])
                if (entity_uri, OWL.sameAs, wikidata_uri) not in g:
                    g.add((entity_uri, OWL.sameAs, wikidata_uri))
                    change_log.append([uri_str, "owl:sameAs", str(wikidata_uri), "URIRef (Wikidata)"])
                    enriched_entities.add(uri_str)

            # ISO Country Code
            if "countryCode" in row:
                cc_val = Literal(row["countryCode"]["value"])
                if (entity_uri, SCHEMA.addressCountry, cc_val) not in g:
                    g.add((entity_uri, SCHEMA.addressCountry, cc_val))
                    change_log.append([uri_str, "schema:addressCountry", str(cc_val), "xsd:string"])
                    enriched_entities.add(uri_str)

        time.sleep(0.12)  # Endpoint throttling

    print(" Done.\n")

    # Post-stats
    triples_after = len(g)
    individuals_after = count_individuals(g)

    # Determine report filename
    base_name = output_file.rsplit(".", 1)[0]
    report_file = f"{base_name}_changes.{report_format}"

    # Write report file
    stats_summary = {
        "input_file": input_file,
        "output_file": output_file,
        "entities_eval": len(target_uris),
        "entities_added": len(enriched_entities),
        "triples_added": triples_after - triples_before,
        "triples_after": triples_after
    }

    if report_format == "csv":
        write_csv_report(report_file, change_log)
    else:
        write_html_report(report_file, change_log, stats_summary)

    # Save Enriched Graph
    out_fmt = "turtle" if output_file.endswith(".ttl") else "xml"
    g.serialize(destination=output_file, format=out_fmt)

    # Print Summary Statistics
    print("="*65)
    print("                FAIR ENRICHMENT SUMMARY")
    print("="*65)
    print(f"  Input Dataset:              {input_file}")
    print(f"  Output Graph:               {output_file}")
    print(f"  Modification Report:        {report_file}")
    print("-" * 65)
    print(f"  Entities Evaluated:         {len(target_uris):,}")
    print(f"  Entities Enriched:          {len(enriched_entities):,}")
    print(f"  Entities Unchanged:         {len(target_uris) - len(enriched_entities):,}")
    print("-" * 65)
    print(f"  Total Triples BEFORE:       {triples_before:,}")
    print(f"  Total Triples AFTER:        {triples_after:,}  (+{triples_after - triples_before:,})")
    print("-" * 65)
    print(f"  Total Individuals BEFORE:   {individuals_before:,}")
    print(f"  Total Individuals AFTER:    {individuals_after:,}  (+{individuals_after - individuals_before:,})")
    print("="*65)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Enrich an RDF dataset from DBpedia, Wikidata & ROR API with FAIR metadata."
    )
    parser.add_argument("dataset", type=str, help="Path to input RDF file (e.g., EVENTSKG.ttl)")
    parser.add_argument("-o", "--output", type=str, default=None, help="Output RDF file path")
    parser.add_argument(
        "-f", "--format", 
        type=str, 
        choices=["html", "csv"], 
        default="html", 
        help="Format for human-readable changes log (default: html)"
    )

    args = parser.parse_args()

    input_path = args.dataset
    if args.output:
        output_path = args.output
    else:
        if "." in input_path:
            base, ext = input_path.rsplit(".", 1)
            output_path = f"{base}_Enriched.{ext}"
        else:
            output_path = f"{input_path}_Enriched.ttl"

    enrich_dataset(input_path, output_path, args.format)