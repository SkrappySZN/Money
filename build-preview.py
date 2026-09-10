#!/usr/bin/env python3
"""Renders the previews from preview-data.json — the app engine's own output.

    bun preview-data.js > preview-data.json && python3 build-preview.py

No figure in a preview is typed by hand. If the app's numbers change, the
previews change with them or the build refuses.
"""
import json, re, sys, pathlib, hashlib, subprocess

# ── Editing helpers ──────────────────────────────────────────────────
# A slice taken between two markers is only meaningful if they are in order.
# Getting that wrong once produced an empty slice, and str.replace('', x)
# inserts between every character — it took this file from 39KB to 123MB.
def cut(text, start, end):
    a, b = text.index(start), text.index(end)
    assert a < b, (f'slice bounds inverted: {start!r} at {a} comes after {end!r} at {b}')
    return text[a:b]

def replace_once(text, old, new):
    assert old, 'refusing to replace an empty string — it inserts between every character'
    n = text.count(old)
    assert n == 1, f'expected exactly one match, found {n}: {old[:60]!r}'
    return text.replace(old, new)

D = json.load(open('preview-data.json'))
CSS_BASE = pathlib.Path('preview-css/base.css').read_text()
CSS_RAIL = pathlib.Path('preview-css/rail.css').read_text()

# ── Staleness guard ──────────────────────────────────────────────────
def _sha(p): return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()[:16]
def _head():
    try: return subprocess.run(['git','rev-parse','HEAD'], capture_output=True,
                               text=True, check=True).stdout.strip()
    except Exception: return 'unknown'

META = D.get('_meta', {})
NOW_HASH, NOW_HEAD = _sha('index.html'), _head()
STALE = []
if META.get('appHash') != NOW_HASH:
    STALE.append(f"index.html changed since the data was dumped "
                 f"({META.get('appHash','?')} -> {NOW_HASH})")
if META.get('gitHead') != NOW_HEAD:
    STALE.append(f"HEAD moved ({str(META.get('gitHead','?'))[:8]} -> {NOW_HEAD[:8]})")
if STALE and '--stale-ok' not in sys.argv:
    print('REFUSING to render — preview-data.json is stale:', file=sys.stderr)
    for s_ in STALE: print(f'  · {s_}', file=sys.stderr)
    print('\n  bun preview-data.js > preview-data.json && python3 build-preview.py',
          file=sys.stderr)
    sys.exit(1)
BANNER = ('' if not STALE else
  '<div style="background:var(--negative);color:var(--paper);padding:10px 18px;'
  'font:600 13px system-ui;letter-spacing:.04em">STALE — rendered from data that does '
  'not match the app: ' + '; '.join(STALE) + '</div>')

# ── formatting ───────────────────────────────────────────────────────
def money(n, dp=2): return ('−' if n < 0 else '') + f"${abs(n):,.{dp}f}"
def m0(n):          return ('−' if n < 0 else '') + f"${abs(n):,.0f}"
def pct(v, dp=1):   return f"{v*100:.{dp}f}%"
def esc(t):         return str(t).replace('&','&amp;').replace('<','&lt;').replace('"','&quot;')
def shortdate(s):
    if not s: return '—'
    M=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
    y,mo,dd = s.split('-'); return f"{M[int(mo)-1]} {int(dd)}"

MONEY_RE = re.compile(r'−?\$[\d,]+(?:\.\d\d)?')

def mark(html, severity):
    """R11 three-level marking, applied to the app's own check text: account name
    and the breach figure in oxblood, every other number set apart by figure
    style, prose in ink. Derived, never retyped."""
    lead = re.search(r'<b>(.*?)</b>', html)
    if lead:
        inner = lead.group(1)
        for name in sorted(D['accountNames'], key=len, reverse=True):
            if inner.startswith(name):
                inner = f'<span class="account">{esc(name)}</span>' + inner[len(name):]
                break
        html = html[:lead.start()] + inner + html[lead.end():]
    html = re.sub(r'\b(\d+)\s(weeks?|days?)\b', r'<span class="fig">\1 \2</span>', html)
    html = MONEY_RE.sub(lambda m: f'<span class="fig">{m.group(0)}</span>', html)
    if severity != 'ok':
        i = html.find('—')
        if i >= 0:
            html = html[:i] + re.sub(r'<span class="fig">', '<span class="fig-breach">',
                                     html[i:], count=1)
    return html

# ── shared components ────────────────────────────────────────────────
# One segmented control serves This Week (Compact/Full sheet) and both Attack
# and Payoff (strategy). It has needed no variation.
def seg(options, current):
    return ('<span class="seg">' + ''.join(
        f'<button aria-pressed="{"true" if o==current else "false"}">{esc(o)}</button>'
        for o in options) + '</span>')

def sect(title, id_, trailing=''):
    tail = f'<span style="margin-left:auto">{trailing}</span>' if trailing else ''
    return f'<h2 class="sect-label" id="{id_}">{esc(title)}{tail}</h2>'

def hero(label, figure, note=''):
    n = f'<div class="hero-note">{esc(note)}</div>' if note else ''
    return (f'<div class="hero-row"><div class="hero-label">{esc(label)}</div>'
            f'<div class="hero-figure">{figure}</div>{n}</div>')

def metric(label, value, note=None, state=''):
    n = f'<div class="m-note">{esc(note)}</div>' if note else ''
    return (f'<div class="metric"><div class="m-label">{esc(label)}</div>'
            f'<span class="m-value {state}">{value}</span>{n}</div>')

# ── This Week ────────────────────────────────────────────────────────
RAMP = [('Attack','var(--fill-emphasis)'), ('Other debt','var(--fill-strong)'),
        ('Minimums','var(--fill-mid)'), ('Buckets & savings','var(--fill-faint)')]

def alloc_bar():
    span = max(D['allocated'], D['income'])
    parts, legend = [], []
    for name, colour in RAMP:
        v = D['alloc'][name]
        if v <= 0: continue
        parts.append(f'<span style="width:{v/span*100:.4f}%;background:{colour}"></span>')
        legend.append(f'<span class="k"><i class="sw" style="background:{colour}"></i>'
                      f'{esc(name)} <b>{money(v)}</b></span>')
    over = D['allocated'] > D['income'] + 0.005
    if over:
        at = D['income']/span*100
        parts.append(f'<i class="overrun" style="left:{at:.4f}%;'
                     f'width:{(D["allocated"]-D["income"])/span*100:.4f}%"></i>')
        parts.append(f'<i class="paycheck-line" style="left:{at:.4f}%"></i>')
    seg_txt = ', '.join(f"{n} {money(D['alloc'][n])}" for n,_ in RAMP if D['alloc'][n] > 0)
    tail = (f"Over-allocated by {money(-D['unallocated'])}." if D['unallocated'] < -0.005
            else f"Unassigned {money(D['unallocated'])}." if abs(D['unallocated']) >= 0.005
            else "Fully assigned, nothing left over.")
    label = (f"Where the paycheck goes. Paycheck {money(D['income'])}, "
             f"assigned {money(D['allocated'])}. {seg_txt}. {tail}")
    return (f'<div class="allocbar{" is-over" if over else ""}" role="img" '
            f'aria-label="{esc(label)}">{"".join(parts)}</div>'
            f'<div class="legend">{"".join(legend)}</div>')

def strip():
    s, un = D['strip'], D['unallocated']
    state = 'is-over' if un < -0.005 else ('is-settled' if abs(un) < 0.005 else 'is-idle')
    word  = 'Over by' if un < -0.005 else 'Unassigned'
    shown = money(abs(un)) if un < -0.005 else money(un)
    return '<div class="strip">' + ''.join([
        metric(word, shown, None, state),
        metric('Total debt', m0(s['debtBalance']),
               f'{m0(s["cardBalance"])} cards · {m0(s["loanBalance"])} loans'),
        metric('Utilization', pct(s['usage']), f'{m0(s["availAfter"])} open', 'is-flagged'),
        metric('Interest this week', money(s['weekInterest']),
               f'{money(s["monthlyInterest"])}/mo at today’s balances'),
    ]) + '</div>'

def checks():
    attn = [c for c in D['checks'] if c['s'] != 'ok']
    fine = [c for c in D['checks'] if c['s'] == 'ok']
    h = ''
    if attn:
        rows = ''.join(f'<li class="attn-row"><p>{mark(c["t"], c["s"])}</p></li>' for c in attn)
        h += (f'<h2 class="sect-label" id="attn-h">Needs attention '
              f'<span class="count">{len(attn)}</span></h2><ul class="attn-list">{rows}</ul>')
    if fine:
        rows = ''.join(f'<li>{mark(c["t"], "ok")}</li>' for c in fine)
        h += ('<button class="ok-head" aria-expanded="false" aria-controls="ok-list">'
              '<span class="caret"><svg width="9" height="9" viewBox="0 0 12 12" fill="none" '
              'stroke="currentColor" stroke-width="2" stroke-linecap="round" '
              'stroke-linejoin="round"><path d="M4.5 2.5L8 6l-3.5 3.5"/></svg></span>'
              f'Going well <span class="count">{len(fine)}</span></button>'
              f'<ul class="ok-list" id="ok-list" hidden>{rows}</ul>')
    return h

def funds():
    rows, notes = [], []
    for f in D['funds']:
        cls = 'done' if f['done'] else ''
        rows.append(f'<div class="fund"><div class="fname">{esc(f["name"])}</div>'
                    f'<div class="fbar"><i class="{cls}" style="width:{f["pct"]}%"></i></div>'
                    f'<div class="fnum">{m0(f["after"])} / {m0(f["target"])}</div></div>')
        if f['done']:
            extra = f' — {money(f["frees"])}/wk frees up' if f.get('frees') else ''
            notes.append(f'<span class="k">{esc(f["name"])}: <b>funded</b>{esc(extra)}</span>')
        else:
            by = f' by {shortdate(f["by"])}' if f['by'] else ''
            notes.append(f'<span class="k">{esc(f["name"])}: {money(f["short"])} to go{esc(by)}</span>')
    return ''.join(rows) + f'<div class="legend">{"".join(notes)}</div>'

COMPACT = ['Account','Balance','Min due','Due','Min','Attack','Other','Total','Interest','After']
FULL    = ['Account','Limit','APR','Balance','Usage','Min due','Close','Due','Min','Attack',
           'Other','Total','Interest','After','Usage after','Avail after','6 mo']

def cellin(v, cls=''):
    z = ' is-zero' if abs(v) < 0.005 else ''
    c = f' {cls}' if cls else ''
    return f'<td class="num"><input class="cell{c}{z}" value="{v:.2f}"></td>'

def grid(dense):
    cols = COMPACT if dense else FULL
    body = []
    for r in D['grid']:
        if 'sect' in r:
            body.append(f'<tr class="sect"><th scope="rowgroup" colspan="{len(cols)}">'
                        f'<span>{esc(r["sect"])}</span></th></tr>')
            continue
        cls = ' '.join(filter(None, ['rollup' if r['rollup'] else '',
                                     'child' if r['child'] else '']))
        cells = [f'<th scope="row" title="{esc(r["name"])}">'
                 f'<span class="acct">{esc(r["name"])}</span></th>']
        if not dense:
            cells += [f'<td class="num dim">{m0(r["limit"]) if r["limit"] else "—"}</td>',
                      f'<td class="num dim">{pct(r["apr"],2) if r["apr"] else "—"}</td>']
        if r['rollup'] or r['income']:
            cells.append(f'<td class="num dim">{money(r["balance"])}</td>')
            if not dense: cells.append('<td class="num dim">—</td>')
            cells += ['<td class="num dim">—</td>'] * (2 if dense else 3)
            cells += [f'<td class="num dim">{money(r[k])}</td>' for k in ('min','attack','other')]
        else:
            cells.append(f'<td class="num"><input class="cell" value="{r["balance"]:.2f}"></td>')
            if not dense:
                cells.append(f'<td class="num dim">'
                             f'{pct(r["usage"]) if r["usage"] is not None else "—"}</td>')
            cells.append(f'<td class="num dim">{money(r["minAmt"]) if r["minAmt"] else "—"}</td>')
            if not dense: cells.append(f'<td class="num dim">{shortdate(r["close"])}</td>')
            cells.append(f'<td class="num dim">{shortdate(r["due"])}</td>')
            cells += [cellin(r['min']), cellin(r['attack'], 'is-attack'), cellin(r['other'])]
        cells.append(f'<td class="num">{money(r["total"])}</td>')
        cells.append(f'<td class="num dim">{money(r["interest"]) if r["debt"] else "—"}</td>')
        cells.append(f'<td class="num">{money(r["after"])}</td>')
        if not dense:
            cells += [f'<td class="num dim">'
                      f'{pct(r["usageAfter"]) if r["usageAfter"] is not None else "—"}</td>',
                      f'<td class="num dim">'
                      f'{money(r["availAfter"]) if r["availAfter"] is not None else "—"}</td>',
                      f'<td class="num dim">{m0(r["sixMo"]) if r["sixMo"] is not None else "—"}</td>']
        body.append(f'<tr class="{cls}">{"".join(cells)}</tr>')

    t = D['cardTotals']
    tot = ['<th scope="row">Total</th>']
    if not dense: tot += [f'<td class="num">{m0(t["limit"])}</td>', '<td class="num"></td>']
    tot.append(f'<td class="num">{money(t["balance"])}</td>')
    if not dense: tot.append(f'<td class="num">{pct(t["usage"])}</td>')
    tot += ['<td class="num"></td>'] * (2 if dense else 3)
    tot += [f'<td class="num">{money(t[k])}</td>'
            for k in ('min','attack','other','total','interest')]
    tot.append(f'<td class="num">{money(t["after"])}</td>')
    if not dense:
        tot += [f'<td class="num">{pct(t["usageAfter"])}</td>',
                f'<td class="num">{money(t["availAfter"])}</td>', '<td class="num"></td>']
    body.append(f'<tr class="tot">{"".join(tot)}</tr>')

    head = ''.join(f'<th scope="col"{"" if i == 0 else " class=num"}>{c}</th>'
                   for i, c in enumerate(cols))
    return (f'<div class="gridwrap"><table class="{"grid" if dense else "grid full"}">'
            f'<thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table></div>')

def week_page(dense):
    return f"""<main class="page">
  <header class="masthead">
    <div><h1 class="page-title">{esc(D['label'])}</h1>
      <div class="dateline">{esc(D['dateline'])}</div></div>
    <div class="controls">
      <button class="ctl" aria-label="Previous week">←</button>
      <span class="jump"><select aria-label="Jump to week">
        <option selected disabled>Jump to week</option>
        <option>{esc(D['label'])}</option></select><span class="caret"><svg width="9" height="9"
        viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.6"
        stroke-linecap="round" stroke-linejoin="round"><path d="M2.5 4.5L6 8l3.5-3.5"/></svg>
        </span></span>
      <button class="ctl" aria-label="Next week">→</button>
      <button class="ctl ctl-primary">+ Next week</button>
    </div>
  </header>
  <div class="hero-row">
    <div class="hero-label">Paycheck in</div>
    <div class="hero-figure"><span class="mark">$</span>
      <input value="{D['income']:.2f}" aria-label="Paycheck in"></div>
    <div class="hero-note">{esc(D['incomeAccount'])}</div>
  </div>
  {strip()}
  <section class="band" aria-labelledby="alloc-h">
    <h2 class="sect-label" id="alloc-h">Where the paycheck goes</h2>
    {alloc_bar()}
  </section>
  <section class="band" aria-labelledby="attn-h">{checks()}</section>
  <section class="band" aria-labelledby="funds-h">
    <h2 class="sect-label" id="funds-h">Sinking funds</h2>{funds()}
  </section>
  <section class="band" aria-labelledby="grid-h">
    {sect('Allocation', 'grid-h', seg(['Compact','Full sheet'],
                                      'Compact' if dense else 'Full sheet'))}
    {grid(dense)}
  </section>
</main>"""

# ── Attack ───────────────────────────────────────────────────────────
STRATS = ['Avalanche','Snowball','My order']
STRAT_KEY = {'Avalanche':'avalanche','Snowball':'snowball','My order':'custom'}

def attack_view(strategy='My order'):
    A = D['attack']; key = STRAT_KEY[strategy]
    ranked = A['ranked'][key]; top = ranked[0]
    cur = A['sims']['current']; av = A['sims']['avalanche']

    if key == 'avalanche':
        why = (f"Highest rate in the stack at <b>{pct(top['apr'],2)}</b>, costing "
               f"<b>{money(top['weekInterest'])}</b> in interest every week it sits there.")
    elif key == 'snowball':
        why = (f"Smallest balance at <b>{money(top['balance'])}</b>. Clearing it frees its "
               f"<b>{money(top['weeklyMin'])}</b>/week minimum for the next one.")
    elif top['kind'] == 'card' and top['limit']:
        why = (f"First in your order. A card at <b>{pct(top['balance']/top['limit'],0)}</b> "
               f"utilization — clearing it moves the number FICO scores, which rate-sorting "
               f"cannot see.")
    else:
        why = "First in your order, ahead of the rate ranking by your own call."

    rows = []
    for i, d in enumerate(ranked):
        used = (f" · {pct(d['balance']/d['limit'],0)} used"
                if d['kind'] == 'card' and d['limit'] else '')
        mn = f" · {money(d['weeklyMin'])}/wk minimum" if d['weeklyMin'] else ''
        rows.append(
          f'<li class="{"lead" if i==0 else ""}"><span class="n">{i+1}</span>'
          f'<span><span class="nm">{esc(d["name"])}</span>'
          f'<div class="meta">{money(d["balance"])}{used} · {pct(d["apr"],2)} APR{mn}</div></span>'
          f'<span class="rt"><div class="rv">{money(d["weekInterest"])}</div>'
          f'<div class="rl">interest / week</div></span></li>')
    for g in A['grace']:
        rows.append(
          f'<li class="pif"><span class="n">PIF</span>'
          f'<span><span class="nm">{esc(g["name"])}</span>'
          f'<div class="meta">{money(g["balance"])} due in full · {pct(g["apr"],2)} APR '
          f'if grace breaks</div></span>'
          f'<span class="rt"><div class="rv">{money(0)}</div>'
          f'<div class="rl">interest / week</div></span></li>')

    ways = [('Avalanche — highest rate first', av),
            ('Snowball — smallest balance first', A['sims']['snowball']),
            ('Your order', A['sims']['custom']),
            ('Repeat this week’s split', cur)]
    finite = [s for _, s in ways if s['weeks']]
    mx = max([s['weeks'] for s in finite] or [520])
    cheapest = min((s['totalInterest'] for s in finite), default=None)
    tl = []
    for name, s in ways:
        w = s['weeks'] or mx
        lead = ' lead' if s['weeks'] and s['totalInterest'] == cheapest else ''
        never = 'never' if not s['weeks'] else ''
        tl.append(f'<div class="tlr{lead}"><div class="tln">{esc(name)}</div>'
                  f'<div class="tlbar"><i class="{never}" '
                  f'style="width:{min(100,max(2,w/mx*100)):.1f}%"></i></div>'
                  f'<div class="tlv">{s["monthsLabel"] if s["weeks"] else "never"}</div></div>')

    onto = A['attackedThisWeek']
    note = (f'This week’s <b>{money(A["attackOnTable"])}</b> is already going to '
            f'{esc(top["name"])}.' if onto == [top['name']] else
            f'This week’s attack is on <b>{esc(", ".join(onto) or "nothing")}</b>. '
            f'{esc(top["name"])} is what your {esc(strategy.lower())} says.')
    heading = ('The stack, in your order' if key == 'custom' else
               'The stack, by what it costs you' if key == 'avalanche' else
               'The stack, by what clears first')

    return f"""<main class="page">
  <header class="masthead">
    <div><h1 class="page-title">Attack</h1>
      <div class="dateline">{esc(D['label'])} · {money(A['attackOnTable'])} on the table</div></div>
    <div class="controls">{seg(STRATS, strategy)}</div>
  </header>
  {hero('This week, put it here', esc(top['name']))}
  <p class="lede">{why}</p>
  <p class="lede muted">{note}</p>
  <section class="band" aria-labelledby="stack-h">
    {sect(heading, 'stack-h')}
    <ul class="rank">{''.join(rows)}</ul>
    <div class="legend"><span class="k">Total bleed <b>{money(A['weeklyBleed'])}</b> per week ·
      <b>{money(A['monthlyBleed'])}</b> per month</span></div>
  </section>
  <section class="band" aria-labelledby="ways-h">
    {sect(f'Same {money(A["budget"])} a week, four ways', 'ways-h')}
    <div class="tl">{''.join(tl)}</div>
  </section>
</main>"""

# ── Payoff ───────────────────────────────────────────────────────────
def monthsdiff(a, b):
    d = a['months'] - b['months']
    if d < 24: return f'{round(d)} mo'
    y, r = divmod(round(d), 12)
    return f'{y}y {r}m' if r else f'{y}y'

def payoff_view(strategy='My order'):
    P = D['payoff']; key = STRAT_KEY[strategy]
    sim = P['compare'][key]; flat = P['flat']

    steps = []
    for st in P['steps']:
        when = (f"lands {st['lands']}" if st['lands']
                else ('not done yet' if st['trigger'] == 'manual' else 'trigger not reached'))
        box = ('checked' if st['fired'] else '') + ('' if st['trigger'] == 'manual' else ' disabled')
        steps.append(
          f'<li class="{"lead" if st["fired"] else ""}">'
          f'<span class="n"><input type="checkbox" {box}></span>'
          f'<span><span class="nm">{esc(st["label"])}</span>'
          f'<div class="meta">{esc(st["note"])} · {esc(when)}</div></span>'
          f'<span class="rt"><div class="rv">+{money(st["weekly"])}</div>'
          f'<div class="rl">per week</div></span></li>')

    clears = sorted(sim['debts'], key=lambda d: (d['paidOff'] is None, d['paidOff'] or 0))
    mx = max([d['paidOff'] for d in clears if d['paidOff']] or [1])
    tl = []
    for i, d in enumerate(clears):
        w = d['paidOff'] or mx
        tl.append(f'<div class="tlr{" lead" if i==0 else ""}">'
                  f'<div class="tln">{esc(d["name"])}</div>'
                  f'<div class="tlbar"><i class="{"never" if not d["paidOff"] else ""}" '
                  f'style="width:{min(100,max(2,w/mx*100)):.1f}%"></i></div>'
                  f'<div class="tlv">{d["clears"] or "never"}</div></div>')

    fin = [P['compare'][k2] for k2 in ('avalanche','snowball','custom') if P['compare'][k2]['weeks']]
    cheap = min((s['totalInterest'] for s in fin), default=None)
    cmp_rows = []
    for label, k2 in [('Avalanche','avalanche'), ('Snowball','snowball'), ('Your order','custom')]:
        s = P['compare'][k2]
        tag = ('<span class="cheapest">cheapest</span>'
               if s['weeks'] and s['totalInterest'] == cheap else '')
        cmp_rows.append(f'<tr class="{"lead" if k2==key else ""}"><td>{label}{tag}</td>'
                        f'<td>{s["debtFree"] or "never"}</td>'
                        f'<td>{round(s["months"]) if s["months"] else "—"}</td>'
                        f'<td>{m0(s["totalInterest"]) if s["weeks"] else "—"}</td></tr>')

    saved = (f'{monthsdiff(flat, sim)} sooner' if flat['weeks'] and sim['weeks']
             else ('clears it' if sim['weeks'] else '—'))
    strip_ = '<div class="strip">' + ''.join([
        metric('Weekly debt budget',
               f'<span class="mark">$</span><input class="cell inline" '
               f'value="{P["budget"]:.2f}" aria-label="Weekly debt budget">',
               f'{money(P["floor"])} of that is minimums · rises to {money(sim["endBudget"])}'),
        metric('Interest you’ll pay', m0(sim['totalInterest']),
               f'on {m0(P["debtBalance"])} of principal'),
        metric('What the steps buy you', saved,
               f'against holding {money(P["budget"])} flat'),
    ]) + '</div>'

    return f"""<main class="page">
  <header class="masthead">
    <div><h1 class="page-title">Payoff</h1>
      <div class="dateline">From {esc(D['label'])} · {money(P['debtBalance'])} across
        {P['accounts']} accounts</div></div>
    <div class="controls">{seg(STRATS, strategy)}</div>
  </header>
  {hero('Debt free', esc(sim['debtFree'] or 'Never'),
        f"{sim['monthsLabel']} from now" if sim['weeks']
        else 'the payment cannot outrun the interest')}
  {strip_}
  <section class="band" aria-labelledby="chart-h">
    {sect('Balance from here', 'chart-h')}
    <div class="chart" id="chart"></div>
  </section>
  <section class="band" aria-labelledby="steps-h">
    {sect('Attack steps up as these land', 'steps-h')}
    <p class="lede muted">Each one permanently frees a weekly line. The date above already
      assumes them — untick a step to see what it is worth.</p>
    <ul class="rank">{''.join(steps)}</ul>
  </section>
  <section class="band" aria-labelledby="clears-h">
    {sect('What clears when', 'clears-h')}
    <div class="tl">{''.join(tl)}</div>
  </section>
  <section class="band" aria-labelledby="cmp-h">
    {sect(f'Three orders at {money(P["budget"])} a week', 'cmp-h')}
    <table class="cmp"><thead><tr><th>Order</th><th>Debt free</th><th>Months</th>
      <th>Total interest</th></tr></thead><tbody>{''.join(cmp_rows)}</tbody></table>
  </section>
</main>"""

CHART_JS = """
(function(){
  const S=%s, el=document.getElementById('chart'); if(!el) return;
  const W=el.clientWidth||900, H=260, PL=64, PR=16, PT=12, PB=30;
  const hi=Math.max(...S.map(p=>p.total));
  const step=Math.pow(10,Math.floor(Math.log10(hi/4)));
  const tick=Math.ceil(hi/4/step)*step, ticks=[];
  for(let v=0;v<=hi+tick*0.001;v+=tick) ticks.push(v);
  const top=ticks[ticks.length-1];
  const X=i=>PL+(W-PL-PR)*(i/(S.length-1)), Y=v=>PT+(H-PT-PB)*(1-v/top);
  const line=S.map((p,i)=>(i?'L':'M')+X(i).toFixed(1)+','+Y(p.total).toFixed(1)).join('');
  const money=n=>'$'+Math.round(n).toLocaleString('en-US');
  el.innerHTML='<svg viewBox="0 0 '+W+' '+H+'" role="img" aria-label="Remaining balance from '
    +S[0].t+' to '+S[S.length-1].t+'">'
    +ticks.map(t=>'<line class="gridline" x1="'+PL+'" x2="'+(W-PR)+'" y1="'+Y(t).toFixed(1)
      +'" y2="'+Y(t).toFixed(1)+'"/><text class="axl" x="'+(PL-10)+'" y="'+(Y(t)+4).toFixed(1)
      +'" text-anchor="end">'+money(t)+'</text>').join('')
    +S.map((p,i)=>i%%Math.ceil(S.length/6)===0||i===S.length-1
      ?'<text class="axl" x="'+X(i).toFixed(1)+'" y="'+(H-8)+'" text-anchor="middle">'+p.x+'</text>':'').join('')
    +'<path class="chartline" d="'+line+'"/>'
    +'<g class="hov"><line class="crosshair" y1="'+PT+'" y2="'+(H-PB)+'"/>'
    +'<circle class="chartdot" r="4"/></g></svg><div class="tip"></div>';
  const svg=el.querySelector('svg'), hov=el.querySelector('.hov'), tip=el.querySelector('.tip');
  const cross=hov.querySelector('line'), dot=hov.querySelector('circle');
  const show=i=>{const p=S[i], box=svg.getBoundingClientRect(), sx=W/box.width;
    cross.setAttribute('x1',X(i)); cross.setAttribute('x2',X(i));
    dot.setAttribute('cx',X(i)); dot.setAttribute('cy',Y(p.total));
    tip.innerHTML='<div class="tt">'+p.t+'</div>'
      +'<div class="tr"><span>Remaining</span><span class="tv">'+money(p.total)+'</span></div>'
      +'<div class="tr"><span>From now</span><span class="tv">'+p.months+'</span></div>';
    const w=tip.offsetWidth;
    tip.style.left=Math.max(4,Math.min(box.width-w-4,X(i)/sx-w/2))+'px';
    tip.style.top=Math.max(2,Y(p.total)/sx-tip.offsetHeight-14)+'px';};
  svg.addEventListener('pointermove',e=>{const b=svg.getBoundingClientRect();
    show(Math.max(0,Math.min(S.length-1,
      Math.round(((e.clientX-b.left)*(W/b.width)-PL)/((W-PL-PR)/(S.length-1))))));});
  show(Math.round(S.length*0.42));
})();
"""

# ── Plan ─────────────────────────────────────────────────────────────
def plan_view():
    P = D['plan']
    now = [c for c in P['calendar'] if c['overdue']] + \
          [c for c in P['calendar'] if c['soon']][:2]

    # R9 on dated rows: a date that has passed is wrong and takes oxblood; a date
    # that is coming is worth noticing and takes attention. With nothing overdue
    # the whole list used to render red, so the colour carried no information.
    needs = ''
    if now:
        rows = ''.join(
          f'<li class="attn-row{"" if c["overdue"] else " upcoming"}">'
          f'<p><span class="{"account" if c["overdue"] else "when"}">{shortdate(c["d"])}</span> — '
          f'{esc(c["t"])}' + (f'. {esc(c["n"])}' if c['n'] else '') + '</p></li>' for c in now)
        needs = (f'<section class="band tight" aria-labelledby="now-h">'
                 f'{sect("Needs you now", "now-h")}<ul class="attn-list">{rows}</ul></section>')

    order, n = [], len(P['order'])
    for i, o in enumerate(P['order']):
        used = (f" · {pct(o['balance']/o['limit'],0)} used"
                if o['kind'] == 'card' and o['limit'] and o['balance'] else '')
        meta = ('nothing owed' if o['clear'] else
                f"{money(o['balance'])}{used} · {pct(o['apr'],2)} APR · "
                f"{money(o['weekInterest'])}/wk")
        clear = '<span class="state clear">clear</span>' if o['clear'] else ''
        order.append(
          f'<li class="{"lead" if i==0 else ""}"><span class="n">{i+1}</span>'
          f'<span><span class="nm">{esc(o["name"])}</span>{clear}'
          f'<div class="meta">{meta}</div></span>'
          f'<span class="rt reorder">'
          f'<button aria-label="Move {esc(o["name"])} up"{" disabled" if i==0 else ""}>↑</button>'
          f'<button aria-label="Move {esc(o["name"])} down"'
          f'{" disabled" if i==n-1 else ""}>↓</button></span></li>')

    openq = ''.join(
      f'<li class="{"done" if o["done"] else ""}">'
      f'<span><input type="checkbox" {"checked" if o["done"] else ""}></span>'
      f'<span><div class="pt">{esc(o["t"])}</div>'
      + (f'<div class="pn">{esc(o["n"])}</div>' if o['n'] else '') + '</span></li>'
      for o in P['open'])

    def cal_rows(items):
        return ''.join(
          f'<li class="{"done" if c["done"] else ""}">'
          f'<span><input type="checkbox" {"checked" if c["done"] else ""}></span>'
          f'<span class="pd{" is-overdue" if c["overdue"] else ""}">{shortdate(c["d"])}</span>'
          f'<span><div class="pt">{esc(c["t"])}</div>'
          + (f'<div class="pn">{esc(c["n"])}</div>' if c['n'] else '') + '</span></li>'
          for c in items)

    soon  = [c for c in P['calendar'] if c['soon']]
    later = [c for c in P['calendar'] if not c['soon'] and not c['overdue'] and not c['done']]
    done  = [c for c in P['calendar'] if c['done']]

    ref = ''
    if P['ref']:
        rrows = ''.join(
          f'<tr><td>{esc(r["name"])}</td><td>{money(r["sheet"])}</td>'
          f'<td>{money(r["handoff"])}</td>'
          f'<td>{"—" if abs(r["delta"])<0.005 else ("+" if r["delta"]>0 else "")+money(r["delta"])}</td></tr>'
          for r in P['ref']['rows'])
        mins = ''.join(
          f'<li class="attn-row upcoming"><p><span class="account">{esc(m["name"])}</span> '
          f'minimum is an estimate — <span class="fig">{money(m["est"])}</span>, {esc(m["n"])}. '
          f'Real number lands when the statement closes {shortdate(m["when"])}.</p></li>'
          for m in P['minsToVerify'])
        ref = f"""<section class="band" aria-labelledby="ref-h">
    {sect(f'Handoff snapshot · {shortdate(P["ref"]["asOf"])}', 'ref-h')}
    <p class="lede muted">Reference only — <b>the weekly sheet is the source of truth</b>.
      Rows that differ are usually the sheet being ahead of the doc.</p>
    <table class="cmp"><thead><tr><th>Account</th><th>Sheet</th><th>Handoff</th>
      <th>Δ</th></tr></thead><tbody>{rrows}</tbody></table>
    <ul class="attn-list" style="margin-top:var(--space-3)">{mins}</ul>
  </section>"""

    outstanding = sum(1 for o in P['open'] if not o['done'])
    return f"""<main class="page">
  <header class="masthead">
    <div><h1 class="page-title">Plan</h1>
      <div class="dateline">{esc(P['source'])}</div></div>
    <div class="controls">
      <button class="ctl">+ Date</button><button class="ctl">+ Open item</button>
    </div>
  </header>
  {needs}
  <section class="band{'' if needs else ' tight'}" aria-labelledby="order-h">
    {sect('Payoff order', 'order-h')}
    <p class="lede muted">What <b>My order</b> follows on Attack and Payoff. Rate-sorting
      cannot see utilization or a freed minimum; this can.</p>
    <ul class="rank">{''.join(order)}</ul>
  </section>
  <section class="band" aria-labelledby="open-h">
    {sect('Open items', 'open-h', f'<span class="count">{outstanding} left</span>')}
    <ul class="plan-list">{openq}</ul>
  </section>
  <section class="band" aria-labelledby="cal-h">
    {sect('Calendar', 'cal-h')}
    <h3 class="sub-label">Next four weeks</h3>
    <ul class="plan-list dated">{cal_rows(soon)}</ul>
    <h3 class="sub-label">After that</h3>
    <ul class="plan-list dated">{cal_rows(later)}</ul>
    {'<h3 class="sub-label">Done</h3><ul class="plan-list dated">' + cal_rows(done) + '</ul>' if done else ''}
  </section>
  {ref}
</main>"""

# ── Accounts ─────────────────────────────────────────────────────────
KINDS = ['income','cash','savings','loan','card']
# Only fields the registry actually holds. minAmt is populated on 0 of 20 accounts
# — minimums live per-week in the grid's "Min due", not here — and weeklyOutflow on
# 1 of 20, so it rides as an inline note rather than a column of em-dashes.
SHAPE_DEBT  = [('Limit','limit'), ('APR %','apr')]
SHAPE_MONEY = []
DEBT_GROUPS = {'Loans','Credit cards'}

def accounts_view():
    A = D['accounts']
    live = sum(len(g['rows']) for g in A['groups'])
    blocks, empty, total = [], 0, 0
    for g in A['groups']:
        shape = SHAPE_DEBT if g['label'] in DEBT_GROUPS else SHAPE_MONEY
        cols = '1fr 108px ' + ' '.join(['112px'] * len(shape)) + ' 88px'
        head = ''.join(f'<span>{esc(h)}</span>' for h, _ in shape)
        rows = []
        for a in g['rows']:
            sel = ''.join(f'<option{" selected" if kk==a["kind"] else ""}>{kk.title()}</option>'
                          for kk in KINDS)
            fields = []
            for label, key in shape:
                v = a[key]
                v = (round(v*100, 2) if v else '') if key == 'apr' else (v or '')
                total += 1
                if v == '': empty += 1
                fields.append(f'<input class="field num" value="{v}" placeholder="—" '
                              f'aria-label="{esc(label)} for {esc(a["name"])}">')
            notes = []
            if a['weeklyOutflow']: notes.append(f'{money(a["weeklyOutflow"])}/wk out')
            if a['target']:        notes.append(f'target {m0(a["target"])}')
            if a['grace']:         notes.append('in grace')
            note = (f'<div class="rowmeta">{esc(" · ".join(notes))}</div>') if notes else ''
            rows.append(
              f'<div class="acct-row" style="grid-template-columns:{cols}">'
              f'<span><input class="field" value="{esc(a["name"])}" aria-label="Name">{note}</span>'
              f'<select class="field" aria-label="Type">{sel}</select>'
              + ''.join(fields) +
              f'<button class="archive" aria-label="Archive {esc(a["name"])}">Archive</button></div>')
        blocks.append(f'<h3 class="sub-label">{esc(g["label"])}</h3>'
                      + (f'<div class="acct-head" style="grid-template-columns:{cols}">'
                         f'<span>Name</span><span>Type</span>{head}<span></span></div>'
                         if shape else '')
                      + ''.join(rows))
    print(f'  accounts: {empty} empty of {total} data cells'
          + (f' ({empty/total*100:.0f}%)' if total else ''))
    return f"""<main class="page">
  <header class="masthead">
    <div><h1 class="page-title">Accounts</h1>
      <div class="dateline">{live} active · {len(A['archived'])} archived</div></div>
    <div class="controls"><button class="ctl ctl-primary">+ Account</button></div>
  </header>
  <section class="band tight" aria-labelledby="acct-h">
    {sect('Registry', 'acct-h')}
    <p class="lede muted">Defined once. Change an APR here and every week recalculates.
      Minimums and due dates belong to a week, so they are edited in the grid on
      <b>This Week</b>, not here.</p>
    {''.join(blocks)}
  </section>
  <section class="band" aria-labelledby="data-h">
    {sect('Data', 'data-h')}
    <p class="lede muted">Everything lives in this browser and in your own Supabase
      project. Export before clearing site data or moving machines.</p>
    <div class="actions">
      <button>Export backup</button><button>Import backup</button>
      <button>Export CSV</button><button class="danger">Reset to imported sheet</button>
    </div>
  </section>
</main>"""

# ── History ──────────────────────────────────────────────────────────
METRICS = [('Total debt','debt',m0), ('Card balance','cards',m0),
           ('Utilization','util',pct), ('Paid to debt','paid',m0),
           ('Attack','attack',m0), ('Paycheck','income',m0)]

def spark_svg(pts, up):
    if len(pts) < 2: return ''
    lo, hi = min(pts + [0]), max(pts + [1])
    W, H = 200, 34
    X = lambda i: W * i / (len(pts) - 1)
    Y = lambda v: H - 2 - (H - 6) * ((v - lo) / (hi - lo or 1))
    d = ''.join(('L' if i else 'M') + f'{X(i):.1f},{Y(v):.1f}' for i, v in enumerate(pts))
    k = 'up' if up else 'down'
    return (f'<svg viewBox="0 0 {W} {H}" preserveAspectRatio="none" aria-hidden="true">'
            f'<path class="sparkline {k}" d="{d}"/>'
            f'<circle class="sparkdot {k}" cx="{X(len(pts)-1):.1f}" '
            f'cy="{Y(pts[-1]):.1f}" r="2.2"/></svg>')

def history_view(metric='Total debt'):
    H = D['history']
    label, key, fmt = next(m for m in METRICS if m[0] == metric)
    series = [{'x': w['x'], 't': w['t'], 'v': w[key]} for w in H['weeks']]
    now, first = series[-1]['v'], series[0]['v']
    delta = round(now - first, 2)

    strip_ = '<div class="strip">' + ''.join([
        metric_tile(f'{label} now', fmt(now), H['span']['to']),
        metric_tile(f'Change over {H["span"]["n"]} weeks',
                    ('+' if delta > 0 else '') + fmt(delta),
                    f'from {fmt(first)} at {H["span"]["from"]}',
                    'is-over' if delta > 0 else 'is-settled'),
        metric_tile('Paid to debt, all weeks', m0(H['totals']['paidAll']),
                    f'{m0(H["totals"]["attackAll"])} of it attack'),
        metric_tile('Unplanned drift', m0(H['drift']),
                    'balances landing above projection',
                    'is-idle' if H['drift'] > 0 else ''),
    ]) + '</div>'

    sparks = ''.join(
        f'<div class="spark"><div class="sn"><span>{esc(s["name"])}</span>'
        f'<span class="sv">{m0(s["now"])}</span></div>'
        f'<div class="sd"><span class="{"up" if s["delta"] > 0 else "down"}">'
        f'{("+" if s["delta"] > 0 else "")}{m0(s["delta"])}</span>'
        + (f' · {pct(s["used"], 0)} used' if s['used'] is not None else '') + '</div>'
        + spark_svg(s['pts'], s['delta'] > 0) + '</div>'
        for s in H['spark'])

    rows = ''.join(
        f'<tr class="{"planned" if w["planned"] else ""}"><td>{esc(w["x"])}</td>'
        f'<td>{m0(w["income"])}</td><td>{m0(w["allocated"])}</td>'
        f'<td>{money(w["unallocated"])}</td><td>{m0(w["cards"])}</td>'
        f'<td>{pct(w["util"], 0)}</td><td>{m0(w["paid"])}</td>'
        f'<td>{m0(w["attack"]) if w["attack"] else "—"}</td></tr>'
        for w in reversed(H['weeks']))

    return f"""<main class="page">
  <header class="masthead">
    <div><h1 class="page-title">History</h1>
      <div class="dateline">{H['span']['n']} weeks · {esc(H['span']['from'])} to
        {esc(H['span']['to'])}</div></div>
    <div class="controls">
      <span class="jump"><select aria-label="Metric">
        {''.join(f'<option{" selected" if m[0]==metric else ""}>{m[0]}</option>' for m in METRICS)}
      </select><span class="caret"><svg width="9" height="9" viewBox="0 0 12 12" fill="none"
        stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
        <path d="M2.5 4.5L6 8l3.5-3.5"/></svg></span></span>
      {seg(['All','This year','13 weeks'], 'All')}
    </div>
  </header>
  {strip_}
  <section class="band" aria-labelledby="hchart-h">
    {sect(esc(label), 'hchart-h')}
    <div class="chart" id="chart"></div>
  </section>
  <section class="band" aria-labelledby="spark-h">
    {sect(f'Each card, {H["span"]["n"]} weeks', 'spark-h')}
    <div class="sparks">{sparks}</div>
  </section>
  <section class="band" aria-labelledby="wk-h">
    {sect('Every week', 'wk-h')}
    <table class="cmp"><thead><tr><th>Week</th><th>Paycheck</th><th>Assigned</th>
      <th>Left</th><th>Card balance</th><th>Util</th><th>To debt</th><th>Attack</th>
    </tr></thead><tbody>{rows}</tbody></table>
  </section>
</main>"""

def metric_tile(label, value, note=None, state=''):
    return metric(label, value, note, state)
HISTORY_JS = """
(function(){
  const S=%s, el=document.getElementById('chart'); if(!el) return;
  const W=el.clientWidth||900, H=260, PL=68, PR=16, PT=12, PB=30;
  const hi=Math.max(...S.map(p=>p.v));
  const st=Math.pow(10,Math.floor(Math.log10(hi/4)));
  const tk=Math.ceil(hi/4/st)*st, ticks=[];
  for(let v=0;v<=hi+tk*0.001;v+=tk) ticks.push(v);
  const top=ticks[ticks.length-1];
  const X=i=>PL+(W-PL-PR)*(i/(S.length-1)), Y=v=>PT+(H-PT-PB)*(1-v/top);
  const line=S.map((p,i)=>(i?'L':'M')+X(i).toFixed(1)+','+Y(p.v).toFixed(1)).join('');
  const money=n=>'$'+Math.round(n).toLocaleString('en-US');
  el.innerHTML='<svg viewBox="0 0 '+W+' '+H+'" role="img" aria-label="Total debt across '
    +S.length+' weeks, '+money(S[0].v)+' to '+money(S[S.length-1].v)+'">'
    +ticks.map(t=>'<line class="gridline" x1="'+PL+'" x2="'+(W-PR)+'" y1="'+Y(t).toFixed(1)
      +'" y2="'+Y(t).toFixed(1)+'"/><text class="axl" x="'+(PL-10)+'" y="'+(Y(t)+4).toFixed(1)
      +'" text-anchor="end">'+money(t)+'</text>').join('')
    +S.map((p,i)=>i%%Math.ceil(S.length/7)===0||i===S.length-1
      ?'<text class="axl" x="'+X(i).toFixed(1)+'" y="'+(H-8)+'" text-anchor="middle">'+p.x+'</text>':'').join('')
    +'<path class="chartline" d="'+line+'"/>'
    +'<g class="hov"><line class="crosshair" y1="'+PT+'" y2="'+(H-PB)+'"/>'
    +'<circle class="chartdot" r="4"/></g></svg><div class="tip"></div>';
  const svg=el.querySelector('svg'), hov=el.querySelector('.hov'), tip=el.querySelector('.tip');
  const cross=hov.querySelector('line'), dot=hov.querySelector('circle');
  const show=i=>{const p=S[i], b=svg.getBoundingClientRect(), sx=W/b.width;
    cross.setAttribute('x1',X(i)); cross.setAttribute('x2',X(i));
    dot.setAttribute('cx',X(i)); dot.setAttribute('cy',Y(p.v));
    tip.innerHTML='<div class="tt">'+p.t+'</div>'
      +'<div class="tr"><span>Total debt</span><span class="tv">'+money(p.v)+'</span></div>';
    const w=tip.offsetWidth;
    tip.style.left=Math.max(4,Math.min(b.width-w-4,X(i)/sx-w/2))+'px';
    tip.style.top=Math.max(2,Y(p.v)/sx-tip.offsetHeight-14)+'px';};
  svg.addEventListener('pointermove',e=>{const b=svg.getBoundingClientRect();
    show(Math.max(0,Math.min(S.length-1,
      Math.round(((e.clientX-b.left)*(W/b.width)-PL)/((W-PL-PR)/(S.length-1))))));});
  show(Math.round(S.length*0.62));
})();
"""

# ── Rail ─────────────────────────────────────────────────────────────
RAIL_NAV = [('This Week','1'), ('Attack','2'), ('Payoff','3'),
            ('Plan','4'), ('History','5'), ('Accounts','6')]

def rail(current='This Week'):
    nav = ''.join('<a href="#"%s>%s<span class="key">%s</span></a>'
                  % (' aria-current="page"' if n == current else '', n, k)
                  for n, k in RAIL_NAV)
    s = D['strip']
    return f"""<nav class="rail" aria-label="Sections">
  <div class="brand">Money</div>
  <div class="nav">{nav}</div>
  <div class="railfoot">
    <div class="railstat"><span class="wk">{esc(D['label'])}</span><br>
      {m0(s['debtBalance'])} owed<br>{pct(s['usage'])} utilization</div>
    <div class="sync"><span class="dot"></span>Synced 2 min ago</div>
    <div class="railact"><button>Export backup</button><button>Import backup</button>
      <button>Sign out</button></div>
  </div>
</nav>"""

JS = ("const h=document.querySelector('.ok-head'),l=document.getElementById('ok-list');"
      "if(h)h.addEventListener('click',()=>{const o=h.getAttribute('aria-expanded')==='true';"
      "h.setAttribute('aria-expanded',String(!o));l.hidden=o;});"
      "document.querySelectorAll('.seg button').forEach(b=>b.addEventListener('click',()=>{"
      "b.parentElement.querySelectorAll('button').forEach(x=>x.setAttribute('aria-pressed','false'));"
      "b.setAttribute('aria-pressed','true');}));"
      "document.querySelectorAll('.nav a').forEach(a=>a.addEventListener('click',e=>{e.preventDefault();"
      "document.querySelectorAll('.nav a').forEach(x=>x.removeAttribute('aria-current'));"
      "a.setAttribute('aria-current','page');}));")

STAMP = ("<!-- Generated by build-preview.py from preview-data.json, which is the app "
         "engine's own output. Do not hand-edit: run `bun preview-data.js > "
         "preview-data.json && python3 build-preview.py`. -->")

def write(path, title, css, body, extra_js=''):
    pathlib.Path(path).write_text(
        f'<!DOCTYPE html>\n{STAMP}\n<html lang="en"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{title}</title><link rel="stylesheet" href="tokens.css?v={D["income"]}">'
        f'<style>{css}</style></head><body>{BANNER}{body}'
        f'<script>{JS}{extra_js}</script></body></html>')
    print(f'  {path}')

CSS_ALL = CSS_BASE + CSS_RAIL
print('rendered from the engine:')
write('preview-this-week.html',      'This Week — preview', CSS_BASE, week_page(True))
write('preview-this-week-full.html', 'Full sheet — preview', CSS_BASE, week_page(False))
write('preview-rail.html',           'Rail — preview', CSS_ALL,
      f'<div class="shell">{rail()}{week_page(True)}</div>')
write('preview-attack.html',         'Attack — preview', CSS_ALL,
      f'<div class="shell">{rail("Attack")}{attack_view()}</div>')
write('preview-payoff.html',         'Payoff — preview', CSS_ALL,
      f'<div class="shell">{rail("Payoff")}{payoff_view()}</div>',
      extra_js=CHART_JS % json.dumps(D['payoff']['series']))
write('preview-plan.html',           'Plan — preview', CSS_ALL,
      f'<div class="shell">{rail("Plan")}{plan_view()}</div>')
write('preview-accounts.html',       'Accounts — preview', CSS_ALL,
      f'<div class="shell">{rail("Accounts")}{accounts_view()}</div>')
write('preview-history.html',        'History — preview', CSS_ALL,
      f'<div class="shell">{rail("History")}{history_view()}</div>',
      extra_js=HISTORY_JS % json.dumps(
          [{'x': w['x'], 't': w['t'], 'v': w['debt']} for w in D['history']['weeks']]))
print(f"\n  allocation segments sum to {money(sum(D['alloc'].values()))} "
      f"against a {money(D['income'])} paycheck")

