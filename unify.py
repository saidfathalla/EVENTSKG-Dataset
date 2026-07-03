import re
import rdflib
from datetime import datetime
from rdflib import URIRef, Literal, Namespace
from rdflib.namespace import RDF, OWL, RDFS, XSD
from rdflib.term import bind

# Define a custom date-time parser to clean trailing spaces and truncate nanoseconds to microseconds
def parse_lax_datetime(lexical):
    # 1. Strip leading/trailing whitespaces
    cleaned = lexical.strip()
    # 2. Truncate 7+ digit fractional seconds down to 6 digits (e.g., .0000000 -> .000000)
    cleaned = re.sub(r'\.(\d{6})\d+', r'.\1', cleaned)
    return datetime.fromisoformat(cleaned)

# Bind the custom converter to XSD.dateTime before initializing the graph
bind(XSD.dateTime, datetime, constructor=parse_lax_datetime)

def refine_eventskg_dataset(file_path, output_path):
    print(f"[*] Initializing Graph and parsing {file_path}...")
    g = rdflib.Graph()
    g.parse(file_path, format="turtle")
    
    # Namespaces
    SEO = Namespace("http://purl.org/seo/")
    CONF = Namespace("https://w3id.org/scholarlydata/ontology/conference-ontology.owl#")
    EVENTSKG = Namespace("http://w3id.org/EVENTSKG-Dataset/ekg#")
    
    print("[*] Consolidating and deduplicating string casing variations...")
    # 1. Unify acceptedpaper -> acceptedPapers
    for s, o in g.subject_objects(SEO.acceptedpaper):
        g.add((s, SEO.acceptedPapers, o))
        g.remove((s, SEO.acceptedpaper, o))
        
    # 2. Unify submittedpaper -> submittedPapers
    for s, o in g.subject_objects(SEO.submittedpaper):
        g.add((s, SEO.submittedPapers, o))
        g.remove((s, SEO.submittedpaper, o))
        
    print("[*] Executing deep data cleaning for timeline and spatial bugs...")
    # 3. Fix CHI2007 Temporal contradiction (End Date was accidentally set to 2003)
    chi2007 = EVENTSKG.CHI2007
    g.remove((chi2007, CONF.endDate, None))
    g.add((chi2007, CONF.endDate, Literal("2007-05-03T00:00:00.000000Z", datatype=XSD.dateTime)))
    
    # 4. Fix UIST2007 Country discrepancy (Newport, RI is in the USA, not England)
    uist2007 = EVENTSKG.UIST2007
    g.remove((uist2007, SEO.heldInCountry, None))
    g.add((uist2007, SEO.heldInCountry, URIRef("http://dbpedia.org/resource/United_States")))
    
    # 5. Fix UIST2009 Country discrepancy (Victoria, BC is in Canada, not USA)
    uist2009 = EVENTSKG.UIST2009
    g.remove((uist2009, SEO.heldInCountry, None))
    g.add((uist2009, SEO.heldInCountry, URIRef("http://dbpedia.org/resource/Canada")))
    
    print("[*] Re-typing properties and embedding semantics...")
    # 6. Change core statistical properties from Annotation to Datatype Property
    for prop in [SEO.acceptedPapers, SEO.submittedPapers, SEO.acceptanceRate]:
        g.remove((prop, RDF.type, OWL.AnnotationProperty))
        g.add((prop, RDF.type, OWL.DatatypeProperty))
        
    # 7. Change spatial & alignment fields from Annotation to Object Property
    for prop in [SEO.city, SEO.heldInCountry, SEO.belongsToSeries, SEO.field, SEO.state]:
        g.remove((prop, RDF.type, OWL.AnnotationProperty))
        g.add((prop, RDF.type, OWL.ObjectProperty))
        
    print("[*] Exporting updated clean knowledge graph file...")
    # Clean up empty dangling definitions of old variant keys
    g.remove((SEO.acceptedpaper, None, None))
    g.remove((SEO.submittedpaper, None, None))
    
    # Save output
    g.serialize(output_path, format="turtle")
    print(f"[✓] Completed! Refactored file saved as: {output_path}")

if __name__ == "__main__":
    refine_eventskg_dataset("EVENTKG_R2.ttl", "EVENTKG_R2_Updated.ttl")
