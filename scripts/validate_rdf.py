#!/usr/bin/env python3
"""Validation of the published RDF files of EVENTSKG (run by GitHub Actions).

1. Syntax: every RDF file in the repository (Turtle, N-Triples, JSON-LD,
   RDF/XML, N3) must parse.
2. Consistency: the five serializations of each edition must contain the
   same number of triples.
3. Constraints: both editions must conform to the SHACL shapes.

Exits with status 1 if any check fails.
"""
import glob, os, sys
from rdflib import Graph

FORMATS = {".ttl": "turtle", ".nt": "nt", ".jsonld": "json-ld", ".rdf": "xml", ".n3": "n3"}
SKIP_DIRS = (".git", "node_modules", ".venv", "venv")
EDITIONS = {  # edition -> its five serializations
    "generated": ["EVENTSKG.ttl"] + [f"serializations/EVENTSKG.{e}" for e in ("nt", "jsonld", "rdf", "n3")],
    "enriched": ["EVENTSKG-enriched.ttl"] + [f"serializations/EVENTSKG-enriched.{e}" for e in ("nt", "jsonld", "rdf", "n3")],
}
SHAPES = "shapes/shapes.ttl"

errors = []
sizes = {}

# 1. syntax
files = sorted(f for ext in FORMATS for f in glob.glob(f"**/*{ext}", recursive=True)
               if not any(p in SKIP_DIRS for p in f.split(os.sep)))
print(f"== Syntax: {len(files)} RDF files")
for f in files:
    try:
        g = Graph().parse(f, format=FORMATS[os.path.splitext(f)[1]])
        sizes[f] = len(g)
        print(f"  ok    {f} ({len(g):,} triples)")
    except Exception as e:  # noqa: BLE001
        errors.append(f"syntax error in {f}: {e}")
        print(f"  FAIL  {f}: {e}")

# 2. same number of triples in all serializations of an edition
print("== Consistency of the serializations")
for ed, fs in EDITIONS.items():
    missing = [f for f in fs if not os.path.exists(f)]
    if missing:
        errors.append(f"{ed} edition: missing {', '.join(missing)}")
        print(f"  FAIL  {ed}: missing {', '.join(missing)}")
        continue
    counts = {f: sizes.get(f) for f in fs}
    if len(set(counts.values())) == 1:
        print(f"  ok    {ed}: {next(iter(counts.values())):,} triples in all five serializations")
    else:
        errors.append(f"{ed} edition: serializations differ {counts}")
        print(f"  FAIL  {ed}: {counts}")

# 3. SHACL
print("== SHACL validation")
if os.path.exists(SHAPES):
    from pyshacl import validate
    shapes = Graph().parse(SHAPES, format="turtle")
    for ed, fs in EDITIONS.items():
        if not os.path.exists(fs[0]):
            continue
        conforms, _, text = validate(Graph().parse(fs[0], format="turtle"), shacl_graph=shapes,
                                     advanced=True, allow_warnings=True)
        if conforms:
            print(f"  ok    {ed} edition conforms to {SHAPES}")
        else:
            errors.append(f"{ed} edition violates the SHACL shapes")
            print(f"  FAIL  {ed} edition:\n{text[:4000]}")
else:
    errors.append(f"{SHAPES} not found")
    print(f"  FAIL  {SHAPES} not found")

print()
if errors:
    print(f"{len(errors)} problem(s):")
    for e in errors:
        print("  -", e)
    sys.exit(1)
print("All checks passed.")
