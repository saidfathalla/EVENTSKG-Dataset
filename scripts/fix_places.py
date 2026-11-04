#!/usr/bin/env python3
"""Correct the seven gazetteer IRIs that the enrichment could not find in DBpedia.
Run once from the repository root:  python3 scripts/fix_places.py
"""
P = 'data/dbpedia_places.csv'
R = 'http://dbpedia.org/resource/'
FIX = {
    'Bengaluru':             'Bangalore',              # DBpedia uses the old English title
    'Chia,_Sardinia':        'Chia_(Sardinia)',
    'Friuli_Venezia_Giulia': 'Friuli-Venezia_Giulia',
    'Lofthus,_Ullensvang':   'Lofthus,_Vestland',
    'Roanoke,_Virgini':      'Roanoke,_Virginia',      # typo
    'Tromsø':                'Tromsø_(city)',
    'Victoria_(state)':      'Victoria_(Australia)',
}
text = open(P, encoding='utf-8', newline='').read()
sep = '\r\n' if '\r\n' in text else '\n'
out, n = [], 0
for line in text.split(sep):
    for old, new in FIX.items():
        for tail_old, tail_new in ((',' + R + old, ',' + R + new), (',"' + R + old + '"', ',"' + R + new + '"')):
            if line.endswith(tail_old):
                line = line[: -len(tail_old)] + tail_new
                n += 1
    out.append(line)
open(P, 'w', encoding='utf-8', newline='').write(sep.join(out))
print(f'{n} rows changed (expected 9)')
