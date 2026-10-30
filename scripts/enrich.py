#!/usr/bin/env python3
"""
Check the DBpedia links of the places of an RDF dataset, type the places, and update the VoID counts
of the dataset description.

enrich.yml lists the properties whose values are places and the DBpedia type each place must have:

  places:
    seo:city: dbpedia-owl:Settlement
    seo:heldInCountry: dbpedia-owl:Country

Prefixes are those of the input file (plus an optional "prefixes:" block in enrich.yml).
For each place IRI DBpedia is asked whether it exists, whether it redirects and which types it has.
Redirects are replaced by their target, and each place gets the
expected type it has in DBpedia (dbr:Honolulu a dbpedia-owl:Settlement); a place of another kind than its
role (an island used as a city) gets the types DBpedia gives it (dbr:Maui a dbpedia-owl:Island).
No other facts are copied.
The VoID counts of the dataset description (the void:Dataset of the input) are recomputed.

  python3 enrich.py release/EVENTSKG.ttl -o release/EVENTSKG-final
"""
import argparse
import csv
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict

import rdflib
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS, XSD

import yaml

problems = []          # (severity, item, text)
changes = []           # (subject, property, old value, new value, reason)
VOID_COUNTS = {
    'triples': lambda g: len(g),
    'entities': lambda g: len(set(g.subjects(RDF.type, None))),
    'classes': lambda g: len(set(g.objects(None, RDF.type))),
    'properties': lambda g: len(set(g.predicates())),
    'distinctSubjects': lambda g: len(set(g.subjects())),
    'distinctObjects': lambda g: len(set(g.objects())),
}
VOID = 'http://rdfs.org/ns/void#'
FORMATS = {'ttl': 'turtle', 'nt': 'nt', 'jsonld': 'json-ld', 'rdf': 'xml', 'n3': 'n3'}


def warn(item, text, severity='warning'):
    problems.append((severity, str(item), text))


# --------------------------------------------------------------------------------------- web + cache
class Web:
    def __init__(self, cache_path, offline, refresh, pause, agent):
        self.agent = agent
        self.path, self.offline, self.refresh, self.pause = cache_path, offline, refresh, pause
        self.cache, self.calls, self.hits, self.failed = {}, 0, 0, 0
        if cache_path and os.path.exists(cache_path):
            with open(cache_path, encoding='utf-8') as f:
                self.cache = json.load(f)

    def save(self):
        if self.path:
            with open(self.path, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, ensure_ascii=False, sort_keys=True)

    def sparql(self, endpoint, query):
        key = hashlib.sha1((endpoint + '\n' + query).encode('utf-8')).hexdigest()
        if key in self.cache and not self.refresh:
            self.hits += 1
            return self.cache[key]
        if self.offline:
            return None
        body = urllib.parse.urlencode({'query': query}).encode()
        headers = {'User-Agent': self.agent, 'Accept': 'application/sparql-results+json',
                   'Content-Type': 'application/x-www-form-urlencoded'}
        last = None
        for attempt in range(4):
            self.calls += 1
            try:
                with urllib.request.urlopen(urllib.request.Request(endpoint, body, headers), timeout=120) as r:
                    rows = json.loads(r.read().decode('utf-8'))['results']['bindings']
                self.cache[key] = rows
                time.sleep(self.pause)
                return rows
            except urllib.error.HTTPError as e:
                last = e
                if e.code not in (429, 500, 502, 503, 504):
                    break
                time.sleep(int(e.headers.get('Retry-After') or 0) or 2 ** attempt * 3)
            except Exception as e:                      # network error, timeout, bad JSON
                last = e
                time.sleep(2 ** attempt * 3)
        warn(endpoint, f'no answer ({last})')
        self.failed += 1
        return None


# ------------------------------------------------------------------------------- what the mapping says
def read_config(path, g):
    """places: {property: type or [types]} -> {label: (property IRI, set of type IRIs)}"""
    try:
        with open(path, encoding='utf-8') as f:
            c = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        sys.exit(f'{path}: not valid YAML ({str(e).splitlines()[0]})')
    except OSError as e:
        sys.exit(f'{path}: {e.strerror}')
    prefixes = {p: str(n) for p, n in g.namespaces() if p}
    prefixes.update({p: str(n) for p, n in (c.get('prefixes') or {}).items()})

    def iri(x, required=True):
        x = str(x).strip()
        if re.match(r'^[a-z][a-z0-9+.-]*://', x, re.I):
            return URIRef(x)
        pfx, sep, local = x.partition(':')
        if sep and pfx in prefixes:
            return URIRef(prefixes[pfx] + local)
        if not required:
            return None
        sys.exit(f'{path}: "{x}" has no prefix known in the input file (add it under "prefixes:")')

    rules = {}
    for prop, types in (c.get('places') or {}).items():
        types = types if isinstance(types, list) else [types] if types else []
        rules[str(prop)] = (iri(prop), {iri(t) for t in types})
    if not rules:
        sys.exit(f'{path}: "places" lists no property')
    for p, ns in prefixes.items():
        g.bind(p, ns, override=False)
    return rules, c, iri


def write(g, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    fmt = FORMATS[path.rsplit('.', 1)[1]]
    if fmt == 'json-ld':
        g.serialize(path, format=fmt, context={p: str(n) for p, n in g.namespaces() if p}, indent=1, encoding='utf-8')
    else:
        g.serialize(path, format=fmt, encoding='utf-8')


# ------------------------------------------------------------------------------------------- places
def collect_places(g, rules):
    roles = defaultdict(set)
    for role, (prop, _) in rules.items():
        for s, o in g.subject_objects(prop):
            if isinstance(o, URIRef):
                roles[o].add(role)
            else:
                warn(s, f'{role} {o.n3()} is a literal, not an IRI: not checked')
    return roles


def look_up(web, a, places, same_as, lang):
    """IRI -> {'exists', 'target' (redirect), 'types', 'same' (owl:sameAs links), 'labels'}"""
    info = {p: {'exists': False, 'target': None, 'types': set(), 'same': set(), 'labels': set()} for p in places}
    sa = (f'OPTIONAL {{ ?t <{OWL.sameAs}> ?same FILTER(REGEX(STR(?same), "{same_as.replace(chr(92), chr(92) * 2)}")) }}' if same_as else '')
    lb = (f'OPTIONAL {{ ?t <{RDFS.label}> ?label FILTER(LANGMATCHES(LANG(?label), "{lang}")) }}' if lang else '')
    items = sorted(places)
    for i in range(0, len(items), a.batch):
        part = items[i:i + a.batch]
        red = f'OPTIONAL {{ ?s <{a.redirects}> ?r }}' if a.redirects else ''
        q = (f'SELECT DISTINCT ?s ?r ?type ?same ?label WHERE {{ VALUES ?s {{ {" ".join(f"<{p}>" for p in part)} }} '
             f'{red} BIND(COALESCE(?r, ?s) AS ?t) FILTER EXISTS {{ ?t ?anyp ?anyo }} '
             f'OPTIONAL {{ ?t <{RDF.type}> ?type }} {sa} {lb} }}')
        rows = web.sparql(a.endpoint, q)
        if rows is None:
            warn(f'{len(part)} places', 'lookup failed; rerun later (answers are cached)', 'error')
            for p in part:
                info[p]['exists'] = None
            continue
        for r in rows:
            p = URIRef(r['s']['value'])
            info[p]['exists'] = True
            if 'r' in r:
                info[p]['target'] = URIRef(r['r']['value'])
            if 'type' in r:
                info[p]['types'].add(URIRef(r['type']['value']))
            if 'same' in r:
                info[p]['same'].add(URIRef(r['same']['value']))
            if 'label' in r:
                info[p]['labels'].add(Literal(r['label']['value'], lang=r['label'].get('xml:lang')))
    return info


def superclasses(web, a, types):
    """type -> set of its superclasses (itself included), from the source's ontology.
    DBpedia states only the most specific type (Cologne a dbo:City), not dbo:Settlement."""
    out = {t: {t} for t in types}
    items = sorted(types)
    for i in range(0, len(items), a.batch):
        part = items[i:i + a.batch]
        q = (f'SELECT DISTINCT ?c ?sup WHERE {{ VALUES ?c {{ {" ".join(f"<{t}>" for t in part)} }} '
             f'?c <{RDFS.subClassOf}>* ?sup }}')
        for r in web.sparql(a.endpoint, q) or []:
            out[URIRef(r['c']['value'])].add(URIRef(r['sup']['value']))
    return out


def wiki_title(iri):
    return urllib.parse.unquote(re.split(r'[/#]', str(iri))[-1]).replace('_', ' ')


def wikidata_items(web, a, nodes):
    """place IRI -> Wikidata item, exactly: the item whose Wikipedia article has the title the DBpedia IRI is
    named after (dbr:Alexandria,_Virginia -> article "Alexandria, Virginia" -> wd:Q88).
    Returns None if Wikidata could not be asked."""
    if not nodes or not a.wikidata_endpoint:
        return None
    by_title = defaultdict(list)
    for n in nodes:
        by_title[wiki_title(n)].append(n)
    titles = sorted(by_title)
    out = {}
    for i in range(0, len(titles), 100):
        part = titles[i:i + 100]
        values = ' '.join('"' + t.replace('\\', '\\\\').replace('"', '\\"') + f'"@{a.wiki_lang}' for t in part)
        q = (f'SELECT ?title ?item WHERE {{ VALUES ?title {{ {values} }} ?article <http://schema.org/about> ?item ; '
             f'<http://schema.org/isPartOf> <{a.wikipedia}> ; <http://schema.org/name> ?title }}')
        rows = web.sparql(a.wikidata_endpoint, q)
        if rows is None:
            return None
        for r in rows:
            for n in by_title.get(r['title']['value'], []):
                out[n] = URIRef(r['item']['value'])
    return out


def check_places(g, rules, web, a, cfg):
    places = collect_places(g, rules)
    info = look_up(web, a, places, cfg.get('same_as'), cfg.get('place_labels')) if places else {}
    short = g.namespace_manager.normalizeUri
    match = re.compile(a.type_match) if a.type_match else None
    known = {t for i in info.values() for t in i['types'] if not match or match.search(str(t))}
    sup = superclasses(web, a, known) if known else {}
    stats = Counter(places=len(places))
    for role in rules:
        stats[f'role:{role}'] = sum(1 for r in places.values() if role in r)
    records = {}
    for p, roles in sorted(places.items()):
        i = info[p]
        rec = records[p] = {'iri': p, 'roles': roles, 'status': 'correct', 'node': p, 'types': set(), 'same': None, 'label': None}
        if i['exists'] is None:
            stats['unchecked'] += 1
            rec['status'] = 'not checked'
            continue
        if not i['exists']:
            warn(p, 'does not exist in the source: fix the IRI in the places file')
            stats['missing'] += 1
            rec['status'] = 'not in source'
            continue
        node = p
        if i['target'] and i['target'] != p:
            if a.fix_redirects:
                node = i['target']
                for prop, _ in rules.values():
                    for s in list(g.subjects(prop, p)):
                        g.remove((s, prop, p))
                        g.add((s, prop, node))
                        changes.append((str(s), short(prop), str(p), str(node), 'redirect'))
                warn(p, f'redirects to <{node}>: replaced (change it in the places file too)', 'info')
                stats['redirects fixed'] += 1
                rec['node'], rec['redirect'] = node, True
            else:
                warn(p, f'redirects to <{i["target"]}>: change it in the places file')
                stats['redirects'] += 1
                rec['redirect'] = True
        ok, fitting = True, set()
        informative = {t for t in i['types'] if t in sup}          # e.g. dbo:City, not owl:Thing
        closure = set().union(*(sup[t] for t in informative)) if informative else set()
        for role in sorted(roles):
            want = rules[role][1]
            if not want:
                continue
            if not informative:                  # nothing to check against: trust the role
                fitting |= set(sorted(want, key=str)[:1])
                rec['unverified'] = True
                warn(p, f'has no {a.type_label} type in the source, so its kind cannot be checked; '
                        f'typed {short(sorted(want, key=str)[0])} from its role', 'info')
            elif closure & want:
                fitting |= closure & want
            else:
                found = ', '.join(sorted(map(short, informative)))
                rec['found'] = {t for t in informative if not any(o != t and t in sup.get(o, ()) for o in informative)}
                warn(p, f'used as {short(rules[role][0])} but is {found} in the source, not '
                        f'{" or ".join(sorted(map(short, want)))}: typed as in the source', 'info')
                ok = False
        stats['correct' if ok else 'other kind'] += 1
        stats['type not checkable'] += bool(rec.get('unverified'))
        if not ok:                               # another kind of place (island, lake ...): type it as the source does
            rec['status'] = 'other kind'
            fitting |= rec['found']
        new = {t for t in i['types'] if not match or match.search(str(t))} if a.types == 'all' else \
            fitting if a.types == 'expected' else set()
        for t in sorted(new):
            if (node, RDF.type, t) not in g:
                g.add((node, RDF.type, t))
                stats['types added'] += 1
                rec['types'].add(t)
        if a.types != 'none' and not new and (node, RDF.type, None) not in g:
            stats['untyped'] += 1
        rec['candidates'] = set(i['same'])
        rec['linkable'] = True
        labels = sorted(i['labels'], key=str)
        if labels and (node, RDFS.label, None) not in g:
            g.add((node, RDFS.label, labels[0]))
            stats['place labels added'] += 1
            rec['label'] = labels[0]
    # owl:sameAs to Wikidata: the item of the place's Wikipedia article; DBpedia's links only as fallback
    linkable = {r['node']: r for r in records.values() if r.get('linkable')}
    exact = wikidata_items(web, a, list(linkable)) if cfg.get('same_as') else {}
    if exact is None:
        warn('Wikidata', 'Wikidata could not be asked: places with one DBpedia owl:sameAs link get it, places with '
                         'several get none; rerun later (answers are cached)')
    match_same = re.compile(cfg['same_as']) if cfg.get('same_as') else None
    for node, rec in linkable.items():
        cands = rec['candidates']
        x = (exact or {}).get(node)
        if x is not None and match_same and not match_same.search(str(x)):
            x = None
        if x is not None:
            stats['sameAs from Wikipedia title'] += 1
            if cands and x not in cands:
                warn(node, f'DBpedia links {", ".join(sorted(map(short, cands)))}, but the Wikipedia article '
                           f'"{wiki_title(node)}" belongs to {short(x)}: {short(x)} used', 'info')
        elif len(cands) == 1:
            x = next(iter(cands))
            stats['sameAs from DBpedia'] += 1
        elif cands:
            stats['sameAs undecided'] += 1
            if exact is not None:
                warn(node, f'no Wikidata item has the Wikipedia article "{wiki_title(node)}" and DBpedia gives '
                           f'{len(cands)} candidates: no owl:sameAs added')
        if x is not None and (node, OWL.sameAs, x) not in g:
            g.add((node, OWL.sameAs, x))
            stats['sameAs links added'] += 1
            rec['same'] = x
    return stats, records


def type_values(g, cfg, iri):
    """value_types: untyped IRI values of a property get the given type(s)."""
    added = Counter()
    for prop, types in (cfg.get('value_types') or {}).items():
        p = iri(prop, False)
        types = [iri(t, False) for t in (types if isinstance(types, list) else [types])]
        if p is None or None in types:
            warn(prop, 'value_types: prefix not in the input file, rule skipped', 'info')
            continue
        for o in set(g.objects(None, p)):
            if isinstance(o, URIRef) and (o, RDF.type, None) not in g:
                for t in types:
                    g.add((o, RDF.type, t))
                added[prop] += 1
    return added


def label_resources(g, cfg, iri):
    """labels: resources without rdfs:label get the value of the first of these properties they have."""
    props = [x for x in (iri(p, False) for p in (cfg.get('labels') or [])) if x is not None]
    n = 0
    for s in set(g.subjects(RDF.type, None)):
        if (s, RDFS.label, None) in g:
            continue
        for p in props:
            v = next((o for o in g.objects(s, p) if isinstance(o, Literal)), None)
            if v is not None:
                g.add((s, RDFS.label, Literal(str(v), lang=v.language)))
                n += 1
                break
    return n


# ----------------------------------------------------------------------------------- dataset metadata
def update_counts(g, ds):
    """Recompute the VoID numbers of the dataset description; nothing else is changed."""
    if ds is None or (ds, None, None) not in g:
        warn('dataset', 'the input has no dataset description (void:Dataset): VoID counts not updated')
        return {}
    props = {n: URIRef(VOID + n) for n in VOID_COUNTS}
    old = {n: g.value(ds, p) for n, p in props.items()}
    for p in props.values():
        g.set((ds, p, Literal(0, datatype=XSD.integer)))
    for _ in range(5):                           # repeat until the counts include themselves
        new = {n: f(g) for n, f in VOID_COUNTS.items()}
        if all(int(g.value(ds, props[n])) == v for n, v in new.items()):
            break
        for n, v in new.items():
            g.set((ds, props[n], Literal(v, datatype=XSD.integer)))
    return {n: (None if old[n] is None else int(old[n]), int(g.value(ds, props[n]))) for n in VOID_COUNTS}


# ------------------------------------------------------------------------------------------ results
STATUSES = ['correct', 'other kind', 'not in source', 'not checked']


def shortener(g):
    nsmap = {str(n): p for p, n in g.namespaces()}

    def short(x):
        x = str(x)
        if x in nsmap:
            return nsmap[x] + ':'
        if not x.startswith('http'):
            return x
        n = g.namespace_manager.normalizeUri(URIRef(x))
        return n if not n.startswith('<') else re.split(r'[/#]', x.rstrip('/#'))[-1]
    return short


def results(g, run):
    """Tables shared by the terminal summary and the statistics page."""
    short, rules, records = shortener(g), run['rules'], run['records']
    roles = list(rules)
    names = {r: short(rules[r][0]).split(':')[-1] for r in roles}
    place_rows = []
    for st in ['checked'] + STATUSES + ['redirect replaced', 'type taken from role']:
        row = []
        for r in roles + [None]:
            recs = [x for x in records.values() if r is None or r in x['roles']]
            if st == 'checked':
                row.append(len(recs))
            elif st == 'type taken from role':
                row.append(sum(1 for x in recs if x.get('unverified')))
            elif st == 'redirect replaced':
                row.append(sum(1 for x in recs if x.get('redirect') and x['node'] != x['iri']))
            else:
                row.append(sum(1 for x in recs if x['status'] == st))
        if st == 'checked' or any(row):
            place_rows.append((st if st != 'not in source' else 'not in the source', row))
    same_targets = Counter(re.match(r'https?://([^/]+)/', str(x['same'])).group(1) for x in records.values() if x['same'])
    added = [('rdf:type', 'places', sum(len(x['types']) for x in records.values())),
             ('owl:sameAs', 'places -> ' + (', '.join(same_targets) or 'none'), sum(same_targets.values())),
             ('rdfs:label', 'places', sum(1 for x in records.values() if x['label'] is not None)),
             ('rdfs:label', 'other resources, from ' + ' / '.join(p.split(':')[-1] for p in run['cfg'].get('labels') or []),
              run['labelled'])]
    added += [('rdf:type', f'values of {p}', n) for p, n in run['typed'].items()]
    ds = run['ds']
    meta = set(g.objects(ds, None)) if ds is not None else set()
    left = sorted({o for _, p, o in g if isinstance(o, URIRef) and p not in (RDF.type, OWL.sameAs) and o not in meta
                   and (o, RDF.type, None) not in g}, key=str)
    types_by_class = Counter(t for x in records.values() for t in x['types'])
    return dict(short=short, roles=roles, names=names, place_rows=place_rows, added=added, left=left,
                types_by_class=types_by_class)


def print_summary(g, run):
    a, R = run['a'], results(g, run)
    short, sev, W = R['short'], run['sev'], 78

    def head(t):
        print(f'\n {t}')

    total_added = len(g) - run['before']
    print('=' * W)
    print(f' enrich   {os.path.basename(a.dataset_file)}  ->  {os.path.basename(os.path.splitext(run["files"][0])[0])}')
    print('=' * W)
    head('Input')
    print(f'   {"dataset":<10}{a.dataset_file:<46}{run["before"]:>12,} triples')
    print(f'   {"config":<10}{a.config:<46}{len(run["rules"])} place properties')
    for r, (p, t) in run['rules'].items():
        print(f'   {"":<10}  {short(p):<24}' + ('must be ' + ' or '.join(sorted(map(short, t))) if t else 'no type check'))
    if not a.no_check:
        w = run['web']
        print(f'   {"source":<10}{a.endpoint:<46}{w.calls} queries, {w.hits} cached, {w.failed} failed'
              + (' (offline)' if a.offline else ''))

    if not a.no_check:
        head('Places')
        cols = [R['names'][r] for r in R['roles']] + ['total']
        print(f'   {"":<22}' + ''.join(f'{c[:13]:>14}' for c in cols))
        for label, row in R['place_rows']:
            print(f'   {label:<22}' + ''.join(f'{v:>14,}' for v in row))

    head('Added')
    print(f'   {"property":<14}{"to":<50}{"triples":>10}')
    for prop, what, n in R['added']:
        print(f'   {prop:<14}{what[:49]:<50}{n:>10,}')
    print(f'   {"total":<64}{total_added:>10,}')

    head('Dataset description (VoID counts)')
    if run['counts']:
        print(f'   {"dataset " + short(run["ds"]):<30}{"before":>14}{"after":>14}')
        for n, (o, v) in run['counts'].items():
            print(f'   {"void:" + n:<30}{"-" if o is None else f"{o:,}":>14}{v:>14,}')
    else:
        print('   the input has no dataset description: counts not updated')

    head('Output')
    exts = ' '.join(os.path.splitext(f)[1] for f in run['files'])
    print(f'   {"RDF":<10}{os.path.splitext(run["files"][0])[0] + "  " + exts:<46}{len(g):>12,} triples')
    print(f'   {"changes":<10}' + (f'{a.changes:<46}{len(changes):>12,} replaced IRI{"s" if len(changes) != 1 else ""}' if changes else 'none'))
    if problems:
        parts = [f'{sev[k]} {k}{"s" if sev[k] != 1 else ""}' for k in ('error', 'warning') if sev[k]]
        parts += [f'{sev["info"]} note{"s" if sev["info"] != 1 else ""}'] if sev['info'] else []
        print(f'   {"report":<10}{a.report:<46}{", ".join(parts):>12}')
    else:
        print(f'   {"report":<10}none (no errors, so no report is generated)')
    if a.stats:
        print(f'   {"stats":<10}{a.stats}')
    left = R['left']
    if left:
        print(f'   {"untyped":<10}{a.untyped:<46}{len(left):>12,} resource{"s" if len(left) != 1 else ""} left')
    else:
        print(f'   {"untyped":<10}none: every resource is typed')
    print('=' * W)


def node_groups(g, g0, run):
    """Groups of nodes to compare before/after: the places of each place property, the values of each
    value_types property, and the typed resources of the dataset grouped by class."""
    short, iri, cfg = shortener(g), run['iri'], run['cfg']
    redirect = {p: x['node'] for p, x in run['records'].items()}
    groups = []
    for _, (prop, _) in run['rules'].items():
        nodes0 = {o for o in g0.objects(None, prop) if isinstance(o, URIRef)}
        groups.append((short(prop).split(':')[-1], nodes0, {redirect.get(o, o) for o in nodes0}))
    for prop in (cfg.get('value_types') or {}):
        p = iri(prop, False)
        if p is not None:
            nodes0 = {o for o in g0.objects(None, p) if isinstance(o, URIRef)}
            if nodes0:
                groups.append((short(p).split(':')[-1], nodes0, nodes0))
    skip = {OWL.NamedIndividual, URIRef(VOID + 'Dataset'), OWL.Ontology}
    by_class = defaultdict(set)
    for s_, t in g0.subject_objects(RDF.type):
        if t not in skip and isinstance(s_, URIRef):
            by_class[t].add(s_)
    for t, nodes in sorted(by_class.items(), key=lambda kv: -len(kv[1])):
        groups.append((short(t).split(':')[-1], nodes, nodes))
    return groups


def coverage(g, nodes):
    n = len(nodes) or 1
    typed = sum(1 for x in nodes if (x, RDF.type, None) in g)
    labelled = sum(1 for x in nodes if (x, RDFS.label, None) in g)
    linked = sum(1 for x in nodes if (x, OWL.sameAs, None) in g)
    return {'typed': 100 * typed / n, 'labelled': 100 * labelled / n, 'linked': 100 * linked / n,
            'counts': (typed, labelled, linked)}


def external_links(g, ds):
    """Links from the data to resources of other datasets, by host (vocabulary terms do not count)."""
    vocab = {re.sub(r'[^#/]*$', '', str(x)) for x in set(g.predicates()) | set(g.objects(None, RDF.type))}
    home = re.match(r'https?://([^/]+)', str(ds)).group(1) if ds is not None else None
    hosts = Counter()
    for s_, p, o in g:
        if s_ == ds or p == RDF.type or not isinstance(o, URIRef):
            continue
        if re.sub(r'[^#/]*$', '', str(o)) in vocab:
            continue
        m = re.match(r'https?://([^/]+)', str(o))
        if m and m.group(1) != home:
            hosts[m.group(1)] += 1
    return hosts


def write_untyped(path, g, run, left):
    """One row per untyped resource: its name, why it has no type, and the resources (events) that use it."""
    short = shortener(g)
    by_node = {}
    for p, rec in run['records'].items():
        by_node[rec['node']] = rec
        by_node.setdefault(p, rec)
    rules = run['rules']

    def name(x):
        lab = g.value(x, RDFS.label)
        return str(lab) if lab is not None else wiki_title(x)

    rows = []
    for x in left:
        rec = by_node.get(x)
        users = sorted({(s_, p) for s_, p in g.subject_predicates(x) if p not in (OWL.sameAs,)}, key=lambda t: str(t[0]))
        used_as = sorted({short(p) for _, p in users})
        if rec is None:
            reason = 'not a place: no rule types it'
        elif rec['status'] == 'not in source':
            reason = 'does not exist in the source: fix the IRI'
        elif rec['status'] == 'other kind':
            found = sorted(map(short, rec.get('found', set()))) or ['no type']
            want = sorted({short(t) for r in rec['roles'] for t in rules[r][1]})
            reason = f'the source says {", ".join(found)}, not {" or ".join(want)}'
        else:
            reason = rec['status']
        rows.append([str(x), name(x), ', '.join(used_as), reason, len({s_ for s_, _ in users}),
                     ' | '.join(name(s_) for s_ in sorted({s_ for s_, _ in users}, key=str)),
                     ' | '.join(str(s_) for s_ in sorted({s_ for s_, _ in users}, key=str))])
    rows.sort(key=lambda r: (r[3], r[1]))
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['resource', 'name', 'used as', 'why it has no type', 'events', 'event names', 'event IRIs'])
        w.writerows(rows)


def write_stats(path, g, run):
    """Before/after page: what the enrichment changed in typing, labels and links."""
    import html
    esc, a, g0, short = html.escape, run['a'], run['g0'], shortener(g)
    ds = run['ds']
    groups = node_groups(g, g0, run)
    rows = [(name, len(n1), coverage(g0, n0), coverage(g, n1)) for name, n0, n1 in groups]

    def all_nodes(gr):
        """Resources the data is about: subjects and values, not classes, not owl:sameAs targets,
        not the dataset description."""
        out = set()
        for s_, p, o in gr:
            if s_ == ds:
                continue
            out.add(s_)
            if isinstance(o, URIRef) and p not in (RDF.type, OWL.sameAs):
                out.add(o)
        return {x for x in out if isinstance(x, URIRef)}
    def share(gr, test):
        nodes = all_nodes(gr)
        return 100 * sum(1 for x in nodes if test(gr, x)) / (len(nodes) or 1), len(nodes)
    t0, n0 = share(g0, lambda gr, x: (x, RDF.type, None) in gr)
    t1, n1 = share(g, lambda gr, x: (x, RDF.type, None) in gr)
    l0, _ = share(g0, lambda gr, x: (x, RDFS.label, None) in gr)
    l1, _ = share(g, lambda gr, x: (x, RDFS.label, None) in gr)
    ext0, ext1 = external_links(g0, ds), external_links(g, ds)
    cls0, cls1 = Counter(g0.objects(None, RDF.type)), Counter(g.objects(None, RDF.type))

    def kpi(label, before, after, fmt='{:,}', suffix=''):
        d = after - before
        dtxt = ('+' if d > 0 else '') + (fmt.format(d) if fmt == '{:,}' else f'{d:.1f}') + suffix
        return (f'<div class="kpi"><div class="kl">{esc(label)}</div><div class="kv">{fmt.format(after)}{suffix}</div>'
                f'<div class="kd">{fmt.format(before)}{suffix} before &middot; <b class="{"up" if d > 0 else "dn" if d < 0 else ""}">'
                f'{dtxt}</b></div></div>')

    kpis = ''.join([
        kpi(f'nodes with a type (of {n1:,})', t0, t1, '{:.1f}', '%'),
        kpi('nodes with a label', l0, l1, '{:.1f}', '%'),
        kpi('links to other datasets', sum(ext0.values()), sum(ext1.values())),
        kpi('datasets linked', len(ext0), len(ext1)),
        kpi('classes', len(cls0), len(cls1)),
        kpi('triples', len(g0), len(g)),
    ])

    def pair_chart(items, unit='%', maxv=None):
        """items: (label, before, after, note)"""
        if not items:
            return '<p class="muted">nothing to show</p>'
        m = maxv or max(max(b, c) for _, b, c, _ in items) or 1
        out = ['<div class="pc">']
        for lab, b, c, note in items:
            fb = f'{b:.0f}{unit}' if unit == '%' else f'{b:,}'
            fc = f'{c:.0f}{unit}' if unit == '%' else f'{c:,}'
            out.append(f'<div class="pl" title="{esc(note)}">{esc(lab)}<span class="muted"> {esc(note)}</span></div>'
                       f'<div class="pb"><div class="b0" style="width:{100 * b / m:.1f}%"></div>'
                       f'<div class="b1" style="width:{100 * c / m:.1f}%"></div></div>'
                       f'<div class="pv"><span class="muted">{fb}</span> &rarr; <b>{fc}</b></div>')
        out.append('</div>')
        return ''.join(out)

    legend = '<div class="lg"><span><i class="sw0"></i>before enrichment</span><span><i class="sw1"></i>after enrichment</span></div>'
    sec = [f'<div class="kpis">{kpis}</div>']
    sec.append('<h2>Typed nodes, by kind of node</h2><p class="muted">Share of the nodes of each kind that have an rdf:type.</p>'
               + legend + pair_chart([(n, b['typed'], c['typed'], f'({k:,})') for n, k, b, c in rows], maxv=100))
    sec.append('<h2>Labelled nodes, by kind of node</h2><p class="muted">Share with an rdfs:label, so tools can show a name instead of an IRI.</p>'
               + legend + pair_chart([(n, b['labelled'], c['labelled'], f'({k:,})') for n, k, b, c in rows], maxv=100))
    linked_rows = [(n, b['linked'], c['linked'], f'({k:,})') for n, k, b, c in rows if c['linked'] or b['linked']]
    if linked_rows:
        sec.append('<h2>Nodes linked to the same thing in another dataset (owl:sameAs)</h2>' + legend +
                   pair_chart(linked_rows, maxv=100))
    hosts = sorted(set(ext0) | set(ext1), key=lambda h: -ext1[h])
    sec.append('<h2>Links to other datasets, by dataset</h2><p class="muted">Triples whose value is a resource of another dataset.</p>'
               + legend + pair_chart([(h, ext0[h], ext1[h], '') for h in hosts], unit=''))
    new_cls = [(short(c), cls0[c], cls1[c], '') for c in sorted(set(cls1), key=lambda c: -(cls1[c] - cls0[c])) if cls1[c] != cls0[c]]
    sec.append('<h2>Classes whose number of instances changed</h2>' + legend + pair_chart(new_cls, unit=''))

    recs = run['records']
    if recs:
        st = Counter(x['status'] for x in recs.values())
        unver = sum(1 for x in recs.values() if x.get('unverified'))
        red = sum(1 for x in recs.values() if x.get('redirect') and x['node'] != x['iri'])
        quality = [('checked and correct', st['correct'] - unver), ('correct, typed from its role', unver),
                   ('redirect replaced by its target', red), ('another kind of place, typed as in DBpedia', st['other kind']),
                   ('not in DBpedia (fix the IRI)', st['not in source'])]
        tot = len(recs) or 1
        sec.append('<h2>Place links checked against DBpedia</h2><div class="pc">' + ''.join(
            f'<div class="pl">{esc(k)}</div><div class="pb"><div class="b1" style="width:{100 * v / tot:.1f}%"></div></div>'
            f'<div class="pv"><b>{v:,}</b> <span class="muted">{100 * v / tot:.0f}%</span></div>' for k, v in quality) + '</div>')
        bad = [(short(p), ', '.join(short(run['rules'][r][0]).split(':')[-1] for r in x['roles']), x['status'])
               for p, x in sorted(recs.items(), key=lambda kv: str(kv[0])) if x['status'] != 'correct']
        if bad:
            sec.append(f'<details><summary>Places to check: not in DBpedia, or another kind of place than their role ({len(bad)})</summary><table>'
                       '<tr><th>place</th><th>used as</th><th>problem</th></tr>' + ''.join(
                           f'<tr><td>{esc(p)}</td><td>{esc(r)}</td><td>{esc(x)}</td></tr>' for p, r, x in bad) + '</table></details>')
        if changes:
            pairs = sorted({(short(o), short(n)) for _, _, o, n, _ in changes})
            sec.append(f'<details><summary>Redirects replaced ({len(pairs)})</summary><table><tr><th>old</th><th>new</th></tr>'
                       + ''.join(f'<tr><td>{esc(o)}</td><td>{esc(n)}</td></tr>' for o, n in pairs) + '</table></details>')
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Enrichment: before and after</title>
<style>
:root{{--bg:#fcfcfb;--fg:#0b0b0b;--muted:#6b6a65;--line:#e4e3df;--card:#f3f2ef;--b0:#c9c8c2;--b1:#2a78d6;--up:#008300;--dn:#e34948}}
@media (prefers-color-scheme:dark){{:root{{--bg:#1a1a19;--fg:#f0efec;--muted:#a3a29b;--line:#33322f;--card:#242422;--b0:#55544f;--b1:#3987e5;--up:#3fae3f;--dn:#e66767}}}}
body{{background:var(--bg);color:var(--fg);font:14px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:0;padding:24px 16px}}
main{{max-width:980px;margin:0 auto}} h1{{font-size:22px;margin:0 0 4px}} h2{{font-size:16px;margin:32px 0 4px}}
p{{margin:0 0 8px}} .muted{{color:var(--muted)}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:18px 0}}
.kpi{{background:var(--card);border-radius:8px;padding:12px 14px}} .kv{{font-size:22px;font-weight:600}}
.kl{{color:var(--muted);font-size:12px}} .kd{{color:var(--muted);font-size:12px}} .up{{color:var(--up)}} .dn{{color:var(--dn)}}
.lg{{display:flex;gap:16px;font-size:12px;color:var(--muted);margin:4px 0 8px}} .lg i{{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:6px;vertical-align:-2px}}
.sw0{{background:var(--b0)}} .sw1{{background:var(--b1)}}
.pc{{display:grid;grid-template-columns:minmax(150px,240px) 1fr 120px;gap:6px 12px;align-items:center}}
.pl{{font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.pb{{display:flex;flex-direction:column;gap:2px}} .b0,.b1{{height:9px;border-radius:0 4px 4px 0;min-width:1px}}
.b0{{background:var(--b0)}} .b1{{background:var(--b1)}} .pv{{text-align:right;font-variant-numeric:tabular-nums;font-size:13px}}
details{{margin-top:16px}} summary{{cursor:pointer;font-weight:600}}
table{{border-collapse:collapse;width:100%;font-size:13px;margin-top:8px}} th,td{{padding:5px 8px;border-bottom:1px solid var(--line);text-align:left}}
th{{color:var(--muted)}}
@media (max-width:600px){{.pc{{grid-template-columns:1fr 90px}} .pb{{grid-column:1/-1;order:3}}}}
</style></head><body><main>
<h1>Enrichment: before and after</h1>
<p class="muted">{esc(os.path.basename(a.dataset_file))} &rarr; {esc(os.path.basename(run['files'][0]))}
&middot; {esc(a.endpoint)} &middot; {len(g) - len(g0):,} triples added</p>
{''.join(sec)}
</main></body></html>"""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(page)


# --------------------------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description='Check the DBpedia links of the places of an RDF dataset, type the '
                                             'places and update the VoID counts.')
    ap.add_argument('dataset_file', help='RDF dataset (any RDF format)')
    ap.add_argument('-c', '--config', default='enrich.yml', metavar='FILE.yml',
                    help='settings: place properties and types, sameAs, labels, value types (default enrich.yml)')
    ap.add_argument('--stats', metavar='FILE.html', help='also write a statistics page (HTML) about the enrichment')
    ap.add_argument('-o', '--output', metavar='BASE', help='output base name; BASE.ttl, .nt, .jsonld, .rdf, .n3 '
                    '(default: input name + "-enriched")')
    ap.add_argument('--formats', help='comma-separated subset of ttl,nt,jsonld,rdf,n3 (default: all)')
    ap.add_argument('--endpoint', help='SPARQL endpoint of the places (default: "endpoint" in the config, else DBpedia)')
    ap.add_argument('--redirects', default='http://dbpedia.org/ontology/wikiPageRedirects',
                    help='redirect property of the source ("" = do not follow redirects)')
    ap.add_argument('--keep-redirects', dest='fix_redirects', action='store_false',
                    help='only report redirecting IRIs instead of replacing them')
    ap.add_argument('--types', choices=['expected', 'all', 'none'], default='expected',
                    help='types added to the places: the one from the "type" check (default), all source types '
                         'matching --type-match, or none')
    ap.add_argument('--type-match', default=r'^http://dbpedia\.org/ontology/',
                    help='which source types count (default: the DBpedia ontology; owl:Thing etc. do not)')
    ap.add_argument('--wikidata-endpoint', default='https://query.wikidata.org/sparql',
                    help='used to choose between several owl:sameAs candidates ("" = do not; such places get no link)')
    ap.add_argument('--wikipedia', default='https://en.wikipedia.org/', help='Wikipedia whose titles the place IRIs use')
    ap.add_argument('--user-agent', default='csv2rdf-enrich/1.0 (https://github.com/saidfathalla/EVENTSKG-Dataset)',
                    help='sent with every query; Wikidata asks for a contact URL')
    ap.add_argument('--no-check', action='store_true', help='do not query the source; only update the counts')
    ap.add_argument('--batch', type=int, default=50, help='IRIs per query (default 50)')
    ap.add_argument('--pause', type=float, default=1.0, help='seconds between queries (default 1)')
    ap.add_argument('--cache', default='.enrich_cache.json', help='answer cache ("" = none)')
    ap.add_argument('--offline', action='store_true', help='use cached answers only')
    ap.add_argument('--refresh', action='store_true', help='ignore the cache')
    ap.add_argument('--changes', default='enrich_changes.csv', help='list of replaced IRIs')
    ap.add_argument('--report', default='enrich_report.csv', help='errors (written only if there are any)')
    ap.add_argument('--untyped', default='enrich_untyped.csv', metavar='FILE.csv',
                    help='resources left without a type, with their name, the reason and the events that use them')
    ap.add_argument('--warnings', action='store_true', help='also write warnings and notes to the report')
    a = ap.parse_args()
    a.endpoint_given = bool(a.endpoint)
    a.wiki_lang = re.match(r'https?://([a-z-]+)\.wikipedia', a.wikipedia).group(1) if 'wikipedia' in a.wikipedia else 'en'
    a.type_label = 'DBpedia ontology' if 'dbpedia' in (a.type_match or '') else 'matching'
    a.endpoint = a.endpoint or 'https://dbpedia.org/sparql'

    exts = [e.strip().lstrip('.') for e in (a.formats or ','.join(FORMATS)).split(',') if e.strip()]
    bad = [e for e in exts if e not in FORMATS]
    if bad:
        sys.exit(f'unknown format(s) {", ".join(bad)} (use {", ".join(FORMATS)})')
    base = a.output or os.path.splitext(a.dataset_file)[0] + '-enriched'
    base = re.sub(r'\.(' + '|'.join(FORMATS) + r')$', '', base)
    files = [f'{base}.{e}' for e in exts]
    if any(os.path.abspath(f) == os.path.abspath(a.dataset_file) for f in files):
        sys.exit('the output would overwrite the input: choose another -o')

    g = Graph(bind_namespaces='none')
    try:
        g.parse(a.dataset_file, format=rdflib.util.guess_format(a.dataset_file) or 'turtle')
    except Exception as e:
        sys.exit(f'{a.dataset_file}: cannot be read as RDF ({e})')
    rules, cfg, iri = read_config(a.config, g)
    if cfg.get('endpoint') and not a.endpoint_given:
        a.endpoint = cfg['endpoint']
    before = len(g)
    g0 = Graph(bind_namespaces='none')                 # copy before enrichment, for --stats
    if a.stats:
        for t in g:
            g0.add(t)
    found = [s for s in g.subjects(RDF.type, URIRef(VOID + 'Dataset')) if isinstance(s, URIRef)]
    if len(found) > 1:
        sys.exit(f'{len(found)} void:Dataset resources in the input: cannot tell which one to update')
    ds = found[0] if found else None

    web = Web(a.cache, a.offline, a.refresh, a.pause, a.user_agent)
    stats, records = (Counter(), {}) if a.no_check else check_places(g, rules, web, a, cfg)
    typed = type_values(g, cfg, iri)
    labelled = label_resources(g, cfg, iri)
    web.save()
    counts = update_counts(g, ds)
    for f in files:
        write(g, f)

    if changes:
        with open(a.changes, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(['subject', 'property', 'old value', 'new value', 'reason'])
            w.writerows(changes)
    elif os.path.exists(a.changes):
        os.remove(a.changes)
    if not a.warnings:                          # only errors are reported unless --warnings
        problems[:] = [p for p in problems if p[0] == 'error']
    sev = Counter(p[0] for p in problems)
    if problems:
        with open(a.report, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(['severity', 'item', 'problem'])
            w.writerows(sorted(problems, key=lambda p: ({'error': 0, 'warning': 1}.get(p[0], 2), p[1])))
    elif os.path.exists(a.report):
        os.remove(a.report)

    run = dict(g0=g0, iri=iri, a=a, rules=rules, cfg=cfg, stats=stats, records=records, typed=typed, labelled=labelled,
               counts=counts, ds=ds, before=before, files=files, web=web, sev=sev)
    left = results(g, run)['left']
    if left:
        write_untyped(a.untyped, g, run, left)
    elif os.path.exists(a.untyped):
        os.remove(a.untyped)
    if a.stats:
        write_stats(a.stats, g, run)
    print_summary(g, run)
    sys.exit(1 if sev['error'] else 0)


if __name__ == '__main__':
    main()
