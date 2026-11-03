#!/usr/bin/env python3
"""Add or refresh schema.org contentSize for every DataDownload in the JSON-LD of
docs/index.html, using the size of the local file. Run from the repository root
after each regeneration:  python3 scripts/add_file_sizes.py
"""
import os, re, sys

PAGE = "docs/index.html"
BASE = "https://saidfathalla.github.io/EVENTSKG-Dataset/"

def human(n):
    return f"{n / 1024:.1f} KB" if n < 1024 ** 2 else f"{n / 1024 ** 2:.1f} MB"

html = open(PAGE, encoding="utf-8").read()
# drop sizes written by an earlier run
html = re.sub(r'^[ \t]*"contentSize": "[^"]*",\n', "", html, flags=re.M)

done, missing = 0, []
def add(m):
    global done
    indent, url = m.group(1), m.group(2)
    path = url[len(BASE):] if url.startswith(BASE) else None
    if not path or not os.path.exists(path):
        missing.append(url)
        return m.group(0)
    done += 1
    return f'{indent}"contentSize": "{human(os.path.getsize(path))}",\n{m.group(0)}'

html = re.sub(r'([ \t]*)"contentUrl": "([^"]+)"', add, html)
open(PAGE, "w", encoding="utf-8").write(html)
print(f"contentSize set for {done} downloads")
for u in missing:
    print("  no local file for", u)
sys.exit(1 if missing else 0)
