# Hatfield Financial — Optimization & Bug Findings

Audit date: 2026-06-02
Branch: HFA-064-3-optimization-review
Scope: backend, frontend, financial logic, infrastructure, and .claude/guides accuracy. Nitpicks included.

Severity labels: **CRIT** (broken / security) · **HIGH** (correctness / cost / DoS) · **MED** (material but bounded) · **LOW** (nit / cleanup).

---

## 1) Potential Code Bugs

### Backend

#### Concurrency / queue (`data_fetcher.py`)
- **CRIT — data_fetcher.py:151-153** — `YFinanceQueue.submit()` uses `_SUBMIT_TIMEOUT=20s` for the caller's `event.wait()`. The worker also uses 20 s for its `_t.join(timeout=...)` guard around the actual yfinance call. When a call takes ~20 s, the submitter raises `TimeoutError` at the same moment the worker completes successfully — wasted work, spurious errors, possible double-submit on retry. Caller timeout should be longer than worker timeout (e.g. caller 30 s, worker 20 s).
- **HIGH — data_fetcher.py:208-223** — Starvation-promotion logic in `_run` can leave the worker processing the wrong item: it peeks `get_nowait()`, conditionally re-inserts both, and then proceeds without re-checking which item it has. Race condition.
- **HIGH — data_fetcher.py:310-315** — Outer `except Exception as outer:` calls `event.set()` but `event` may be unbound if the failure was in `self._pq.get()`. Silent worker crash if it ever fires.
- **HIGH — data_fetcher.py:417, 449, 481, 513, 540, 572, 671, 763** — Caller threads mutate `_yf_queue._min_endpoint_calls` (a plain dict) on cache hits with NO lock. The worker reads/clears it under `_record_lock`. Concurrent dict mutation across threads → potential `RuntimeError` or counter loss.
- **HIGH — data_fetcher.py:1009-1024** — `clear_ticker_cache` declares `global _ticker_objects` but never reassigns; the `global` is dead. (The lock-guarded `.clear()` itself is fine.)
- **HIGH — data_fetcher.py:84-99 / 319** — Module-level `_yf_queue = YFinanceQueue()` starts a daemon thread at import time. Safe with `gunicorn --workers 1` (current Dockerfile) but a footgun if the worker count ever increases. **Note: the Dockerfile no longer uses `--preload`, so each gunicorn worker would also start its own queue worker — additional risk.**

#### Routes
- **HIGH — routes/stock_data.py:111-130** — `refresh_stock_data` parses `start_str`/`end_str` then calls `get_stock_data(ticker)`, which re-parses them itself. The wrapper's parsing is dead code; if the dispatch ever changes, behavior diverges.
- **HIGH — routes/strategies/breakout_52week.py:62, 81** — `if close > high52 and prev_close <= float(prev['High52']) if not pd.isna(...) else False:` is unreadable due to Python operator precedence. The `if not isna` already guarded earlier; the inline conditional is dead. Rewrite with parens.
- **HIGH — services/custom_etf/simulator.py:148** — When `row is None` (position dropped out of the universe), `sell_price = pos.avg_cost` — i.e. sells at the buy price, recording $0 P&L on EXIT_UNIVERSE trades that actually moved. Real cash-tracking bug — money-relevant. (Also flagged under Financial.)
- **HIGH — services/custom_etf/markov_portfolio_backtest.py:88** — `datetime.utcnow()` is deprecated in Python 3.12+ and returns naive datetime, mixed with tz-aware comparisons elsewhere in the file.

#### Auth / validation
- **MED — auth.py:42** — `g.current_user_id = payload['user_id']` — `KeyError` → 500 instead of 401 on malformed token.
- **MED — auth.py:25** — `except (jwt.ExpiredSignatureError, jwt.InvalidTokenError)` — `ExpiredSignatureError` is a subclass of `InvalidTokenError`; tuple is redundant.
- **MED — routes/auth_routes.py:33** — Email-uniqueness check is racy (`filter_by(email=...).first()` then later commit). Two simultaneous registrations both pass; one explodes on unique constraint → 500.
- **MED — routes/admin.py:23, 42** — `User.query.get(user_id)` is removed in SQLAlchemy 2.x. Will break on the next SA bump. Use `db.session.get(User, user_id)`.
- **MED — routes/user_data.py:312-315** — `update_holding` accepts `ticker` without length validation; 21+ char tickers get silently truncated on Postgres or stored verbatim on SQLite.
- **MED — routes/stock_info.py:354-364** — `hist['Open'].iloc[-1]` for day-change can be a prior-day open on weekend / pre-open queries, so `dayChange` reflects an arbitrary prior session.
- **MED — routes/stock_info.py:517** — `float(info.get('dividendRate', 0)) > 0` — `'N/A'` string would raise. Use the `safe_float` helper.
- **MED — routes/markov.py:24-25** — 365-day default window may be too short for a stable transition matrix; `get_ohlcv`'s 280-day warmup helps but the trim happens before analysis.

#### Cache / state
- **MED — routes/recommendations.py:402 vs 134** — `future.result(timeout=5)` while the underlying queue submit allows up to 20 s. Most futures abandon their work before the queue gets to them; the work still runs and populates cache. Net effect is bandwidth waste + possible duplicate fetches on retry.
- **MED — routes/recommendations.py:485-487** — When Lambda is configured but failing, the backend never falls back — serves 202 forever.
- **MED — routes/recommendations.py:582** — `_fetching = False` only on `finally`; if the background thread hard-crashes pre-`finally`, the flag stays True forever.
- **MED — routes/custom_etf.py:61** — `get_spy_history(start.isoformat(), end.isoformat(), ...)` passes `str` but `get_spy_history` calls `.strftime(...)` → `AttributeError` swallowed by the bare except. Fallback path is dead.
- **MED — scripts/backfill_spy_prices.py:25-27** — Same `get_spy_history` str/datetime misuse. Script will crash on real work.

#### Lower-priority
- **MED — services/custom_etf/markov_portfolio_backtest.py:141-159** — Allocates `np.zeros((n+1, 3, 3), dtype=int)` per ticker; for 500 × 1250 bars that's ~45 MB live just for cum_counts.
- **MED — services/custom_etf/simulator.py:200** — `or 1.0` fallback after `max(..., 0.0)` turns negative-weight signals into a baseline-weight allocation. Probably surprising vs the docstring.
- **MED — services/custom_etf/strategies/buy_score.py:62-66** — `_avg()` returns `50` on empty input, silently hiding missing-data quality issues.
- **MED — routes/stock_info.py:184** — `avg_volume` can be NaN for short history; downstream conditional treats NaN as falsy. Fragile.
- **MED — routes/stock_info.py:269** — `len(spy_hist) >= 63` guards SPY length but doesn't align with `hist`'s index; differing trading-day sets aren't reconciled.
- **LOW — models.py:11** — Username case-sensitive (`Bob` ≠ `bob`). Two users can register the same name in different cases.
- **LOW — auth.py:75-95** — No max-password-length cap; a 10 MB password is allowed and will hash slowly.
- **LOW — routes/strategies/post_earnings_drift.py:40-43** — Earnings DataFrame's index is `tz_localize`d in place — **mutates the cached DataFrame**. Next request gets corrupted tz. Cache pollution.
- **LOW — routes/strategies/post_earnings_drift.py:33-34** — `pd.Timestamp(...).tz_localize(str(hist_tz))` — `str(hist_tz)` is unreliable for non-standard tz objects.
- **LOW — routes/strategies/relative_strength.py:28** — No null-check on `spy_hist` before `.Close`.
- **LOW — sp500.py:75-88, 97-102** — `pd.read_html(url)` has no timeout. Cache lock released across the network call, so two threads can both fetch.
- **LOW — routes/stock_data.py:39-40** — Computes `Close.rolling(20).std()` twice; reuse one.
- **LOW — routes/strategies/mean_reversion.py:48** — `if hasattr(row, 'get')` branch is dead (Series always has `.get`).
- **LOW — routes/strategies/ma_confluence.py:60-68** — Dead variable aliases (`prev_close_val`, etc.).
- **LOW — `_compute_rsi` duplicated in 5 places** (stock_data, stock_info, strategies/rsi, backtest, recommendations). Worth a single helper.

### Frontend

#### Races / lifecycle (`App.js`, `StockChart.js`)
- **HIGH — App.js:186-214** — Two parallel fetches (`/api/stock-info`, `/api/analyst-data`) on ticker change with no cancellation. Fast ticker switching can let stale responses overwrite newer state.
- **HIGH — App.js:154-184** — `handleRefreshData` has no cancellation either. Spam-clicking Refresh interleaves results.
- **HIGH — App.js:119-130** — Initial watchlist fetch has no cancellation. Logout-during-load → setState on unmounted / wrong-user component.
- **HIGH — StockChart.js:54-78, 81-123** — Both internal fetches (price data, signals) lack a `cancelled` guard. Ticker/strategy spam yields stale data overwrites and `onSignals` re-emits.
- **HIGH — StockChart.js:1427** — `${s.price.toFixed(2)}` crashes on null `s.price`. The same row defensively handles null `conviction`/`score` but not `price`.

#### Rendering / perf
- **HIGH — Recommendations.js:671-681** — `rows = filteredStocks.map(s => ({ ..., buyScore: computeBuyScore(s) }))` runs `computeBuyScore` (10 lookups + arithmetic) on every single render — ~5000 ops per keystroke for a 500-row universe. Wrap in `useMemo`.
- **HIGH — StockChart.js:200-228, 234-1185** — Every render reconstructs `priceData`, `volumeData`, `macdData`, `rsiData`, `atrData`, `stochData`, `obvData`, plus options objects. Divergence loops are O(n × divWindow). Memoize on `[stockData, strategy, startDate, endDate]`.
- **MED — Recommendations.js:478-481** — `setInterval(() => setLastUpdated((v) => v), 30_000)` deliberately re-renders the entire tab tree every 30 s. Move the "X mins ago" tick into a small sub-component.
- **MED — Recommendations.js:660-688** — `counts`, `filteredStocks`, `rows`, `expandedStock`, `expandedRank`, `activeStrategyMeta` recomputed every render.
- **MED — Watchlist.js:343** — `const columns = buildColumns(handleRemove)` rebuilt every render → DataTable sort recomputes.
- **MED — CustomEtfPanel.js:107-110** — 1 s `setInterval` re-renders `NextRebalanceTimer` and re-runs `toLocaleString` for the countdown. Move format into the minute-keyed `useMemo`.
- **MED — StockChart.js:325** — `dates.map((d) => earningsSet.has(d) ? close[dates.indexOf(d)] : null)` is O(n²). Use the map index.
- **MED — ApiMonitorPanel.js:80-94** — `setInterval` runs an `async` `apiFetch` that can exceed the 3 s tick (apiFetch retries 429 with 3 s delay × 3 → 9 s). Stack of in-flight requests. Use chained `setTimeout`.

#### State / cache
- **MED — api.js:18-25** — Documented "max 50 entries" cache evicts FIFO (first-inserted), not LRU. Documented behavior matches docs only loosely.
- **MED — api.js:6-25** — Cache stores `Response` objects (with cloned body streams), pinning ~5-10 MB of body buffers if filled with multi-KB JSON. Cache `response.json()` results instead.
- **MED — CustomEtfPanel.js / ApiMonitorPanel.js / MarkovBacktestPanel.js** — All three append `?t=${Date.now()}` to GET URLs to bypass the api.js cache. Each request adds a unique cache key that evicts useful entries — over 5 min of polling can flush the cache. Skip the cache via a request flag instead.
- **MED — api.js:78-83 vs AuthContext** — Two sources of truth for token: api.js clears localStorage on 401 + dispatches event, AuthContext.login/register write to localStorage directly. A 401 during login round-trip races.
- **MED — StockInfo.js:99** — `info.rsi !== null` lets `undefined` pass → `NaN`. Use `!= null`.
- **MED — StockChart.js:122** — `onSignals` excluded via eslint-disable — but App.js never passes `onSignals` at all, so the wired lift is a no-op (see Misc → `SIGNAL_COLUMNS` and `onSignals`).
- **LOW — Various** — `key={i}` (array index) used in many list renders: InsiderTransactions.js:140, InstitutionalHoldings.js:186, AnalystPanel.js:167, MarkovBacktestPanel.js:329, StockChart.js:1425, CustomEtfPanel.js:573. Sort/insert will mismatch identity.
- **LOW — AdminPanel.js:227, 242** — `window.confirm` vs the in-app `DeleteConfirmModal`. Mix of destructive-action confirmation styles.
- **LOW — StatCard.js:95-99** — Inlines `<style>` with `@keyframes spin` per render. Move to `StatCard.css`.
- **LOW — StockChart.js:231-232** — `new Set([...])` reconstructed every render. Lift to module scope.

---

## 2) Financial Bugs

### Look-ahead bias (most common pattern)

- **HIGH — routes/strategies/mean_reversion.py:27** — `hist['Close'].rolling(20).max()` does NOT shift, so today's close influences today's drawdown calc. `52-week-breakout` correctly uses `shift(1)` but `mean-reversion` does not. Backtest entry signals slightly overcount; impact ~0.5-1.5 % positive bias.
- **HIGH — routes/strategies/bollinger_bands.py:29** — `VolMA20 = Volume.rolling(20).mean()` includes today's volume in the 20-day average that today's volume is then compared against — weakens the `volume > 1.3× avg` filter.
- **HIGH — routes/strategies/volatility_squeeze.py:32-36** — 60-day percentile / median include today's BB-width in the threshold today's BB-width is compared against.
- **HIGH — routes/strategies/breakout_52week.py:33** — Volume MA used in the breakout confirmation includes today's volume. (The high/low rollings DO `shift(1)`; this one doesn't.)

### Indicator / formula
- **HIGH — routes/strategies/breakout_52week.py:62, 81** — Operator-precedence trap (see Code Bugs). When `prev['High52']` is NaN, the ternary short-circuits safely today, but the structure is fragile. Wrap in parens.
- **MED — routes/stock_info.py:52 vs strategies/rsi.py:15 vs backtest.py:15 vs recommendations.py:74** — Two RSI implementations live in the codebase. `stock_info.py` uses `ewm(com=period-1)`; everywhere else uses `ewm(alpha=1/period, adjust=False)` (Wilder). The card RSI on the analysis tab differs from the RSI chart signal RSI by ~2-5 points on the same data. Pick Wilder and standardize.
- **MED — routes/stock_info.py:159 vs routes/strategies/macd_crossover.py:50-51** — "MACD momentum" computed two different ways: `abs(macd - signal) > 0.5` (stock_info) vs `abs(hist) / recent_range × 60` (macd_crossover). They measure different things; pick one definition for display vs signal consistency.

### Backtest engine (`routes/backtest.py`)
- **MED — backtest.py:178, 257** — `shares = int(cash / sig_price)` truncates fractional shares; over many trades this can accumulate $1-2k of dead cash on a $10k starting capital, depressing returns 1-3 % annually. Fine if "no fractional shares" is the documented rule — but it isn't.
- **MED — backtest.py:275-276** — `num_losses = sum(1 for t in closed if t['pnl'] <= 0)` counts breakeven trades as losses → win rate biased down by 1-2 %.
- **MED — backtest.py:289** — `profit_factor = float('inf')` when there are wins and no losses. Mathematically correct but not actionable; consider capping at e.g. 100 or returning `null` + a `hasInfiniteProfitFactor` flag.

### Custom ETF / portfolio simulator
- **HIGH — services/custom_etf/simulator.py:148** — EXIT_UNIVERSE sells use `pos.avg_cost` as the sell price, recording $0 P&L and ignoring the actual market move since entry. Cash tracking + reported returns are both wrong for these trades. (Listed under both Financial and Code Bugs.)
- **MED — services/custom_etf/simulator.py:200** — Negative `weight()` returns get clamped to 0, then `or 1.0` promotes to 1.0 — same allocation as a strong-conviction pick. Counter-intuitive vs the docstring.

### Biases & structural issues
- **MED — Analyst-based ETF strategies** (`analyst_conviction.py`, `undervalued_strong_buy.py`) — `targetUpsidePct` and `numberOfAnalysts` are forward-looking consensus values. Backtests using today's analyst estimates on historical dates leak hindsight; expect ~5-15 % overstated backtest returns.
- **MED — Survivorship bias** — All backtests use the *current* S&P 500 list. Removed/delisted tickers are excluded → mild upward bias over 5+ year windows. Document, not fixable without a point-in-time membership table.
- **MED — routes/strategies/post_earnings_drift.py:45-47** — Doesn't dedupe earnings dates across repeated calls. Each call is stateless, so today this is harmless, but worth a comment.
- **LOW — services/custom_etf/markov_portfolio_backtest.py** — Markov-state classification uses 20-bar lookback log-returns (no peek). Transition matrix is built strictly from `regime[:-1] → regime[1:]` (no peek). The transition counts are tiny early on; the resulting matrix is noisy for the first ~50 bars. Worth a min-data guard.
- **LOW — routes/strategies/breakout_52week.py:29** — Uses 252 trading days for the "52-week" window. For 24/7 crypto symbols (365 trading days/year) the window is actually ~36 weeks.
- **LOW — routes/stock_info.py:269** — SPY/Stock alignment for 1-month/3-month returns doesn't enforce the same date set, just the same length cutoff.

---

## 3) Cost Optimization Bugs

### API / Yahoo data costs
- **HIGH — data_fetcher.py:457** — `get_ticker_info` only caches truthy responses. Tickers that legitimately return None / `{}` (delisted, halted) hit Yahoo on every request. Add negative caching with a short TTL.
- **HIGH — data_fetcher.py:230 (get_earnings_dates cache key)** — Key is `f'earnings:{ticker}'` with no `limit` suffix. `stock_info` calls with `limit=4` and `stock_data` with `limit=20` share one cached value (first writer wins) → wrong size returned to the other caller. Money-correctness adjacent.
- **HIGH — data_fetcher.py:951, 973 vs 412** — `get_many_ohlcv` writes cache key `ohlcv_period:{t}:{period}`; `get_ohlcv` reads `ohlcv:{ticker}:{start}:{end}`. Different prefixes → the recommendations bulk fetch does NOT accelerate later per-ticker route reads. Docstring at line 970 claims it does — wrong. Either unify keys or stop seeding the bulk cache.
- **HIGH — routes/recommendations.py:396-407** — 500 `_get_ticker_info` futures submitted concurrently with `max_workers=8`, but all serialize through the YFinanceQueue at 0.3 s intervals — the thread pool adds overhead with no parallelism. Add `future.result(timeout=5)` (line 402) abandoning work that the queue is still about to run = wasted Yahoo traffic.
- **HIGH — routes/recommendations.py:300-312** — `analyze_markov` runs 4-5 numpy `matrix_power` calls per ticker × 500 tickers = ~2500 matrix powers per refresh, every 20 minutes. Vectorize across tickers or cache.
- **HIGH — data_fetcher.py:420 / _MAX_WARMUP_DAYS** — Every `get_ohlcv` call fetches 280 days of pre-warmup regardless of the strategy's actual need (RSI 60 d, BB 40 d, RS 20 d). With a 182-day default user window, that's a 462-day fetch every time. Per-strategy warmup would cut Yahoo bandwidth ~30 %.
- **HIGH — routes/stock_info.py:613-652** — Every `/api/stock-info/<ticker>` call fetches ticker info + OHLCV + earnings + insider transactions + institutional holders + SPY period. Each insider/institutional access is 1-2 yfinance property calls. For a tab switch to a new ticker that's 6-8 queue-serialized calls (~2 s minimum). Lazy-load the insider/institutional panels behind their respective sub-tabs.
- **MED — data_fetcher.py:579-607 (get_analyst_data)** — 5 separate property accesses serialized at 0.3 s each = ~1.5 s minimum. yfinance has batched aggregator methods — consolidate.
- **MED — routes/stock_info.py:267-282 vs strategies/relative_strength.py** — Two SPY cache keys (`spy_period:3mo` vs `spy_history:{start}:{end}`) that hold ~the same data without sharing. Pick one.
- **MED — routes/recommendations.py:589-590** — `/progress` returns the full `stocks` array (500 entries) every poll. The frontend polls every 1-5 s while loading. Return only `{status, progress, total}` until done.

### Compute / memory
- **HIGH — services/custom_etf/markov_portfolio_backtest.py:141-159** — `np.zeros((n+1, 3, 3), dtype=int)` per ticker for 500 × 1250 bars = ~45 MB live arrays just for cum_counts, plus the O(n) copy each step → ~14 M ops × 500 tickers per backtest. Vectorize with `np.cumsum`.
- **HIGH — Frontend Recommendations re-render burden** — see Code Bugs §Recommendations: 500 `computeBuyScore` calls per render, no-op `setLastUpdated` every 30 s. Significant browser CPU.
- **HIGH — Frontend StockChart re-render burden** — full chart data + options reconstructed per render. Memoize.
- **MED — Frontend cache pollution** — three panels use `?t=Date.now()` to bypass api.js cache, evicting hot entries within minutes.

### AWS / infra (see INFRASTRUCTURE.md updates)
- **HIGH (~$10-15/mo) — infra/modules/efs** — EFS for a tiny SQLite file is the most expensive storage tier on AWS and serves no real purpose when `desired_count = 1` is hard-locked by SQLite-single-writer. Migrate to RDS (already coded in `infra/modules/rds/`) or use container-local disk with periodic S3 snapshots; either eliminates the EFS cost and unlocks `desired_count > 1`.
- **HIGH (~$15/mo) — infra/modules/ecs/main.tf:19-20** — 512 CPU / 1024 MB Fargate task is oversized for the current traffic. 256 / 512 likely sufficient. Halves the bill.
- **MED ($3-7/mo) — infra/modules/lambda/main.tf:124** — Precompute Lambda at 2048 MB × 24/7 every 20 min. Profile actual usage; 1024 MB likely fine.
- **MED ($2-5/mo) — Lambda log groups have no retention set** — defaults to indefinite. Add `aws_cloudwatch_log_group` resources for both Lambdas with `retention_in_days = 14`.
- **LOW — Frontend S3 bucket** has versioning on but no lifecycle rule. Old asset versions accumulate forever (~$0.50-2/mo). Add a 30-day non-current cleanup. The Lambda cache bucket DOES have one.

---

## 4) What Was Added / Removed from MD Files

I updated the .claude files in place. Bug fixes for code are NOT included — only documentation accuracy.

### `.claude/CLAUDE.md`
- **Added** a "Major subsystems" section pointing at Custom ETF simulator, Markov model, and admin tooling — previously invisible to the agent.
- **Replaced** the "Backend Rules" block to reflect reality (the documented `get_quotes`/`get_bars` interface and `request_id` / structured JSON logging are NOT implemented; the actual rule is "use `data_fetcher` helpers"). The aspirational rules are dropped to avoid misleading future agents.
- **Added** an "Environment Variables" section listing `SECRET_KEY`, `DATABASE_URL`, `ALLOWED_ORIGIN`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `INTERNAL_API_SECRET`, `S3_CACHE_BUCKET`, and `REACT_APP_API_URL`.
- **Expanded** the reference-guides list to mention all 9 chart strategies + 6 Custom ETF strategies, all React components (not just the original five), the priority queue + S3-backed prewarm, and the Lambda × 2 architecture.

### `.claude/guides/ARCHITECTURE.md`
- **Rewrote** the file tree: added `admin.py`, `custom_etf.py`, `markov.py`, `lambda_handler.py`, `lambda_rebalance_handler.py`, `Dockerfile.lambda`, the full `services/custom_etf/` + `services/markov/` subtrees, and the `scripts/` directory. Added 12 missing frontend components.
- **Replaced** the "4 tabs" section with the actual 9 top-level tabs + 6 analysis sub-tabs. Removed the non-existent "Components" tab.
- **Updated** the data-flow diagram: info TTL corrected to 10 min (was 30 min). Added the Lambda → S3 → backend prewarm path and the EventBridge → Lambda → backend auto-rebalance path.
- **Added** the `EtfPortfolio`/`EtfPosition`/`EtfTrade`/`EtfEquitySnapshot` models.
- **Added** missing `data_fetcher` helpers (`get_insider_transactions`, `get_institutional_holders`, `get_many_ohlcv`, `get_spy_1m_return`, `clear_cache`, `clear_ticker_cache`) and documented the `YFinanceQueue` priority levels + starvation promotion + metrics recording.
- **Corrected** the CORS claim: prod accepts `hatfield-financial.com` *plus* whatever's in `ALLOWED_ORIGIN`, always.
- **Flagged** the `SIGNAL_COLUMNS` / `onSignals` claim as out-of-date — `SIGNAL_COLUMNS` doesn't exist and App.js never passes `onSignals`.
- **Marked** `Backtester.js` / `Backtester.css` as ORPHANED (not imported anywhere; CSS has the only mobile media queries).
- **Removed** the "common provider interface" claim and the `request_id` / structured-JSON-logging claim because neither is actually implemented.

### `.claude/guides/API.md`
- **Added** sections documenting these previously-undocumented endpoints:
  - **Admin** — `GET /api/admin/users`, `DELETE /api/admin/users/<id>`, `PATCH /api/admin/users/<id>/role`, metrics start/status/clear
  - **Custom ETF** — strategies, summary, state, rankings, rebalance, reset, auto-rebalance-all, markov-regime/backtest, backtest/<job_id>
  - **Markov** — `GET /api/markov/<ticker>`
  - **Watchlist bulk data** — `GET /api/user/watchlists/<id>/data` + per-ticker variant
  - **`PATCH /api/auth/me`** for profile updates
  - **Debug** — `GET /api/debug/yfinance/<ticker>` (and called out as an information-disclosure surface)
- **Corrected** the `/api/recommendations/progress` response shape (`progress`/`stocks`/`total`, NOT `fetched`/`pct`).
- **Added** a callout that `/api/stock-info` returns many more fields than the spec enumerated (governance risks, insider, institutional, business summary, etc.) and that `/api/recommendations` includes `markovRegime`/`markovBull3d`/`markovBull5d`/`markovBear5d`.

### `.claude/guides/DATA.md`
- **Corrected** the info-TTL from 30 min to 10 min.
- **Added** the priority-queue mention (single worker, 0.3 s interval, starvation promotion).
- **Replaced** the `stock.calendar`-as-primary section with the actual fact: only `get_earnings_dates()` is used in current code paths.
- **Documented** the earnings cache-key/limit collision.
- **Removed** the reference to a non-existent `CRYPTO_TICKERS` constant; clarified what `sp500.py` actually contains.
- **Added** a note about `get_ticker_info` skipping the cache for falsy results (causes repeated re-fetches for known-bad tickers).
- **Added** the S3-backed Recommendations cache (the one exception to the "in-memory only" rule).

### `.claude/guides/FIN_STRATEGIES.md`
- **Clarified** that Mean Reversion's 20-day high is NOT shifted (unlike 52-week breakout). Added a warning callout pointing at this report.
- **Added** the **Markov Regime — Conviction-Weighted Bull** Custom ETF strategy section — previously the file documented 5 ETF strategies; the code registers 6.

### `.claude/guides/COMPONENTS.md`
- **Added** full sections for 12 previously-undocumented components: `Watchlist`, `CustomEtfPanel`, `MarkovMethod`, `MarkovBacktestPanel`, `MarkovExplainPanel`, `InsiderTransactions`, `InstitutionalHoldings`, `AccountPanel`, `AdminPanel`, `ApiMonitorPanel`, `AuthPage`, `AboutPage`.
- **Replaced** the Backtester section with an "ORPHANED" status block — it's not imported anywhere and its CSS holds the only mobile media queries in the codebase.
- **Updated** the DataTable prop table to include `onRowDoubleClick`.
- **Updated** StockChart's key props: added `fetchStart`, `fetchEnd`, `onRangePerformance`, `refreshKey`; marked `onSignals` as currently dead.
- **Corrected** the Recommendations CSS-class prefix: `rec-*` (not `recommendations__*`).

### `.claude/guides/INFRASTRUCTURE.md` (full rewrite)
- **Corrected** the architecture diagram: shows API Gateway → VPC Link → Cloud Map → ECS, plus the EventBridge → Lambda → S3 / backend paths.
- **Replaced** "RDS PostgreSQL (prod)" with "SQLite on EFS at `/mnt/efs/hatfield.db` (prod). RDS module exists but is not wired in."
- **Added** the `lambda` Terraform module (precompute + rebalance + S3 cache bucket + EventBridge rule + scheduler).
- **Corrected** the dependency chain.
- **Corrected** the variables list: only `secret_key` and `internal_api_secret` are declared at the root; `db_username`/`db_password` are unused leftovers.
- **Updated** deploy.yml from "two parallel jobs" to **three** (added `deploy-lambda`); flagged the missing `needs:` ordering and lack of `aws ecs wait services-stable`.
- **Corrected** the Dockerfile CMD: actual flags are `--workers 1 --threads 4 --timeout 120` (NOT `--preload`).
- **Added** missing env vars: `INTERNAL_API_SECRET`, `S3_CACHE_BUCKET`, `S3_BUCKET`/`S3_KEY`, `BACKEND_URL`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`.
- **Corrected** `REACT_APP_API_URL`'s purpose: API Gateway (not ALB; there is no ALB).
- **Added** a "Cost-relevant defaults" section: Fargate sizing, EFS tier, Lambda memory/timeout, log retention, no NAT.

### `.claude/guides/DESIGN_SYSTEM.md`
- **No changes.** Verified against the codebase — color palette, typography, spacing, chart heights, state patterns are all still accurate.

---

## 5) Misc

### Architecture rules in CLAUDE.md vs reality
- **`get_quotes(symbols)` / `get_bars(symbol, tf, start, end)`** common provider interface — never implemented. Actual helpers are `get_ohlcv`, `get_ticker_info`, etc. (Removed from CLAUDE.md.)
- **Cache key format `(provider, endpoint, params_hash)`** — never implemented; actual keys are string-concatenated `ohlcv:{ticker}:{start}:{end}` style. (Removed from CLAUDE.md.)
- **`request_id` per request + structured JSON logging** — never implemented. (Removed from CLAUDE.md.)
- **Global error handler returning standardized errors** — defined for 500 + 429 but bypassed by most routes catching their own exceptions. (Removed the "standardized" claim from CLAUDE.md.)
- **CORS restricted to `http://localhost:3000`** — in fact, prod always allows `hatfield-financial.com` too via set-union. (Corrected in CLAUDE.md and ARCHITECTURE.md.)
- **Desktop-only rule** — violated by `Backtester.css` (the only @media query in the repo). Backtester is also orphaned code, so the violation is dormant — but the file is still in the bundle.

### Dead code / unused references
- **Backtester.js + Backtester.css** — Not imported anywhere. `/api/backtest` is still live on the backend. Either delete the React component or wire it back in under AdminPanel (per the recent "made backtesting admin only" commit).
- **scripts/restore_snapshot_marks.py + scripts/repair_etf_allocations.py** — Per the docstring on `fix_etf_snapshots.py`, both are superseded. Delete.
- **routes/backtest.py:2** — `import numpy as np` never used in this file (only pandas).
- **app.py:13** — `generate_password_hash` only used in conditional admin-seed block; for normal startup it's dead.
- **requirements.txt** — `flask-migrate` listed but never imported. `requests-cache`, `requests-ratelimiter`, `pyrate-limiter<3.0` listed but explicitly disabled per the data_fetcher comment ("Do NOT pass a custom `session=` to yf.Ticker"). All four are dead deps.
- **routes/stock_info.py:13** — `logger.info(f'stock_info blueprint created: ...')` fires on every module import. Noise.
- **routes/stock_info.py:16-45** — `/api/debug/yfinance/<ticker>` is documented as "temporary" but permanently registered with no auth gate. Information-disclosure surface.
- **routes/stock_data.py:113** — `refresh_stock_data` parses args then ignores them (covered above).
- **services/custom_etf/markov_portfolio_backtest.py:40** — `_YEARS_TO_PERIOD = {1: '5y', 3: '5y'}` — both keys map to the same value.
- **app.py:225** — Prewarm thread starts at module load. Fine with `--workers 1`; would run once per worker if that ever changed.

### Inconsistencies
- **Color-variant helpers** — Duplicated between `Watchlist.js`, `Recommendations.js`, and `StockInfo.js` with subtly different return conventions. Extract to a shared `utils/colorVariants.js`.
- **`InfoPopover`** — Defined verbatim in both `InsiderTransactions.js` and `InstitutionalHoldings.js`. Extract.
- **Inline styles vs CSS classes** — Many `style={{ display: 'flex', gap: '8px', ... }}` blocks across App.js, StockInfo.js, Recommendations.js. The codebase otherwise prefers CSS classes; the inline-style pattern is unidiomatic.
- **Two cache layers** — api.js (2-min memory, FIFO, 50 entries) + Recommendations.js localStorage (20-min). Different naming and conventions across the two. Fine as a design choice but the conventions could converge.
- **`apiFetch` error copy hard-codes "port 5000"** — Backtester.js:131, StockChart.js:75, StockChart.js:118 show "Could not connect to the backend. Make sure the Flask server is running on port 5000." even though `REACT_APP_API_URL` can override the actual URL.

### CI/CD nits
- **No tests in deploy.yml or infra.yml** — no `pytest`, no `npm test`, no lint. Every push to main ships.
- **No concurrency control** — two simultaneous pushes can race ECS deploys.
- **No failure notifications** — silent failure of the scheduled Lambda deploy could go unnoticed.
- **Static AWS access keys** — `.github/workflows/deploy.yml` lines 36-37, 66-67, 149-150 use long-lived `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`. Move to GitHub OIDC federation.
- **`.github/workflows/infra.yml`** — passes `TF_VAR_db_username`, `TF_VAR_db_password` which are NOT declared at the root level (only inside the unused RDS module). Dead config. Does NOT pass `TF_VAR_internal_api_secret` which IS required → every plan currently fails until added.

### Infra security defense-in-depth
- **`terraform.tfvars.example`:7-9** — Ships hardcoded weak values (`db_username = "name"`, `db_password = "password"`, `secret_key = "idkGoodLuckGuesing!"`). Replace with `<REPLACE_ME>` or delete the values.
- **infra/modules/iam/main.tf:51-58** — Creates a long-lived IAM user + access key for GitHub Actions. Move to OIDC.
- **infra/modules/ecs/main.tf:22** — `task_role_arn = var.ecs_task_execution_role_arn` — execution role reused as task role. Split them.
- **infra/modules/ecs/main.tf:39, 42** — Secrets passed via `environment` (plain) instead of `secrets` (Secrets Manager / SSM Parameter Store).
- **Backend/Dockerfile** — Container runs as root; no `.dockerignore`. Add a non-root user and `Backend/.dockerignore`.
- **infra/modules/rds/main.tf:25-27** — Even though unused, its defaults are dangerous (`skip_final_snapshot = true`, `deletion_protection = false`). Either fix the defaults or delete the module.

### CI/CD critical
- **`.github/workflows/infra.yml`** — Missing `TF_VAR_internal_api_secret`. Every PR plan currently fails. **Highest-priority single fix.**

---

## Summary of the Top 10 Worth Fixing First

1. **CI broken** — Add `TF_VAR_internal_api_secret` to `.github/workflows/infra.yml`. Quick.
2. **EXIT_UNIVERSE sells use cost basis** (`simulator.py:148`) — silently wrong money tracking on auto-rebalance.
3. **YFinanceQueue caller-vs-worker timeout race** (`data_fetcher.py:151-153`) — spurious TimeoutErrors on completed work.
4. **Earnings cache-key/limit collision** (`get_earnings_dates`) — wrong-size DataFrame returned to one of the callers.
5. **`get_many_ohlcv` writes a different cache prefix than `get_ohlcv` reads** — bulk fetches don't reduce later single-ticker traffic.
6. **CORS unconditionally allows production domain from local dev** (`app.py:48-49`).
7. **Backtester is dead code** with the only mobile media queries — delete or re-wire.
8. **EFS for SQLite is the wrong tool** (~$10-15/mo waste, hard-locks `desired_count = 1`, prevents horizontal scale). Decide RDS or container-local + S3 snapshot.
9. **Frontend re-render burden** (Recommendations / StockChart memoization) — UX win on the most-used screens.
10. **Lambda log groups have no retention** — silently accumulating CloudWatch storage forever.

---

# HFA-069 — Custom ETF Quant Review (2026-07-08)

Branch: HFA-069-1-financial-algo-corrections. Full accuracy/usability review of the 6 Custom ETF
strategies, live simulator, and Markov backtest. **Fixed in the branch:** backtest≠live semantics
(new shared `rebalance_core` + generic `walk_forward` engine), Momentum sleeve re-based from
1-month relative return to 6-1M cross-sectional momentum, Low Vol sleeve re-based from self-relative
ATR ratio to cross-sectional realized σ, daily equity marking, stale-price and NaN guards, Buy Score
flagged backtest-unsafe. **The items below were confirmed but deliberately NOT fixed (report-only) —
they are the follow-up backlog.**

## Financial accuracy follow-ups

- **HIGH — services/custom_etf/simulator.py** — Live simulator never credits dividend cash to
  portfolios, while the walk-forward backtest uses yfinance auto-adjusted (dividend-inclusive)
  closes. Live sleeves understate total return ~1-2%/yr (worst for Low Vol's dividend payers) and
  live-vs-backtest numbers aren't apples-to-apples. Fix: credit `ticker.dividends` for held
  positions at each rebalance via a cached `data_fetcher` helper.
- **HIGH — services/custom_etf/rebalance_core.py (sell phase)** — Held names that turn *ineligible*
  (e.g. Markov Bear flip) are sold via the EXIT_UNIVERSE path: reason mislabeled, score=None, and
  the price is re-fetched from `.info` even though the snapshot row has `currentPrice`. Fix: pass
  the full (pre-eligibility) row map into the pass; price from snapshot; label `INELIGIBLE`.
- **HIGH — services/markov/** — Transition matrices are built from OVERLAPPING 20-day returns, so
  day-to-day regime persistence is inflated by construction and P^5 mostly predicts "stay put".
  The prewarm matrix uses ~10 months of bars while `/api/markov/<ticker>` uses 730 days — the same
  ticker shows different regime numbers in two places. `low_confidence` is computed but never
  propagated to rec rows or the ETF eligibility gate. Fix candidates: debounced/non-overlapping
  transition sampling, Laplace smoothing, unify windows, surface `transitionsObserved` on rows.
- **MED — walk_forward.py** — Same-bar execution (decide and fill on the rebalance close). Now
  disclosed in `result['caveats']`; next-open fills would be more conservative.
- **MED — simulator.py `_closed_trade_stats` / `serialize_state`** — $0-P&L exits count as losses
  in win rate; best/worst trade ranked by dollars in the sidebar but by percent on the state page.
- **MED — routes/recommendations.py 52-week fallback** — `close.tail(252)` over a ~210-bar (10mo)
  series makes the fallback a 10-month high/low, and mixes adjusted closes with raw `.info` prices.
- **LOW — buy_score.py** — `_vol_ratio_score` caps at 80 so the 7% volatility component can never
  reach 100; Buy-Score upside clamp is [−10,+30] vs [−10,+50] in the analyst sleeves. Document as
  intentional or align.

## Usability follow-ups

- **MED — CustomEtfPanel.js** — Live page has no "vs SPY" headline card even though `vsSpyPct` is
  in the summary payload; Entry/Current Score columns and score-badge colors have no
  tooltip/legend; slippage & threshold chips are unexplained.
- **NOTE — local dev environment** — AVG Web Shield TLS interception breaks all yfinance calls
  (curl 60) with yfinance ≥ 1.x. See DATA.md "Known Limitations" for the CURL_CA_BUNDLE workaround.
