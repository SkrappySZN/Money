#!/usr/bin/env python3
"""
Build the publishable copy.

index.html holds your real data (48% of it is balances, limits and 40 weeks of
history). docs/index.html is the same app with every seed block emptied, so the
published page carries nothing personal. It refuses to write a file that still
has your data in it.

    python3 build.py
"""
import json, re, sys, pathlib

HERE = pathlib.Path(__file__).parent
SRC  = HERE / "index.html"
OUT  = HERE / "docs" / "index.html"

# each seed constant, and what it becomes in the published copy
BLANKS = {
    "SEED":      'const SEED={"v":1,"accounts":[],"weeks":{}};',
    "PLAN_SEED": 'const PLAN_SEED={source:"",order:[],steps:[],calendar:[],open:[],ref:null,minsToVerify:[]};',
    "ACCT_SEED": 'const ACCT_SEED={};',
}

# if any of these survive into the output, the build is wrong and we stop
FORBIDDEN = [
    "[redacted]", "[redacted]", "[redacted]", "[redacted]", "[redacted]", "[redacted]",
    "[redacted]", "[redacted]", "[redacted]", "Z4", "[redacted]", "[redacted]",
    "[redacted]", "[redacted]", "[redacted]", "[redacted]",
]

def strip_const(src: str, name: str, blank: str) -> str:
    """Replace `const NAME={...};` with an empty equivalent, brace-matching so a
    95KB object literal full of nested braces comes out cleanly."""
    m = re.search(r"const\s+" + name + r"\s*=\s*\{", src)
    if not m:
        sys.exit(f"build: could not find `const {name} = {{` in {SRC.name}")
    i = src.index("{", m.start())
    depth, j, in_str, quote, esc = 0, i, False, "", False
    while j < len(src):
        c = src[j]
        if in_str:
            if esc:            esc = False
            elif c == "\\":    esc = True
            elif c == quote:   in_str = False
        elif c in "\"'":       in_str, quote = True, c
        elif c == "{":         depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                break
        j += 1
    else:
        sys.exit(f"build: unbalanced braces reading {name}")
    end = j + 1
    while end < len(src) and src[end] in " ;\n":     # take the trailing `;`
        if src[end] == ";":
            end += 1
            break
        end += 1
    return src[:m.start()] + blank + src[end:]

def main():
    src = SRC.read_text()
    before = len(src)

    seed = json.loads(re.search(r"const SEED=(\{.*?\});\n", src, re.S).group(1))
    print(f"source : {SRC.name}  {before:,} bytes")
    print(f"         {len(seed['accounts'])} accounts, {len(seed['weeks'])} weeks of real data")

    out = src
    for name, blank in BLANKS.items():
        out = strip_const(out, name, blank)

    # nothing personal may survive
    hits = sorted({w for w in FORBIDDEN if w in out})
    if hits:
        sys.exit(f"build: REFUSING to write — personal data still present: {', '.join(hits)}")

    # and it still has to be a working app
    for marker in ("function renderWelcome(", "function computeWeek(", "boot();"):
        if marker not in out:
            sys.exit(f"build: output is missing `{marker}` — something was over-stripped")

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(out)
    print(f"wrote  : docs/{OUT.name}  {len(out):,} bytes  ({before-len(out):,} bytes of data removed)")
    print("checked: no account names, balances or plan details in the published copy")

if __name__ == "__main__":
    main()
