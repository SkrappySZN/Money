# Money

A weekly zero-based allocation ledger, in one HTML file. No build step, no server,
no account — everything lives in your own browser's local storage and nothing is
ever uploaded.

**Live:** https://skrappyszn.github.io/Money/

It opens empty. Import a backup, or start from scratch and add your accounts.

## What it does

Built to replace a spreadsheet with one tab per pay week, copied forward by hand.
Here the accounts are defined once and every week reflows around them.

- **This Week** — paycheck in at the top, every account below it, and a Min / Attack /
  Other split on each row. The balance check reads *Balanced* only at exactly $0.
  **+ Next week** rolls everything forward: balances projected with real daily-rate
  interest, statement and due dates advanced a month, sinking funds and recurring
  minimums carried over. Correct a balance the bank disagrees with and the row tags
  the gap, so interest and unplanned spend stay separable.
- **Attack** — where the extra dollars do the most good this week. Cards in a grace
  period are pinned out of the ranking, because paying one *partially* is what ends grace.
- **Payoff** — a week-by-week simulation with the snowball rolling forward as each
  account clears. Budget steps switch on as their triggers land, so a plan where the
  payment rises over time is modelled honestly.
- **Plan** — your payoff order, the budget steps, a calendar, and open questions.
  Anything landing inside the current pay week surfaces in This Week's checks.
- **History** — every metric over every week, a sparkline per card, and the full table.
- **Accounts** — the registry. Add a card, archive a closed one, change an APR;
  every week recalculates. History keeps archived accounts.

`1`–`6` switch tabs. `[` and `]` step through weeks.

## Getting your data in and out

**Export backup** writes a JSON file with everything — accounts, weeks, and plan.
**Import backup** reads it back. That is how you move between devices, since local
storage is per-browser. **Export CSV** gives you every week × every account, flat.

## Sync

Optional. With `SUPABASE` filled in at the top of the file, the sidebar gains a
sign-in button; leave it empty and the app never touches the network.

Login is an emailed magic link — no password to remember or leak. Your whole ledger
is one row in a `ledger` table, reachable only by the account that owns it:

```sql
create policy ledger_select_own on public.ledger
  for select using (auth.uid() = user_id);
```

That is why the publishable key can ship in a public page. It is a key to the front
door of a building where every flat has its own lock.

Writes are debounced 2.5s, so entering a week's numbers is one write rather than forty.
Each one is compare-and-set on a `version` column: if another device saved in the
meantime, the write **fails instead of overwriting**, and you get a prompt naming both
sides — "Here: 40 weeks, saved 2 min ago. There: 41 weeks, saved just now" — and pick.
It never guesses, and it never uploads an empty ledger over a real one.

localStorage stays the working copy, so the app opens and works offline and pushes
when it can.

### Setting it up for a new project

Run `supabase-setup.sql` in the SQL editor, add the site URL under
Authentication → URL Configuration, then put the project URL and publishable key
into the `SUPABASE` block.

## Working on it

`index.html` is the local copy and holds real data. The published copy is built from
it with every seed block emptied:

```
python3 build.py      # index.html -> docs/index.html, seeds stripped
```

The build refuses to write an output that still contains personal data, and a
pre-commit hook blocks the same thing at commit time. `index.html` is gitignored.
