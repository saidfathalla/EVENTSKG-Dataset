#!/usr/bin/env python3
"""
csv2rdf.py - convert a CSV data file to RDF with an SSSOM mapping file (and an optional places file).

    python3 csv2rdf.py DATA.csv MAPPING.sssom.tsv [--places PLACES.csv] [-o OUT.ttl ...]

    python3 csv2rdf.py data/EVENTSKG_data.csv eventskg.sssom.tsv --places data/dbpedia_places.csv -o EVENTSKG.ttl

Nothing here is specific to one dataset: what each column becomes is written in the mapping file.

Mapping file (SSSOM)
  MAPPING.sssom.tsv  the mapping table, one row per (data field -> RDF property)
  MAPPING.sssom.yml  its metadata (curie_map = prefixes, mapping_set_id, license ...); a "#" metadata block at
                     the top of the TSV is read too.
  Standard columns: subject_id (the data field, e.g. eventskg-data:start_date; its local name is the CSV column),
  predicate_id (skos:exactMatch), object_id (the RDF property, e.g. conference-ontology:startDate),
  mapping_justification. Extension columns say how a cell is written:
    resource    IRI pattern of the resource the value belongs to, e.g. eventskg:{event_id}. Several patterns
                separated by " || ": the first one whose columns are all filled is used.
    datatype    xsd datatype of the literal (xsd:integer, xsd:decimal, xsd:dateTime ...). A date YYYY-MM-DD
                given for xsd:dateTime is written as YYYY-MM-DDT00:00:00+00:00.
    iri_pattern the value becomes an IRI, e.g. eventskg:{value}
    value_map   allowed values and their IRIs: "Conference=co:Conference owl:NamedIndividual|Workshop=..."
                (several IRIs separated by spaces; nothing after "=" writes nothing; "*" = any value)
    lookup      the value is a place name; its IRI comes from the places file rows of this type
                (city / state / country). The places file's other columns (e.g. state, country) are matched
                with the data columns of the same name.
    separator   several values in one cell, e.g. |
    check       rules separated by ";":  required | unique | <= other_column | with other_column | range 0..1 |
                = column_a / column_b   (computed when the cell is empty, checked when it is filled)
  A column that is mapped without a separator must have one value per resource (checked across rows).

Places file: CSV with the columns place_type, name, (any context columns, e.g. state, country), iri.

Output: the RDF (-o, repeatable; format from the extension .ttl .nt .jsonld .rdf; default DATA.ttl) and
report.csv with every problem (errors first, with the CSV line). A bad cell is skipped, the rest of the row
is converted; the exit code is 1 when there are errors.
Dataset description
  dataset_* keys in the mapping metadata (.sssom.yml) describe the dataset itself and are written to the output:
  dataset_iri, dataset_type, dataset_title, dataset_label, dataset_description, dataset_creator, dataset_license,
  dataset_created, dataset_issued, dataset_version, dataset_previous_version, dataset_namespace_prefix,
  dataset_namespace, dataset_language (language of title/label/description). Declare them in
  extension_definitions, as SSSOM asks for non-standard keys.

Options
  --void FILE          also write the dataset description with VoID counts to FILE (repeatable: VoID.ttl, VoID.nt)
                       and add the counts to the output. Dataset resource: --dataset, else dataset_iri, else the
                       mapping's object_source.
  --dataset IRI        dataset resource (IRI or CURIE)
  --include FILE.ttl   extra triples merged into the output as they are (repeatable)
  --compare OLD.ttl    prints the counts of an earlier file next to the new ones
  --stats FILE.html    also writes a statistics page: classes, completeness of every mapped property,
                       resources per year, numeric summaries, most frequent IRI values (all from the mapping)
  --report FILE.csv    where problems are written (default report.csv next to the output). When there is no
                       error or warning, no report is written (and an old default report.csv is removed).

Requirements: Python 3.8+, pip install rdflib pyyaml
"""
import argparse, csv, datetime as dt, os, re, sys, unicodedata
from collections import Counter, defaultdict

try:
    import rdflib
    import yaml
except ImportError:
    sys.exit('Missing packages:  pip install rdflib pyyaml')
from rdflib import Literal, URIRef
from rdflib.namespace import DCTERMS, OWL, RDF, RDFS, VOID, XSD

PROV = rdflib.Namespace('http://www.w3.org/ns/prov#')
VANN = rdflib.Namespace('http://purl.org/vocab/vann/')


def new_graph():
    """Graph without rdflib's built-in prefixes (rdflib 7 binds schema: to https://schema.org/, which turns the
    http://schema.org/ terms of the mapping into schema1:)."""
    try:
        g = rdflib.Graph(bind_namespaces='none')
    except TypeError:                                 # rdflib < 6.2
        g = rdflib.Graph()
    for p, ns in (('rdf', RDF), ('rdfs', RDFS), ('owl', OWL), ('xsd', XSD), ('void', VOID), ('dcterms', DCTERMS),
                  ('prov', PROV), ('vann', VANN)):
        g.bind(p, ns, override=True, replace=True)   # used by the tool itself (types, VoID)
    return g

FORMATS = {'.ttl': 'turtle', '.nt': 'nt', '.jsonld': 'json-ld', '.json': 'json-ld', '.rdf': 'xml', '.xml': 'xml', '.n3': 'n3'}
DEFAULT_FORMATS = ['ttl', 'nt', 'jsonld', 'rdf', 'n3']          # written by default: every serialization


def base_name(path):
    """strip a known RDF extension: release/EVENTSKG.ttl -> release/EVENTSKG"""
    root, ext = os.path.splitext(path)
    return root if ext.lower() in FORMATS else path


def parse_formats(text):
    out = []
    for f in (text or ','.join(DEFAULT_FORMATS)).replace(' ', ',').split(','):
        f = f.strip().lower().lstrip('.')
        f = {'turtle': 'ttl', 'ntriples': 'nt', 'n-triples': 'nt', 'json-ld': 'jsonld', 'json': 'jsonld',
             'xml': 'rdf', 'rdfxml': 'rdf', 'rdf/xml': 'rdf'}.get(f, f)
        if not f:
            continue
        if '.' + f not in FORMATS:
            sys.exit(f'unknown format "{f}" in --formats (use {", ".join(DEFAULT_FORMATS)})')
        if f not in out:
            out.append(f)
    return out
problems = []                                     # (severity, line, column, resource, message)


def report(sev, line, col, res, msg):
    problems.append((sev, line, col, str(res), msg))


def norm(s):
    s = unicodedata.normalize('NFKD', str(s or '')).encode('ascii', 'ignore').decode()
    return ' '.join(s.lower().replace('_', ' ').split())


def number(v):
    try:
        return float(str(v).replace(',', ''))
    except ValueError:
        return None


# --------------------------------------------------------------------------------------------- SSSOM
class Mapping:
    def __init__(self, path):
        lines = open(path, encoding='utf-8').read().splitlines(True)
        head = [l[1:] for l in lines if l.startswith('#')]
        table = [l for l in lines if not l.startswith('#')]
        meta = yaml.safe_load(''.join(head)) or {}
        ext = os.path.splitext(path)[0].replace('.sssom', '') + '.sssom.yml'
        if os.path.exists(ext):                                        # external metadata file
            try:
                meta.update(yaml.safe_load(open(ext, encoding='utf-8')) or {})
            except yaml.YAMLError as e:
                sys.exit(f'{ext}: not valid YAML ({str(e).splitlines()[0]} ...); values containing ": " or ending '
                         f'with ":" must be quoted, e.g. dataset_iri: "eventskg:"')
        self.meta = meta
        self.prefixes = meta.get('curie_map') or {}
        rows = list(csv.DictReader(table, delimiter='\t'))
        need = {'subject_id', 'predicate_id', 'object_id', 'mapping_justification', 'resource'}
        if not rows or need - set(rows[0]):
            sys.exit(f'{path}: an SSSOM table with the columns {sorted(need)} is needed')
        self.rows = []
        for n, r in enumerate(rows, start=1):
            r = {k: (v or '').strip() for k, v in r.items() if k}
            if r.get('predicate_modifier', '').lower() == 'not' or not r['subject_id']:
                continue
            r['column'] = re.split(r'[:#/]', r['subject_id'])[-1]
            r['checks'] = [c.strip() for c in r.get('check', '').split(';') if c.strip()]
            r['n'] = n
            self.rows.append(r)

    def expand(self, s):
        s = str(s).strip()
        if re.match(r'^[A-Za-z][\w+.-]*://', s):
            return URIRef(s)
        if ':' in s:
            pfx, local = s.split(':', 1)
            if pfx in self.prefixes:
                return URIRef(self.prefixes[pfx] + local)
        raise ValueError(f'"{s}" has no known prefix')

    def resource(self, pattern, row):
        """First IRI pattern whose columns are all filled, or None."""
        for p in pattern.split('||'):
            cols = re.findall(r'{(\w+)}', p)
            if all(row.get(c, '') for c in cols):
                return self.expand(p.strip().format(**row))
        return None


def parse_map(text):
    out = {}
    for part in text.split('|'):
        if '=' in part:
            k, v = part.split('=', 1)
            out[k.strip()] = v.split()
    return out


# -------------------------------------------------------------------------------------------- places
class Places:
    """Places file: place_type, name, context columns (e.g. state, country), iri.
    Also accepted: the older layout city, state, country, iri ("DBpedia IRI"), where an empty city means a
    state row and an empty city and state means a country row. Comma, semicolon or tab separated."""

    def __init__(self, path):
        with open(path, encoding='utf-8-sig', newline='') as f:
            text = f.read()
        try:
            dialect = csv.Sniffer().sniff(text[:4096], delimiters=',;\t')
        except csv.Error:
            dialect = csv.excel
        rd = csv.reader(text.splitlines(), dialect)
        header = [re.sub(r'\W+', '_', h.strip().lower()).strip('_') for h in next(rd, [])]
        header = ['iri' if re.search(r'(^|_)(iri|uri|url)(_|$)', h) else 'city' if h.startswith('city') else h for h in header]
        rows = [dict(zip(header, [x.strip() for x in r])) for r in rd if any(x.strip() for x in r)]
        if {'city', 'state', 'country', 'iri'} <= set(header) and 'place_type' not in header:     # older layout
            conv = []
            for r in rows:
                t = 'city' if r.get('city') else 'state' if r.get('state') else 'country'
                conv.append(dict(place_type=t, name=r.get(t, ''), state=r.get('state', '') if t == 'city' else '',
                                 country=r.get('country', '') if t != 'country' else '', iri=r.get('iri', '')))
            rows, header = conv, ['place_type', 'name', 'state', 'country', 'iri']
        if not {'place_type', 'name', 'iri'} <= set(header):
            sys.exit(f'{path}: the header is {header}; expected place_type, name, (state, country ...), iri '
                     f'or city, state, country, iri')
        self.context = [c for c in header if c not in ('place_type', 'name', 'iri')]
        self.rows = defaultdict(list)                                  # (type, name) -> [(context dict, iri)]
        for r in rows:
            if r.get('place_type') and r.get('name') and r.get('iri'):
                self.rows[(r['place_type'].lower(), norm(r['name']))].append(
                    ({c: norm(r.get(c, '')) for c in self.context}, r['iri']))
        self.count = sum(len(v) for v in self.rows.values())

    def find(self, t, name, row, own_col):
        cands = self.rows.get((t, norm(name)), [])
        if not cands:
            return None
        want = {c: norm(row.get(c, '')) for c in self.context if c != own_col}
        best = []
        for ctx, iri in cands:
            if any(want[c] and ctx[c] and want[c] != ctx[c] for c in want):
                continue                                               # contradicts the row (other country ...)
            best.append((sum(1 for c in want if want[c] and want[c] == ctx[c]), iri))
        if not best:
            return None
        top = max(s for s, _ in best)
        iris = {iri for s, iri in best if s == top}
        return iris.pop() if len(iris) == 1 else None


# ------------------------------------------------------------------------------------------- convert
def convert(data_path, mp, places):
    g = new_graph()
    with open(data_path, encoding='utf-8-sig', newline='') as f:
        rd = csv.DictReader(f)
        header = [h.strip() for h in rd.fieldnames or []]
        rows = [({k.strip(): (v or '').strip() for k, v in r.items() if k}, n) for n, r in enumerate(rd, start=2)]
    used_cols = {m['column'] for m in mp.rows} | {c for m in mp.rows for c in re.findall(r'{(\w+)}', m['resource'])}
    missing = sorted(used_cols - set(header))
    if missing:
        sys.exit(f'{data_path}: the mapping uses columns that are not in the file: {missing}')
    unmapped = [h for h in header if h not in used_cols]
    one_value = defaultdict(lambda: defaultdict(list))   # (mapping row, subject) -> value -> lines
    unique = defaultdict(list)                           # (mapping row, subject) -> lines
    resources = defaultdict(set)
    for row, line in rows:
        if not any(row.values()):
            continue
        for m in mp.rows:
            col = m['column']
            subj = mp.resource(m['resource'], row)
            if subj is None:
                if 'required' in m['checks'] or 'unique' in m['checks']:
                    report('error', line, col, '', f'no resource IRI: the columns of "{m["resource"]}" are empty')
                continue
            resources[m['resource'].split('||')[0].strip()].add(subj)
            raw = row.get(col, '')
            for chk in m['checks']:
                if chk.startswith('=') and raw == '':
                    a, b = [x.strip() for x in chk[1:].split('/')]
                    na, nb = number(row.get(a, '')), number(row.get(b, ''))
                    if na is not None and nb:
                        raw = f'{na / nb:.4f}'
            if 'unique' in m['checks']:
                unique[(m['n'], subj)].append(line)
            if raw == '':
                if 'required' in m['checks']:
                    report('error', line, col, subj, 'required value is empty')
                continue
            if not check(m, raw, row, line, subj):
                continue
            values = [v.strip() for v in raw.split(m['separator'])] if m.get('separator') else [raw]
            for v in filter(None, values):
                for obj in make_objects(m, v, row, line, subj, mp, places):
                    g.add((subj, mp.expand(m['object_id']), obj))
                if not m.get('separator'):
                    one_value[(m['n'], subj)][v].append(line)
    for (n, subj), lines in unique.items():
        if len(lines) > 1:
            report('error', lines[1], next(m['column'] for m in mp.rows if m['n'] == n), subj,
                   f'the same resource is made by lines {lines[:5]}: give the rows different ids')
    for (n, subj), vals in one_value.items():
        if len(vals) > 1:
            col = next(m['column'] for m in mp.rows if m['n'] == n)
            detail = '; '.join(f'"{v}" (line{"s" if len(ls) > 1 else ""} {", ".join(map(str, ls[:3]))}{"..." if len(ls) > 3 else ""})'
                               for v, ls in sorted(vals.items(), key=lambda x: -len(x[1])))
            report('warning', min(min(ls) for ls in vals.values()), col, subj, f'{len(vals)} different values for one resource: {detail}')
    return g, len(rows), len(header), unmapped, resources


def check(m, raw, row, line, subj):
    col = m['column']
    for chk in m['checks']:
        if chk.startswith('<='):
            other = chk[2:].strip()
            ov = row.get(other, '')
            if ov:
                a, b = number(raw), number(ov)
                if (a > b) if a is not None and b is not None else raw > ov:
                    report('warning', line, col, subj, f'{raw} is greater than {other} ({ov})')
        elif chk.startswith('with '):
            other = chk[5:].strip()
            if not row.get(other, ''):
                report('warning', line, col, subj, f'"{raw}" is given but {other} is empty')
        elif chk.startswith('range'):
            lo, hi = [float(x) for x in chk[5:].split('..')]
            n = number(raw)
            if n is None or not lo <= n <= hi:
                report('error', line, col, subj, f'"{raw}" is not a number in {lo:g}..{hi:g}'); return False
        elif chk.startswith('='):
            a, b = [x.strip() for x in chk[1:].split('/')]
            na, nb, n = number(row.get(a, '')), number(row.get(b, '')), number(raw)
            if na is not None and nb and n is not None and abs(n - na / nb) > 0.006:
                report('warning', line, col, subj, f'{raw} differs from {a}/{b} = {na / nb:.4f}')
    return True


def make_objects(m, v, row, line, subj, mp, places):
    col = m['column']
    try:
        if m.get('value_map'):
            vm = parse_map(m['value_map'])
            targets = vm.get(v, vm.get('*'))
            if targets is None:
                report('error', line, col, subj, f'"{v}" is not one of: {", ".join(k for k in vm if k != "*")}'); return []
            return [mp.expand(t) for t in targets]
        if m.get('lookup'):
            if places is None:
                report('error', line, col, subj, 'this column needs the places file (--places)'); return []
            iri = places.find(m['lookup'], v, row, col)
            if iri is None:
                report('warning', line, col, subj, f'"{v}" is not in the places file (or matches several IRIs): '
                                                   f'no {m["object_id"]} triple written'); return []
            return [URIRef(iri)]
        if m.get('iri_pattern'):
            return [mp.expand(m['iri_pattern'].format(value=v, **row))]
        dtype = m.get('datatype')
        if not dtype:
            return [Literal(v)]
        if dtype == 'xsd:dateTime' and re.fullmatch(r'\d{4}-\d{2}-\d{2}', v):
            v += 'T00:00:00+00:00'
        lit = Literal(v, datatype=mp.expand(dtype))
        if getattr(lit, 'ill_typed', False) or (dtype == 'xsd:integer' and not re.fullmatch(r'-?\d+', v)):
            report('error', line, col, subj, f'"{v}" is not a valid {dtype}'); return []
        return [lit]
    except (ValueError, KeyError) as e:
        report('error', line, col, subj, str(e)); return []


# ---------------------------------------------------------------------------------------------- VoID
DATASET_FIELDS = {   # mapping metadata key -> (property, kind)
    'dataset_label': (RDFS.label, 'text'), 'dataset_title': (DCTERMS.title, 'text'),
    'dataset_description': (DCTERMS.description, 'text'), 'dataset_creator': (DCTERMS.creator, 'iri'),
    'dataset_license': (DCTERMS.license, 'iri'), 'dataset_created': (DCTERMS.created, 'date'),
    'dataset_issued': (DCTERMS.issued, 'date'), 'dataset_version': (OWL.versionInfo, 'plain'),
    'dataset_previous_version': (PROV.wasRevisionOf, 'iri'), 'dataset_namespace_prefix': (VANN.preferredNamespacePrefix, 'plain'),
    'dataset_namespace': (VANN.preferredNamespaceUri, 'plain'),
}


def dataset_iri(mp, override=None):
    target = override or mp.meta.get('dataset_iri') or mp.meta.get('object_source')
    if not target:
        return None
    try:
        return mp.expand(target)
    except ValueError as e:
        sys.exit(f'dataset IRI: {e}')


def add_dataset_description(g, mp, ds):
    """The dataset_* keys of the mapping metadata -> triples about the dataset resource."""
    m = mp.meta
    if not any(k in m for k in DATASET_FIELDS) and 'dataset_type' not in m:
        return False
    for t in str(m.get('dataset_type', 'void:Dataset')).split():
        g.add((ds, RDF.type, mp.expand(t)))
    lang = m.get('dataset_language')
    for key, (prop, kind) in DATASET_FIELDS.items():
        v = m.get(key)
        if v in (None, ''):
            continue
        v = ' '.join(str(v).split())
        g.remove((ds, prop, None))
        if kind == 'iri':
            g.add((ds, prop, mp.expand(v)))
        elif kind == 'date':
            g.add((ds, prop, Literal(v, datatype=XSD.date)))
        elif kind == 'text':
            g.add((ds, prop, Literal(v, lang=lang) if lang else Literal(v)))
        else:
            g.add((ds, prop, Literal(v)))
    return True


def add_void(g, ds, date, outputs):
    for p in (VOID.triples, VOID.entities, VOID.classes, VOID.properties, VOID.distinctSubjects, VOID.distinctObjects,
              VOID.feature, DCTERMS.modified):
        g.remove((ds, p, None))
    g.add((ds, RDF.type, VOID.Dataset))
    g.add((ds, DCTERMS.modified, Literal(date, datatype=XSD.date)))
    names = {'turtle': 'Turtle', 'nt': 'N-Triples', 'json-ld': 'JSON-LD', 'xml': 'RDF_XML', 'n3': 'N3'}
    for o in outputs:
        g.add((ds, VOID.feature, URIRef('http://www.w3.org/ns/formats/' + names[FORMATS[os.path.splitext(o)[1].lower()]])))
    stats = (VOID.entities, VOID.classes, VOID.properties, VOID.distinctSubjects, VOID.distinctObjects, VOID.triples)
    compute = {VOID.entities: lambda: len(set(g.subjects(RDF.type, None))), VOID.classes: lambda: len(set(g.objects(None, RDF.type))),
               VOID.properties: lambda: len(set(g.predicates())), VOID.distinctSubjects: lambda: len(set(g.subjects())),
               VOID.distinctObjects: lambda: len(set(g.objects())), VOID.triples: lambda: len(g)}
    for p in stats:                                   # placeholders first, so that the counts include these triples
        g.add((ds, p, Literal(0, datatype=XSD.integer)))
    for _ in range(5):                                # repeat until the numbers no longer change
        new = {p: compute[p]() for p in stats}
        old = {p: int(g.value(ds, p)) for p in stats}
        if new == old:
            break
        for p in stats:
            g.set((ds, p, Literal(new[p], datatype=XSD.integer)))

def write_rdf(g, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    fmt = FORMATS[os.path.splitext(path)[1].lower()]
    if fmt == 'json-ld':                              # context = only the prefixes that are used
        used = {str(x) for t in g for x in t if isinstance(x, URIRef)}
        used |= {str(x.datatype) for x in g.objects() if isinstance(x, Literal) and x.datatype}
        ctx = {p: str(ns) for p, ns in g.namespaces() if p and any(u.startswith(str(ns)) for u in used)}
        g.serialize(path, format='json-ld', context=ctx, indent=1, encoding='utf-8')
    else:
        g.serialize(path, format=fmt, encoding='utf-8')


# -------------------------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description='Convert a CSV data file to RDF with an SSSOM mapping file.')
    ap.add_argument('data', help='CSV data file')
    ap.add_argument('mapping', help='SSSOM mapping table (.sssom.tsv; metadata in .sssom.yml next to it)')
    ap.add_argument('--places', help='places CSV: place_type, name, context columns..., iri')
    ap.add_argument('-o', '--output', metavar='BASE',
                    help='output base name; BASE.ttl, BASE.nt, BASE.jsonld, BASE.rdf and BASE.n3 are written '
                         '(an extension given here is ignored; default: the data file name)')
    ap.add_argument('--formats', help=f'comma-separated subset of {",".join(DEFAULT_FORMATS)} (default: all)')
    ap.add_argument('--include', action='append', default=[], help='Turtle file merged into the output (repeatable)')
    ap.add_argument('--void', nargs='?', const='', metavar='BASE',
                    help='also write the dataset description with VoID counts to BASE.ttl, BASE.nt ... '
                         '(same formats as the output; BASE defaults to VoID next to the output)')
    ap.add_argument('--dataset', help='dataset IRI or CURIE for --void (default: object_source of the mapping)')
    ap.add_argument('--date', default=dt.date.today().isoformat(), help='dcterms:modified for --void (default today)')
    ap.add_argument('--report', help='problem report (default report.csv next to the output; written only if there are problems)')
    ap.add_argument('--stats', metavar='FILE.html', help='also write a statistics page (HTML) about the RDF output')
    ap.add_argument('--compare', help='earlier RDF file whose counts are printed next to the new ones')
    a = ap.parse_args()

    exts = parse_formats(a.formats)
    base = base_name(a.output) if a.output else os.path.splitext(a.data)[0]
    outputs = [f'{base}.{e}' for e in exts]
    if a.void is not None:
        vbase = base_name(a.void) if a.void else os.path.join(os.path.dirname(base), 'VoID')
        if os.path.abspath(vbase) == os.path.abspath(base):
            sys.exit('--void needs a base name different from the output (-o)')
        a.void = [f'{vbase}.{e}' for e in exts]
    mp = Mapping(a.mapping)
    places = Places(a.places) if a.places else None
    g, nrows, ncols, unmapped, resources = convert(a.data, mp, places)
    for path in a.include:
        inc = rdflib.Graph().parse(path)
        for t in inc:
            g.add(t)
        for p, ns in inc.namespaces():
            if p and not re.fullmatch(r'ns\d+', p):
                g.bind(p, ns, override=False)
    for p, ns in mp.prefixes.items():                  # only the prefixes that are used get written
        g.bind(p, ns, override=True, replace=True)
    void_files = []
    ds = dataset_iri(mp, a.dataset)
    described = add_dataset_description(g, mp, ds) if ds is not None else False
    if a.void:
        if ds is None:
            sys.exit('--void needs the dataset IRI: --dataset IRI, or dataset_iri / object_source in the mapping metadata')
        if (ds, DCTERMS.title, None) not in g or (ds, DCTERMS.license, None) not in g:
            report('warning', 0, '--void', ds, 'the dataset has no title or licence: add dataset_title and dataset_license '
                                                 'to the mapping metadata (.sssom.yml)')
        add_void(g, ds, a.date, outputs)
        void_files = a.void
        vg = new_graph()
        for p, ns in g.namespaces():
            vg.bind(p, ns)
        todo, seen = [ds], set()
        while todo:                                   # the dataset node and any blank nodes hanging from it
            s_ = todo.pop()
            if s_ in seen:
                continue
            seen.add(s_)
            for t in g.triples((s_, None, None)):
                vg.add(t)
                if isinstance(t[2], rdflib.BNode):
                    todo.append(t[2])
        for vf in void_files:
            write_rdf(vg, vf)
    elif a.dataset and not described:
        sys.exit('--dataset is used for the dataset description (dataset_* keys in the mapping metadata) or --void FILE')
    for o in outputs:
        write_rdf(g, o)
    sev = Counter(p[0] for p in problems)
    rep = a.report or os.path.join(os.path.dirname(os.path.abspath(outputs[0])), 'report.csv')
    if sev['error'] or sev['warning']:
        with open(rep, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f); w.writerow(['severity', 'line', 'column', 'resource', 'problem'])
            w.writerows(sorted(problems, key=lambda p: ({'error': 0, 'warning': 1}.get(p[0], 2), p[1])))
    else:
        rep = None
        default = os.path.join(os.path.dirname(os.path.abspath(outputs[0])), 'report.csv')
        if not a.report and os.path.exists(default):
            os.remove(default)                     # do not leave the report of an earlier run behind
    old = rdflib.Graph().parse(a.compare) if a.compare else None
    if a.stats:
        os.makedirs(os.path.dirname(os.path.abspath(a.stats)), exist_ok=True)
        write_stats(a.stats, g, mp, resources, ds, old, a, nrows, sev)
    print_summary(a, mp, g, old, nrows, ncols, unmapped, resources, places, outputs, rep, sev)
    sys.exit(1 if sev['error'] else 0)


# ------------------------------------------------------------------------------------------ terminal
def fmt(n):
    return f'{n:,}' if isinstance(n, int) else str(n)


def short_iri(mp, iri):
    iri = str(iri)
    for pfx, ns in sorted(mp.prefixes.items(), key=lambda x: -len(x[1])):
        if pfx and iri.startswith(ns):
            return f'{pfx}:{iri[len(ns):]}'
    return iri


def class_counts(g, mp):
    classes = [t for m in mp.rows if m['object_id'] == 'rdf:type' for ts in parse_map(m.get('value_map', '')).values() for t in ts]
    return {c: len(set(g.subjects(RDF.type, mp.expand(c)))) for c in dict.fromkeys(classes)}


def property_counts(g, mp):
    out = {}
    for pid in dict.fromkeys(m['object_id'] for m in mp.rows if m['object_id'] != 'rdf:type'):
        objs = list(g.objects(None, mp.expand(pid)))
        out[pid] = (len(objs), len(set(objs)) if objs and all(isinstance(o, URIRef) for o in objs) else None)
    return out


def counts(g, mp):                               # kept for scripts that import it
    out = {'triples': len(g), 'subjects': len(set(g.subjects()))}
    out.update({f'instances of {k}': v for k, v in class_counts(g, mp).items()})
    out.update({k: v[0] for k, v in property_counts(g, mp).items()})
    return out


def print_summary(a, mp, g, old, nrows, ncols, unmapped, resources, places, outputs, rep, sev):
    W = 78
    line, rule = '=' * W, '-' * W
    rel = lambda p: os.path.relpath(p) if not os.path.relpath(p).startswith('..' + os.sep + '..') else p
    def section(title):
        print(f'\n{title}\n{rule}')

    print(line)
    print(f' csv2rdf   {os.path.basename(a.data)}  ->  RDF')
    print(line)
    section('Input')
    print(f'  {"data":<10}{rel(a.data):<40}{fmt(nrows)} rows, {ncols} columns')
    yml = os.path.splitext(a.mapping)[0].replace('.sssom', '') + '.sssom.yml'
    print(f'  {"mapping":<10}{rel(a.mapping):<40}{len(mp.rows)} mappings' + (' (+ .sssom.yml)' if os.path.exists(yml) else ''))
    if places:
        print(f'  {"places":<10}{rel(a.places):<40}{fmt(places.count)} IRIs')
    for inc in a.include:
        print(f'  {"include":<10}{rel(inc)}')
    if unmapped:
        print(f'  {"unmapped":<10}{", ".join(unmapped)}  (kept in the CSV only)')

    section('Output')
    def files(label, paths, note=''):
        for i, pth in enumerate(paths):
            size = os.path.getsize(pth) if os.path.exists(pth) else 0
            kind = {'turtle': 'Turtle', 'nt': 'N-Triples', 'json-ld': 'JSON-LD', 'xml': 'RDF/XML', 'n3': 'N3'}[
                FORMATS[os.path.splitext(pth)[1].lower()]]
            hs = f'{size / 1048576:.1f} MB' if size >= 1048576 else f'{size / 1024:.1f} KB'
            print(f'  {label if i == 0 else "":<10}{rel(pth):<40}{kind:<11}{hs:>9}'
                  + (f'   {note}' if i == 0 and note else ''))
    files('RDF', outputs, f'{fmt(len(g))} triples')
    if a.void:
        files('VoID', a.void)
    if a.stats:
        print(f'  {"stats":<10}{rel(a.stats)}')
    print(f'  {"report":<10}' + (f'{rel(rep)}' if rep else 'none (no errors or warnings, so no report is generated)'))

    section('Resources')
    for k, v in resources.items():
        print(f'  {k:<44}{fmt(len(v)):>10}')

    cls, props = class_counts(g, mp), property_counts(g, mp)
    if old is not None:
        ocls, oprops = class_counts(old, mp), property_counts(old, mp)
        hdr = f'  {"":<44}{"before":>10}{"after":>10}{"change":>12}'
        section(f'Classes (compared with {os.path.basename(a.compare)})')
        print(hdr)
        print(f'  {"all triples":<44}{fmt(len(old)):>10}{fmt(len(g)):>10}{len(g) - len(old):>+12,}')
        for c, n in cls.items():
            print(f'  {c:<44}{fmt(ocls[c]):>10}{fmt(n):>10}{n - ocls[c]:>+12,}')
        section('Properties (triples; the indented line counts different IRIs)')
        print(hdr)
        for pid, (n, d) in props.items():
            o, od = oprops[pid]
            print(f'  {pid:<44}{fmt(o):>10}{fmt(n):>10}{n - o:>+12,}')
            if d is not None:
                print(f'  {"  (different IRIs)":<44}{fmt(od or 0):>10}{fmt(d):>10}{d - (od or 0):>+12,}')
    else:
        section('Classes')
        for c, n in cls.items():
            print(f'  {c:<44}{fmt(n):>10}')
        section('Properties')
        print(f'  {"":<44}{"triples":>10}{"different IRIs":>16}')
        for pid, (n, d) in props.items():
            print(f'  {pid:<44}{fmt(n):>10}{(fmt(d) if d is not None else ""):>16}')

    section('Problems')
    if not (sev['error'] or sev['warning']):
        print('  No errors or warnings - no report is generated.')
    else:
        print(f'  {sev["error"]} error(s), {sev["warning"]} warning(s) - details in {rel(rep)}\n')
        shown = [p for p in problems if p[0] in ('error', 'warning')]
        shown.sort(key=lambda p: (p[0] != 'error', p[1]))
        for p in shown[:15]:
            print(f'  {p[0].upper():<8}line {str(p[1]):<6}{short_iri(mp, p[3]) or "-":<26}{p[2]}: {p[4]}')
        if len(shown) > 15:
            print(f'  ... {len(shown) - 15} more in the report')
    print(line)
    print(' done: ' + ('with errors (exit code 1)' if sev['error'] else 'OK'))
    print(line)


# ---------------------------------------------------------------------------------------- stats page
def _esc(x):
    return str(x).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')


def _num(n, d=0):
    return f'{n:,.{d}f}' if isinstance(n, (int, float)) else '-'


def _label(mp, g, iri):
    lab = g.value(iri, RDFS.label) if isinstance(iri, URIRef) else None
    if lab is not None:
        return str(lab)
    s = short_iri(mp, iri)
    loc = re.split(r'[:/#]', s)[-1] if '://' in s else s.split(':', 1)[-1]
    return re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', loc.replace('_', ' ')) or s


def _hbars(items, width=660, bar_h=20, fmtv=lambda v: _num(v)):
    if not items:
        return '<p class="muted">No values.</p>'
    lw, pad = 290, 70
    vmax = max(v for _, v in items) or 1
    h = len(items) * (bar_h + 6) + 6
    out = [f'<svg viewBox="0 0 {width} {h}" class="chart" role="img">']
    for i, (lab, v) in enumerate(items):
        y = 6 + i * (bar_h + 6)
        w = (width - lw - pad) * v / vmax
        out.append(f'<text x="{lw - 8}" y="{y + bar_h * .72:.1f}" text-anchor="end" class="lbl">{_esc(lab if len(lab) <= 42 else lab[:41] + '…')}</text>'
                   f'<rect x="{lw}" y="{y}" width="{max(w, 1):.1f}" height="{bar_h}" rx="3" class="bar"><title>{_esc(lab)}: {fmtv(v)}</title></rect>'
                   f'<text x="{lw + w + 6:.1f}" y="{y + bar_h * .72:.1f}" class="val">{fmtv(v)}</text>')
    return ''.join(out) + '</svg>'


def _columns(points, width=900, height=240, fmtv=lambda v: _num(v)):
    """points: {year: value}"""
    if not points:
        return '<p class="muted">No values.</p>'
    left, right, top, bottom = 56, 12, 12, 28
    xs = sorted(points)
    x0, x1 = xs[0], xs[-1]
    span = max(x1 - x0, 1)
    vmax = (max(points.values()) or 1) * 1.08
    pw, ph = width - left - right, height - top - bottom
    X = lambda x: left + (x - x0) / span * pw
    Y = lambda y: top + ph - y / vmax * ph
    bw = max(pw / (span + 1) * .72, 1)
    out = [f'<svg viewBox="0 0 {width} {height}" class="chart" role="img">']
    for k in range(5):
        yv = vmax * k / 4
        out.append(f'<line x1="{left}" x2="{width - right}" y1="{Y(yv):.1f}" y2="{Y(yv):.1f}" class="grid"/>'
                   f'<text x="{left - 6}" y="{Y(yv) + 4:.1f}" text-anchor="end" class="axis">{fmtv(yv)}</text>')
    step = 10 if span > 50 else 5 if span > 20 else 2 if span > 8 else 1
    for x in range(x0 - x0 % step + (step if x0 % step else 0), x1 + 1, step):
        out.append(f'<text x="{X(x):.1f}" y="{height - 8}" text-anchor="middle" class="axis">{x}</text>')
    for x in xs:
        v = points[x]
        out.append(f'<rect x="{X(x) - bw / 2:.1f}" y="{Y(v):.1f}" width="{bw:.1f}" height="{top + ph - Y(v):.1f}" class="col">'
                   f'<title>{x}: {fmtv(v)}</title></rect>')
    return ''.join(out) + '</svg>'


def write_stats(path, g, mp, resources, ds, old, a, nrows, sev):
    """Generic statistics page: everything is derived from the mapping and the RDF output."""
    title = str(g.value(ds, DCTERMS.title) or os.path.basename(a.data)) if ds is not None else os.path.basename(a.data)
    version = str(g.value(ds, OWL.versionInfo) or '') if ds is not None else ''
    by_res = defaultdict(list)
    for m in mp.rows:
        by_res[m['resource'].split('||')[0].strip()].append(m)
    parts = []
    kpi = [('Triples', _num(len(g))), ('CSV rows', _num(nrows))] + [(k, _num(len(v))) for k, v in resources.items()]
    kpi += [('Classes', _num(len(set(g.objects(None, RDF.type))))), ('Properties', _num(len(set(g.predicates()))))]
    parts.append('<div class="kpis">' + ''.join(f'<div class="kpi"><b>{v}</b><span>{_esc(k)}</span></div>' for k, v in kpi) + '</div>')

    cls = class_counts(g, mp)
    parts.append('<h2>Classes</h2>' + _hbars([(c, n) for c, n in sorted(cls.items(), key=lambda x: -x[1]) if n]))
    if old is not None:
        ocls, oprops, nprops = class_counts(old, mp), property_counts(old, mp), property_counts(g, mp)
        rows = [('all triples', len(old), len(g))] + [(c, ocls[c], n) for c, n in cls.items()] + \
               [(p, oprops[p][0], n) for p, (n, _) in nprops.items()]
        parts.append(f'<h2>Compared with {_esc(os.path.basename(a.compare))}</h2><table><tr><th></th><th>before</th><th>after</th>'
                     '<th>change</th></tr>' + ''.join(f'<tr><td>{_esc(k)}</td><td>{_num(b)}</td><td>{_num(n)}</td><td>{n - b:+,}</td></tr>'
                                                       for k, b, n in rows) + '</table>')
    for pattern, ms in by_res.items():
        subs = resources.get(pattern, set())
        if not subs:
            continue
        parts.append(f'<h2>Resources {_esc(pattern)} ({_num(len(subs))})</h2>')
        # completeness
        rows = []
        for m in ms:
            if m['object_id'] == 'rdf:type':
                continue
            p = mp.expand(m['object_id'])
            n = sum(1 for s_ in subs if (s_, p, None) in g)
            rows.append((m['object_id'], m['column'], n))
        rows = list({r[0]: r for r in rows}.values())
        parts.append('<h3>Completeness</h3><table><tr><th>property</th><th>CSV column</th><th>resources with a value</th><th></th></tr>' +
                     ''.join(f'<tr><td>{_esc(pid)}</td><td>{_esc(col)}</td><td>{_num(n)} ({n / len(subs):.0%})</td>'
                             f'<td><div class="meter"><i style="width:{n / len(subs) * 100:.1f}%"></i></div></td></tr>' for pid, col, n in rows) + '</table>')
        # time axis: first date-like mapping
        date_m = next((m for m in ms if m.get('datatype') in ('xsd:dateTime', 'xsd:date', 'xsd:gYear')), None)
        year_of = {}
        if date_m:
            p = mp.expand(date_m['object_id'])
            for s_ in subs:
                v = g.value(s_, p)
                if v is not None and str(v)[:4].isdigit():
                    year_of[s_] = int(str(v)[:4])
            per_year = Counter(year_of.values())
            parts.append(f'<h3>Resources per year ({_esc(date_m["object_id"])})</h3>' + _columns(dict(per_year)))
        # numeric properties
        for m in ms:
            if m.get('datatype') not in ('xsd:integer', 'xsd:decimal', 'xsd:double', 'xsd:float'):
                continue
            p = mp.expand(m['object_id'])
            vals = {s_: float(v) for s_ in subs for v in [g.value(s_, p)] if v is not None}
            if not vals:
                continue
            xs = sorted(vals.values())
            dec = 4 if m['datatype'] == 'xsd:decimal' else 0
            parts.append(f'<h3>{_esc(m["object_id"])}</h3><p class="muted">{_num(len(xs))} values: min {_num(xs[0], dec)}, '
                         f'median {_num(xs[len(xs) // 2], dec)}, mean {_num(sum(xs) / len(xs), dec)}, max {_num(xs[-1], dec)}</p>')
            if year_of:
                agg = defaultdict(list)
                for s_, v in vals.items():
                    if s_ in year_of:
                        agg[year_of[s_]].append(v)
                if dec:
                    pts = {y: sum(v) / len(v) for y, v in agg.items()}
                    parts.append('<p class="muted">mean per year</p>' + _columns(pts, fmtv=lambda v: f'{v:.2f}'))
                else:
                    parts.append('<p class="muted">total per year</p>' + _columns({y: sum(v) for y, v in agg.items()}))
        # IRI-valued properties: most frequent values
        for m in ms:
            if m['object_id'] == 'rdf:type':
                continue
            p = mp.expand(m['object_id'])
            objs = [o for s_ in subs for o in g.objects(s_, p)]
            if not objs or not all(isinstance(o, URIRef) for o in objs):
                continue
            c = Counter(objs)
            if len(c) < 2:
                continue
            top = [(_label(mp, g, o), n) for o, n in c.most_common(15)]
            parts.append(f'<h3>{_esc(m["object_id"])}: most frequent of {_num(len(c))} values</h3>' + _hbars(top))
    if sev['error'] or sev['warning']:
        parts.append(f'<h2>Problems</h2><p>{sev["error"]} errors, {sev["warning"]} warnings (see the report file).</p>')
    html = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)} statistics</title><style>
:root{{--bg:#fff;--fg:#1b1f24;--muted:#5b6470;--line:#e3e6ea;--bar:#3b6fd8;--card:#f5f7fa}}
@media (prefers-color-scheme:dark){{:root{{--bg:#16181c;--fg:#e8eaed;--muted:#9aa3ad;--line:#2c3036;--bar:#6c9cff;--card:#1f2228}}}}
body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}}
main{{max-width:980px;margin:0 auto;padding:24px 16px 48px}} h1{{margin:0 0 4px;font-size:26px}} h2{{margin:36px 0 10px;font-size:20px;border-bottom:1px solid var(--line);padding-bottom:6px}}
h3{{margin:22px 0 6px;font-size:15px}} .muted{{color:var(--muted);margin:4px 0}} table{{border-collapse:collapse;width:100%;font-size:14px}}
td,th{{text-align:left;padding:5px 8px;border-bottom:1px solid var(--line)}} th{{color:var(--muted);font-weight:600}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px;margin-top:18px}}
.kpi{{background:var(--card);border-radius:8px;padding:12px;overflow-wrap:anywhere}} .kpi b{{display:block;font-size:22px}} .kpi span{{color:var(--muted);font-size:13px}}
.chart{{width:100%;height:auto}} .bar,.col{{fill:var(--bar)}} .lbl,.val,.axis{{fill:var(--fg);font-size:12px}} .axis{{fill:var(--muted)}} .grid{{stroke:var(--line)}}
.meter{{background:var(--line);border-radius:4px;height:8px;width:160px}} .meter i{{display:block;height:8px;border-radius:4px;background:var(--bar)}}
</style></head><body><main>
<h1>{_esc(title)}</h1><p class="muted">{('version ' + _esc(version) + ' &middot; ') if version else ''}generated by csv2rdf.py on {dt.date.today().isoformat()} from {_esc(os.path.basename(a.data))} with {_esc(os.path.basename(a.mapping))}</p>
{''.join(parts)}
</main></body></html>'''
    with open(path, 'w', encoding='utf-8') as f:
        f.write(html)

if __name__ == '__main__':
    main()
