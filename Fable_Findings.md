# Fable Findings — n8n + Ollama Financial Reporting Pipeline

*Reviewed 2026-07-04 on branch `HFA-068-1-ollama-reporting-poc`.*

This document reviews the current n8n → Ollama reporting POC, identifies the gaps
between "reports get written to disk" and "reports get delivered into this repo,"
and recommends concrete changes for report quality and agent-friendly `.md` output.

---

## 1. What exists today (verified)

The pipeline is real and mostly healthy:

| Piece | State |
|---|---|
| `n8n/hourly_ollama_reports.workflow.json` | Schedule (every 30 min) → `executeCommand` runs `sandbox_ollama.py` with the project venv → IF on exit code → one summary email per run. Currently `"active": false` and the SMTP credential is still the `REPLACE_WITH_YOUR_SMTP_CREDENTIAL_ID` placeholder. |
| `sandbox_ollama.py` | Solid POC. Gathers price history, `_build_stock_data` analytics, Markov forecast, analyst data, and news per ticker; builds a grounded prompt; calls `qwen3:4b` via `/api/generate` with `think: false`, temp 0.3, `num_ctx` 8192; strips leaked reasoning; writes `reports/{TICKER}_{YYYY-MM-DD}.md`; deletes older files per ticker; logs tok/s. |
| `news_scraper.py` | Free Yahoo/Google RSS aggregation (Finviz opt-in), normalized to the `get_news` shape, deduped, newest-first, failure-isolated. Good citizen headers/timeouts. |
| `reports/_TEMPLATE.md` | Human-readable spec of the report structure. Tracked in git. |
| Ollama server | Confirmed running (v0.30.11) with `qwen3:4b` pulled — the exact model the script and workflow notes expect. |

**The core gap:** generated reports never reach the repo. They are written to
`reports/` in the working tree, are *not* gitignored, but nothing ever commits or
pushes them. The n8n workflow ends at an email. "Sent to this repo" is the one
step that doesn't exist yet.

---

## 2. Recommended pathway: reports → repo

### 2a. Switch to stable filenames first (prerequisite)

Today's `{TICKER}_{YYYY-MM-DD}.md` + delete-old-files scheme is hostile to git:
every day each ticker produces a **file deletion + a new untracked file**, so
history becomes add/delete churn and you can never `git log` one ticker's report
over time.

Change `write_report()` to a **stable path per ticker**:

```
reports/MU.md          ← overwritten each run
reports/AAPL.md
reports/INDEX.md       ← regenerated each run (see §4)
```

The generation timestamp already lives in the file header, so nothing is lost.
`_delete_old_reports()` becomes unnecessary (keep it for one release to sweep
legacy dated files, then remove). With stable names, `git diff reports/MU.md`
shows exactly what changed between runs — which is also the best possible input
for review by a human or an agent.

### 2b. Add a "Commit & Push Reports" step after generation

Two placement options; **the n8n node is the better fit** because git is
orchestration, not report logic, and failures become visible in n8n executions:

Add an `executeCommand` node between **Generate Reports** and **Failed?**
(success path only — see wiring note below):

```
git -C "C:\...\Hatfield_Financial" add reports/*.md
git -C "C:\...\Hatfield_Financial" diff --cached --quiet || git -C "C:\...\Hatfield_Financial" commit -m "reports: automated Ollama run" && git -C "C:\...\Hatfield_Financial" push origin auto/ollama-reports
```

Key decisions inside that one-liner:

- **`diff --cached --quiet ||`** — commit only when content actually changed.
  With a 30-minute cadence and mostly-daily data, many runs will produce
  identical reports; this prevents empty/no-op commits from failing the node.
- **Dedicated branch `auto/ollama-reports`**, not `main`. Automated half-hourly
  commits on `main` bury human history and fight your PR workflow. A dedicated
  branch keeps the full report history greppable, and you can fast-forward or
  cherry-pick a snapshot into `main` whenever you want one. Create it once:
  `git branch auto/ollama-reports && git push -u origin auto/ollama-reports`.
  ⚠️ The n8n step must then run against a **separate worktree**
  (`git worktree add C:\ollama-reports-worktree auto/ollama-reports`) so the
  automation never touches the branch you're actively coding on. Point
  `OUTPUT_DIR` (or a `--output-dir` flag) at that worktree's `reports/`.
- **Commit only on success** — wire this node off the `Failed?` = false branch,
  *before* the email node, so a run that errored never pushes half-written
  reports. (Today both IF branches feed the same email node, which makes the IF
  effectively decorative — the commit node gives the success branch a real job.)
- **Auth**: you're already pushing as `Tyler_Hatfield` via Git Credential
  Manager on this machine; the n8n `executeCommand` runs as the same Windows
  user, so no extra credentials are needed. Do **not** embed a PAT in the
  workflow JSON.

### 2c. Alternative considered (and why not)

- **Committing from inside `sandbox_ollama.py`** — works, but mixes publishing
  with generation, hides git failures inside the script log, and makes local
  manual runs (`python sandbox_ollama.py`) unexpectedly create commits. Rejected.
- **A separate reports-only repo** — cleanest history isolation, but adds a
  second remote/checkout to maintain for a solo project. Revisit if report
  volume grows to full S&P 500.

### 2d. One environment caveat worth knowing

This repo lives inside **OneDrive**. A `.git` directory receiving automated
commits every 30 minutes is a known OneDrive corruption/sync-conflict risk
(lock files, partial syncs). The worktree approach in §2b sidesteps this if you
place the worktree *outside* OneDrive (e.g. `C:\ollama-reports-worktree`) —
recommended regardless.

---

## 3. Report quality improvements

Ordered by impact-per-effort:

1. **Skip generation when inputs are unchanged.** Hash the assembled data block
   (`build_prompt` output) and store it in the report's frontmatter (§4). If the
   hash matches the previous run, skip the Ollama call entirely. At a 30-minute
   cadence with daily-granularity fundamentals/Markov and hourly news TTL, most
   runs regenerate identical content — this saves GPU time, keeps tok/s
   available for real changes, and means every git commit is a *meaningful* diff.

2. **Validate structure before writing.** The system prompt demands exactly six
   `##` sections. Small models drift. Add a cheap post-check:

   ```python
   REQUIRED = ["## Summary", "## Recent News", "## Technical & Quant",
               "## Fundamentals", "## Markov Regime", "## Bottom Line"]
   missing = [s for s in REQUIRED if s not in body]
   ```

   On failure, retry once (optionally at temperature 0.1); if it fails again,
   log and skip the ticker rather than committing a malformed report. This is
   the single biggest consistency win for a 4B model.

3. **Add a "what changed" delta.** Since the previous report now lives at a
   stable path, feed its `## Bottom Line` into the prompt and ask for one extra
   line: *"Change since last report: upgraded/unchanged/downgraded because …"*.
   This turns a stream of snapshots into a narrative — the most valuable thing
   a recurring report can offer, and something the current design can't do
   because old files are deleted.

4. **Include the next earnings date.** `data_fetcher.get_earnings_dates()`
   already exists (per `DATA.md`) but isn't in the prompt. An upcoming earnings
   date is exactly the kind of "specific catalyst" the Bottom Line section asks
   the model to name — right now it has to leave that generic.

5. **Keep the model warm across the batch.** Add `"keep_alive": "10m"` to the
   Ollama payload so the model isn't at risk of being evicted between the 10
   sequential generations (default is 5 min, fine today, but any slow news
   fetch between tickers can cross it).

6. **Cap output length.** Add `"num_predict": 1200` (~ the target report size).
   Prevents rare runaway generations from eating the 600 s timeout and keeps
   report lengths uniform across tickers.

7. **Schedule sanity.** Consider hourly (or 30-min gated on §3.1's hash) and
   only during market hours + a couple hours after close. Overnight/weekend
   runs on unchanged data produce nothing but heat. n8n's schedule trigger
   supports cron expressions: `*/30 13-22 * * 1-5` (UTC) ≈ US market hours.

---

## 4. `.md` agent optimization

The reports are already good for humans. To make them good for **agents**
(Claude Code sessions, the `financial-analyst-advisor` agent, future RAG):

1. **YAML frontmatter on every report.** Agents (and scripts) shouldn't have to
   parse prose to learn the verdict. Emit this from `write_report()` — it costs
   zero model tokens because it's assembled from `ctx`, not generated:

   ```yaml
   ---
   ticker: MU
   company: Micron Technology, Inc.
   generated: 2026-07-04T09:30:00-04:00
   model: qwen3:4b
   direction: bullish        # parsed from the Bottom Line, or asked for as a first-line token
   price: 142.31
   day_change_pct: 1.2
   markov_regime: Bull
   analyst_rating: buy
   risk_score: 6
   data_hash: 3f9a…          # powers the skip-if-unchanged check (§3.1)
   ---
   ```

   The one generated field is `direction`; the cheapest reliable way to get it
   is instructing the model to end the Bottom Line with `**Verdict: bullish**`
   and regex-extracting it.

2. **Generate `reports/INDEX.md` every run.** One table, one row per ticker:
   ticker, direction, regime, price, day change, last-updated, link. An agent
   (or you) reads one small file to know the state of the world, then opens at
   most one full report. This is the highest-leverage agent optimization
   available — it turns N-file discovery into a 1-file read.

3. **Fix the template/prompt duplication.** `reports/_TEMPLATE.md` and the
   `SYSTEM_INSTRUCTION` string in `sandbox_ollama.py` each describe the report
   structure independently — they *will* drift. Make the script read
   `_TEMPLATE.md` and inject it into the system prompt as the structure spec.
   One source of truth, and editing report structure becomes a Markdown edit
   instead of a Python string edit.

4. **Add `reports/README.md`** (3–5 lines): what these files are, the
   frontmatter schema, the update cadence, and "machine-generated — do not hand
   edit." That's the file a future agent reads first, and it prevents anyone
   (human or agent) from wasting time editing files that get overwritten every
   30 minutes.

---

## 5. Security & ops findings

1. **`secure.md` contains a plaintext password** ("n8n pss"). It *is*
   gitignored (`.gitignore:63`) and has never been committed — verified — but
   it sits in a OneDrive-synced folder in cleartext. Move it to a password
   manager (or at minimum out of the synced project tree) and delete the file.
   n8n's own credentials should live in its encrypted credential store, which
   the workflow's sticky note already correctly instructs.
2. **Workflow is not activatable as committed**: `"active": false` and the SMTP
   credential is a placeholder. Fine for a repo artifact (credentials must
   never be in the JSON), but worth an explicit activation checklist in the
   sticky note: create SMTP credential → select it → create `auto/ollama-reports`
   branch + worktree → activate.
3. **Absolute Windows paths in the workflow** (`C:\Users\hatfi\...`) tie the
   workflow to this machine. Acceptable for a personal rig; if n8n ever moves
   to Docker/a server, the venv-python invocation is the first thing that breaks.
4. **The `Failed?` IF node currently routes both branches to the same email
   node** — harmless (the subject expression re-checks `exitCode`), but it's
   dead logic until §2b gives the success branch its commit step.

---

## 6. Suggested implementation order

| # | Change | Where | Effort |
|---|---|---|---|
| 1 | Stable filenames + frontmatter + verdict token | `sandbox_ollama.py` | S |
| 2 | `INDEX.md` generation | `sandbox_ollama.py` | S |
| 3 | Structure validation + one retry | `sandbox_ollama.py` | S |
| 4 | Worktree + commit/push node on success branch | git + workflow JSON | M |
| 5 | Skip-if-unchanged data hash | `sandbox_ollama.py` | S |
| 6 | Template as single source of truth | `sandbox_ollama.py` + `_TEMPLATE.md` | S |
| 7 | Earnings date in prompt; `keep_alive`; `num_predict`; market-hours cron | script + workflow | S |
| 8 | Delta-vs-last-report line | `sandbox_ollama.py` | M |
| 9 | Retire `secure.md` to a password manager | local hygiene | S |

Items 1–4 constitute the "solid pathway to the repo" the branch is for; 5–8 are
the quality/agent layer on top.
