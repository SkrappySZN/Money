#!/usr/bin/env python3
"""Every var(--token) in the app must resolve to a token that exists.

An unresolved var() fails silently: the declaration is dropped and the element
renders unstyled, which is how a max-width cap once looked like it was working
when it was not. This proves the rename was complete instead of assuming it.

    python3 check-tokens.py index.html
"""
import re, sys, pathlib

path = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else 'index.html')
src = path.read_text()

# A declaration may follow a brace, a semicolon or a newline — several tokens
# per line is normal, so anchoring to line start finds only the first of each.
defined = set(re.findall(r'(?:^|[;{])\s*(--[a-z0-9-]+)\s*:', src, re.M))
used = {}
for m in re.finditer(r'var\(\s*(--[a-z0-9-]+)\s*(?:,([^()]*))?\)', src):
    used.setdefault(m.group(1), []).append((m.start(), m.group(2) is not None))

# where in the file, so a report points somewhere useful
def where(i):
    line = src.count('\n', 0, i) + 1
    style_end = src.index('</style>') if '</style>' in src else len(src)
    return f"line {line} ({'stylesheet' if i < style_end else 'JS template'})"

missing = {t: locs for t, locs in used.items() if t not in defined}
unfallback = {t: [l for l in locs if not l[1]] for t, locs in missing.items()}
unfallback = {t: l for t, l in unfallback.items() if l}

print(f"  tokens defined : {len(defined)}")
print(f"  tokens used    : {len(used)}  ({sum(len(v) for v in used.values())} references)")
unused = defined - set(used)
if unused:
    print(f"  defined but never used: {len(unused)}  {sorted(unused)[:8]}")

if unfallback:
    print(f"\n  *** {len(unfallback)} UNRESOLVED TOKEN(S) — these render as nothing ***")
    for t, locs in sorted(unfallback.items()):
        print(f"    {t}  ×{len(locs)}   first at {where(locs[0][0])}")
    sys.exit(1)

if missing:
    print(f"\n  {len(missing)} undefined token(s), but all have fallbacks — allowed:")
    for t in sorted(missing): print(f"    {t}")

print("\n  every var() resolves")
