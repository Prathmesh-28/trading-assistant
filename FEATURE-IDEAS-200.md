# 200 Handy Features to Add — Fundamentals, Screener.in-style data & more

Original ideas (not from BACKLOG.md), tuned to this project's rules: deterministic,
**no LLM in the runtime**, Python 3.9, fail-soft to `None`, and the import-boundary
convention (a new data source = its own adapter, like `groww_adapter.py`).

> **Screener.in caveat:** Screener.in's Terms of Use prohibit automated scraping/crawling,
> and aggressive requests will get your IP blocked. Sections A treats direct scraping as a
> best-effort, rate-limited, cache-heavy, personal-use option; Section B rebuilds the same
> features from sources you can use cleanly (yfinance — already in `fundamentals.py` — plus
> NSE/BSE filings and official exports). Prefer B where possible.

---

## A. Screener.in-style scraping track (`screener_adapter.py`) — 20

1. **Dedicated `screener_adapter.py`** — Isolate all Screener.in access in one module (mirrors the groww_adapter boundary), so the rest of the app never imports it directly.
2. **Company page fetch by symbol** — Resolve `NSE:SYMBOL` → the `/company/SYMBOL/` page and parse the top ratio grid (P/E, market cap, ROE, ROCE, book value).
3. **Consolidated vs standalone toggle** — Screener exposes both; capture which one you parsed so ratios aren't silently mixed across companies.
4. **Quarterly results table parse** — Pull the last ~12 quarters of sales/OPM/net profit into a clean list, oldest-first, for growth math.
5. **Annual P&L parse** — 10-year sales/expenses/OPM/PAT rows, the core of the Screener "story".
6. **Balance sheet parse** — Equity, reserves, borrowings, fixed + other assets per year for leverage and asset-turnover ratios.
7. **Cash flow parse** — Operating/investing/financing cash flows per year to sanity-check reported profit vs cash.
8. **Ratios table parse** — Debtor days, inventory days, working-capital days, cash-conversion cycle, ROCE trend.
9. **Shareholding pattern parse** — Promoter / FII / DII / public %, quarter over quarter, plus promoter-pledge %.
10. **Pros & cons block parse** — Screener's auto-generated bullet list; store as text notes on the fundamentals card.
11. **Peer comparison table parse** — Same-industry peers with P/E, ROCE, market cap for side-by-side ranking.
12. **Announcements / documents links** — Capture links to filings and concalls (store URLs only, don't re-host).
13. **Polite rate limiter** — Hard cap (e.g. 1 request / 3–5s) + jitter, shared across the process, to stay well under abuse thresholds.
14. **Disk cache with long TTL** — Cache each company page 12–24h (fundamentals are quarterly facts, not live) to minimise requests.
15. **Conditional GET / ETag support** — Send `If-None-Since`/ETag so unchanged pages return 304 and cost nothing.
16. **Robots.txt + ToS guard** — A config flag `SCREENER_SCRAPE_ENABLED` defaulting **off**, with a startup log noting the ToS restriction.
17. **HTML-structure drift detector** — If expected table selectors vanish, fail soft to `None` and alert once (sites change layout often).
18. **User-supplied session cookie** — Let the user paste their own logged-in cookie for their own account rather than bypassing auth.
19. **Graceful 403/429 backoff** — On block responses, disable scraping for a cooldown window and fall back to Section B sources.
20. **Provenance stamp on every field** — Tag each value with `source: "screener.in" | "yfinance" | "nse"` so the UI can show where a number came from.

## B. Same features, clean sources (extend `fundamentals.py`) — 20

21. **NSE/BSE announcement feed** — Pull corporate announcements from the exchanges' own public JSON instead of scraping Screener.
22. **BSE India financial results API** — Official quarterly result PDFs/tables for the balance-sheet and P&L rows.
23. **yfinance quarterly financials** — You already load `income_stmt`; add `quarterly_income_stmt`, `balance_sheet`, `cashflow`.
24. **Promoter/institutional holding via NSE** — NSE publishes shareholding patterns; parse those instead of Screener's table.
25. **Screener CSV export ingestion** — Screener lets logged-in users export to Excel; support importing that file the user downloads themselves (fully compliant).
26. **ROCE computed in-house** — EBIT / (total assets − current liabilities) from statements, so you don't depend on any site's number.
27. **Working-capital-days computed in-house** — Debtor + inventory − creditor days from balance-sheet + sales.
28. **Cash-conversion-cycle metric** — Derived deterministically from the days ratios above.
29. **Piotroski F-Score** — 9-point fundamental health score, pure arithmetic from statements — a Screener favourite you can own.
30. **Altman Z-Score** — Bankruptcy-risk composite from balance sheet + market cap, fully deterministic.
31. **Promoter pledge % tracker** — From NSE/BSE pledge disclosures, with an alert on increases.
32. **Debt-to-equity trend (5y)** — Compute from statements rather than a single trailing ratio.
33. **Interest-coverage ratio** — EBIT / interest expense, flags fragile balance sheets.
34. **Dividend history & payout ratio** — From yfinance dividends series, deterministic payout math.
35. **Free-cash-flow & FCF yield** — Operating CF − capex, divided by market cap.
36. **Sales/PAT CAGR (3y/5y/10y)** — Standard Screener growth columns, computed locally.
37. **OPM & NPM trend** — Operating and net margin per year to see expansion/compression.
38. **Book value & P/B trend** — Track re-rating vs de-rating over time.
39. **Median historical P/E band** — Compare current P/E to its own 5-year median (Screener's "P/E vs median" idea).
40. **Data-freshness label per statement** — Show "as of Q_ FY__" so the user knows how stale a figure is.

## C. Screener-style query engine (rule-based screens) — 20

41. **Custom screen definitions in config** — Let the user define screens as deterministic rule sets (no LLM), e.g. `roe>15 AND debt_to_equity<0.5`.
42. **Screen DSL parser** — A tiny, safe expression evaluator over the fundamentals dict (whitelisted fields/operators only).
43. **Run screen across the universe** — Apply a screen to `universe.py` symbols and return matches, ranked.
44. **Prebuilt "quality" screen** — High ROCE, low debt, consistent profit growth.
45. **Prebuilt "value" screen** — Low P/E and P/B vs sector median with positive earnings.
46. **Prebuilt "momentum + quality" screen** — Combine `quant.py` score with fundamental gates.
47. **Prebuilt "turnaround" screen** — Improving OPM and falling debt over recent years.
48. **Prebuilt "high dividend" screen** — Yield above threshold with sustainable payout.
49. **Prebuilt "52-week-high breakout + strong fundamentals"** — Marries technical positioning to balance-sheet health.
50. **Sector-relative screening** — Compare each stock's ratios to its own sector's median, not absolute cutoffs.
51. **Screen result → watchlist push** — One click to add screen hits to the watchlist.
52. **Saved screens with names** — Persist user screens in the journal DB.
53. **Screen scheduling** — Run a screen every morning pre-open and Telegram the new entrants.
54. **"Fell out of screen" alert** — Notify when a held name no longer passes its screen (fundamental deterioration).
55. **Backtest a screen** — Replay a screen historically to see how its picks would have performed (uses existing backtest engine).
56. **Screen coverage report** — How many universe symbols have enough data to be screened.
57. **Multi-condition AND/OR grouping** — Parenthesised logic in the DSL.
58. **Percentile-rank screens** — "Top 20% by ROCE in the universe" style cross-sectional ranking.
59. **Exclusion lists** — Drop specific sectors/symbols from any screen (e.g. skip financials for D/E rules).
60. **Screen diff vs yesterday** — Show which names entered/exited the screen since last run.

## D. Valuation & intrinsic value — 15

61. **DCF calculator (deterministic)** — User-supplied growth/discount assumptions → intrinsic value per share.
62. **Reverse DCF** — Back out the growth rate the current price implies.
63. **Graham number** — √(22.5 × EPS × book value) classic fair-value line.
64. **Earnings yield vs 10y G-Sec** — Compare stock earnings yield to the risk-free rate.
65. **PEG ratio** — P/E divided by earnings growth, computed locally.
66. **EV/EBITDA** — Enterprise value multiple for cross-company comparison.
67. **Fair-P/E band overlay** — Plot price vs "median P/E × EPS" band on the chart.
68. **Margin-of-safety flag** — Distance between price and intrinsic value, colour-coded.
69. **Dividend discount model** — For steady dividend payers.
70. **Sum-of-parts placeholder** — Manual segment inputs for conglomerates.
71. **Sensitivity table** — Intrinsic value across a grid of growth × discount assumptions.
72. **Historical valuation percentile** — Where today's multiple sits in its 10-year range.
73. **Sector median multiples** — Auto-compute sector P/E, P/B, EV/EBITDA medians from the universe.
74. **Valuation snapshot on idea cards** — Show cheap/fair/expensive tag next to each signal.
75. **Valuation change alerts** — Notify when a watched stock crosses from expensive to fair.

## E. Fundamental alerts & monitoring — 15

76. **Results-date calendar** — Track upcoming quarterly result dates per holding.
77. **Pre-results reminder** — Telegram alert N days before a holding reports.
78. **Post-results delta** — Auto-compare new quarter vs prior on sales/PAT/OPM.
79. **Earnings-surprise flag** — Actual vs the trailing trend (deterministic, no estimates model).
80. **Promoter-pledge-increase alert** — Red flag when pledge % rises.
81. **Promoter-holding-drop alert** — Notify on promoter selling.
82. **FII/DII flow shift alert** — Institutional holding changes quarter over quarter.
83. **Debt-spike alert** — Borrowings up sharply year over year.
84. **Margin-compression alert** — OPM falling for two consecutive quarters.
85. **Auditor/credit-rating change feed** — From exchange announcements.
86. **Dividend declaration alert** — New dividend/record-date announced.
87. **Bonus/split/rights alert** — Corporate actions that affect your position math.
88. **Block/bulk deal alert** — Large trades in a watched name from NSE/BSE feeds.
89. **Insider-trading disclosure alert** — SAST/PIT disclosures from the exchanges.
90. **52-week-high/low fundamental cross-check** — Alert when a technical extreme coincides with a fundamental change.

## F. Peer & sector comparison — 12

91. **Peer table per symbol** — Ratios side-by-side with same-sector names from the universe.
92. **Sector heatmap** — Colour grid of P/E, ROCE, growth across a sector.
93. **Relative-strength vs sector** — Stock return minus sector-average return.
94. **Best-in-sector highlight** — Flag the leader on each key ratio.
95. **Sector rotation view** — Which sectors are trending by aggregate momentum.
96. **Sector average fundamentals** — Median ratios cached per sector.
97. **Correlation matrix of holdings** — Deterministic pairwise return correlation (feeds diversification checks).
98. **Overlap/concentration warning** — Flag when too much capital sits in one sector.
99. **Peer momentum ranking** — Combine `quant.py` scores within a peer group.
100. **Sector-vs-NIFTY spread** — How a sector is doing relative to the index.
101. **Market-cap-band comparison** — Compare against large/mid/small-cap peers appropriately.
102. **Peer valuation percentile** — Where a stock ranks on cheapness within its peers.

## G. Portfolio & watchlist analytics — 18

103. **Portfolio fundamental roll-up** — Weighted-average P/E, ROE, D/E across holdings.
104. **Portfolio sector allocation pie** — Exposure by sector.
105. **Portfolio market-cap allocation** — Large/mid/small split.
106. **Weighted portfolio beta** — Aggregate beta from `quant.py` betas.
107. **Portfolio volatility & Sharpe** — Deterministic from combined return series.
108. **Portfolio max-drawdown tracker** — Rolling peak-to-trough of total equity.
109. **Concentration (Herfindahl) index** — Numeric diversification score.
110. **Correlation-aware position sizing hint** — Warn when adding a highly correlated name.
111. **Portfolio dividend income projection** — Annual expected dividends from holdings.
112. **Portfolio valuation percentile** — Aggregate cheap/expensive read.
113. **Watchlist scorecard** — `quant.py` score + key fundamentals in one sortable table.
114. **Watchlist sorting/filtering** — By score, momentum, P/E, sector, etc.
115. **Watchlist tags/groups** — User-defined buckets (e.g. "core", "tactical").
116. **Watchlist bulk import from CSV** — Paste a list of symbols to seed a watchlist.
117. **Portfolio vs NIFTY benchmark curve** — Overlay equity vs index.
118. **Rolling factor exposure** — Momentum/value/size tilt of the current book.
119. **What-if position simulator** — Add a hypothetical position and see portfolio metrics shift.
120. **Rebalance suggestion (rule-based)** — Flag positions over/under target weight (no LLM).

## H. Technical & chart additions — 20

121. **Bollinger Bands** — Add to `indicators.py` as pure functions.
122. **MACD** — Deterministic MACD line/signal/histogram.
123. **Supertrend** — Popular NSE intraday overlay.
124. **VWAP bands** — Extend the existing VWAP with standard-deviation bands.
125. **Pivot points (classic/Fibonacci)** — Daily support/resistance levels.
126. **Volume profile / VPOC** — Where volume concentrated by price.
127. **OBV (on-balance volume)** — Volume-trend confirmation.
128. **ADX / DMI** — Trend-strength gauge for the regime classifier.
129. **Stochastic oscillator** — Overbought/oversold beyond RSI.
130. **Ichimoku cloud** — Multi-signal trend overlay.
131. **Donchian channels** — Breakout reference used by turtle-style rules.
132. **Keltner channels** — ATR-based envelope.
133. **Anchored VWAP from a date** — VWAP from a chosen event (results day, breakout).
134. **Relative strength vs NIFTY line** — Ratio chart, not RSI.
135. **Candlestick pattern flags** — Deterministic engulfing/hammer/doji detection.
136. **Support/resistance auto-levels** — Swing-high/low clustering.
137. **Gap detector** — Flag opening gaps for the Gap-and-Go strategy context.
138. **Multi-timeframe view** — Daily + weekly candles side by side.
139. **Drawdown shading on chart** — Visualise underwater periods.
140. **Indicator overlays toggle** — Let the user turn each overlay on/off on the dashboard chart.

## I. Data export, reporting & journaling extras — 20

141. **Fundamentals → Excel export** — One-click XLSX of the ratio + statement tables.
142. **Screen results → CSV/XLSX** — Export any screen output.
143. **Per-stock PDF factsheet** — Profile, ratios, chart snapshot, quant verdict in one page.
144. **Portfolio monthly PDF report** — Holdings, performance, allocation.
145. **Financial-year (Indian FY) PnL report** — April–March realised gains for tax prep.
146. **Capital-gains STCG/LTCG split** — Deterministic holding-period classification.
147. **Trade tax-lot tracking** — FIFO lot matching for accurate cost basis.
148. **Contract-note reconciliation import** — Match broker notes to journal entries.
149. **Dividends-received log** — Track dividend income per FY.
150. **Charges/brokerage breakdown export** — From `costs.py`, per trade.
151. **Watchlist snapshot export** — Point-in-time scorecard to file.
152. **Backtest results export** — Trades + equity curve to CSV.
153. **Idea audit export** — Every signal emitted with inputs, for review.
154. **Screener-style company "story" text block** — Deterministic template summarising ratios (no LLM — string templating from numbers).
155. **Printable daily trade plan** — Today's ideas + stops/targets on one page.
156. **Weekly review digest email/Telegram** — Auto-generated performance recap.
157. **Data quality report** — Which symbols are missing fundamentals/candles.
158. **Downloadable journal DB backup** — Since Render disk is ephemeral.
159. **Google Sheets export option** — Push tables to a sheet for the user.
160. **Notion/Obsidian markdown export** — Factsheets as markdown notes.

## J. Automation, UX & platform conveniences — 20

161. **Morning pre-open briefing** — Universe scan + screen entrants + results-today, via Telegram.
162. **End-of-day summary** — Fills, PnL, stops moved, tomorrow's watch.
163. **Scheduled fundamentals refresh** — Nightly cache warm so cards load instantly.
164. **On-demand "analyse this symbol" command** — Telegram `/analyse SYMBOL` returns quant + fundamentals.
165. **Symbol search with fuzzy match** — Type a name, resolve to NSE symbol.
166. **Global command palette in dashboard** — Keyboard-driven quick actions.
167. **Fundamentals card on every idea/position** — Inline P/E, ROE, D/E next to the signal.
168. **"Why this idea" explainer panel** — Deterministic list of the rules that fired.
169. **Watchlist quick-add from any table** — Star icon everywhere a symbol appears.
170. **Compare drawer** — Pin 2–4 symbols for side-by-side quant + fundamentals.
171. **Dark/light theme toggle** — Persisted preference.
172. **Configurable dashboard tiles** — Show/hide/reorder cards.
173. **Mobile-optimised fundamentals view** — Responsive tables.
174. **Offline cache of last snapshot** — View last data when the backend is cold.
175. **Multi-currency display** — INR for NSE, USD for US tickers, with clear labels.
176. **Symbol notes** — Free-text notes per symbol persisted in the journal.
177. **Alert preferences per event type** — Choose which fundamental alerts fire.
178. **Quiet hours / DND window** — Suppress non-critical alerts overnight.
179. **Rate-limit-aware data scheduler** — Central queue so Groww/yfinance/Screener calls never burst.
180. **Health panel for all data sources** — Green/amber/red per adapter (groww, yfinance, screener).

## K. Backtest & research extensions — 20

181. **Fundamental-gated backtests** — Replay strategies with a fundamental filter applied historically.
182. **Screen backtest with rebalancing** — Periodic re-screen and rotate.
183. **Walk-forward validation** — Rolling in-sample/out-of-sample windows.
184. **Monte Carlo trade-order shuffle** — Distribution of outcomes, deterministic seed.
185. **Parameter sweep grid** — Test ORB/positional params across ranges, tabulate.
186. **Benchmark-relative backtest stats** — Alpha vs NIFTY, not just absolute return.
187. **Per-strategy attribution** — Which of the `_STRATEGIES` contributed the PnL.
188. **Regime-conditional performance** — Returns split by `market_regime()` state.
189. **Drawdown & recovery analytics** — Longest underwater period, recovery time.
190. **Trade-expectancy & Kelly fraction** — Deterministic sizing research output.
191. **Slippage/impact sensitivity** — Re-run with different slippage assumptions.
192. **Cost-sensitivity report** — PnL vs brokerage assumptions from `costs.py`.
193. **Sharpe/Sortino/Calmar suite** — Full risk-adjusted metric set.
194. **Rolling correlation of strategy to index** — Diversification of the signal itself.
195. **Backtest reproducibility hash** — Stamp each run with a config+data hash.
196. **Fixture-based fast backtests** — Recorded candles so CI can run without live creds.
197. **Backtest vs live parity check** — Assert the engine replays identically (matches your hard rule).
198. **Survivorship-bias note & delisted handling** — Flag universe gaps.
199. **Multi-symbol portfolio backtest** — Concurrent positions with the heat cap enforced.
200. **Research notebook export** — Dump a run's inputs/outputs for offline analysis (no LLM in the loop).

---

### Suggested priority (given your no-LLM, human-in-the-loop, single-user design)

Highest leverage first: **Section B** (own your fundamentals from clean sources) →
**Section C** screener query engine → **Section E** fundamental alerts →
**Section G** portfolio analytics. Treat **Section A** (direct Screener.in scraping)
as optional and off-by-default because of the ToS/blocking risk — the same data is
reachable through B.
