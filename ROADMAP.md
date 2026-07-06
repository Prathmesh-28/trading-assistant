# Roadmap — missing features

An honest gap analysis: 230+ features the tool doesn't have yet, grouped by
category, each one line. **P1** = directly improves "which stock to sell, when,
and how" (the core ask). **P2** = strong value soon after. **P3** = later.
Within a section, roughly ordered by impact.

## A. Exit intelligence — when & how to sell (the core gap)

1. **P1** Trailing-stop engine on live positions — auto-raise the stop as price rises (Chandelier/ATR), alert "raise your stop to ₹X" instead of today's static stop
2. **P1** Partial-exit plans — "sell half at 1R, trail the rest", tracked per position with separate alerts per tranche
3. **P1** Break-even alert — the moment a position reaches +1R, alert "move stop to entry — this trade can no longer lose"
4. **P1** Time stop for positional — alert to exit stagnant trades (e.g. 20 sessions without progress toward target; capital sitting dead)
5. **P1** Exit-signal detection — alert when the ENTRY conditions reverse (EMA cross back down, close below Supertrend, Donchian low break) even if stop isn't hit
6. **P1** End-of-day positional review push — after close, one message per open position: "hold / tighten stop / exit tomorrow at open", with reason
7. **P1** Gap-risk warning — pre-close alert when an intraday position is near stop and holding overnight would risk a gap through it
8. **P1** Momentum-fade sell signal — RSI divergence at highs, volume drying up on advance, close below VWAP after a runner
9. **P1** Target-extension logic — when price hits target with strong trend (ADX rising), suggest trailing instead of booking, with the new suggested stop
10. **P1** "Why sell now" line from Fable on every exit alert (like entries have)
11. **P1** Stop distance sanity monitor — alert when a position's stop is >2×ATR away (stale stop after volatility drop; tighten it)
12. **P1** Position aging report in /status — days held, R progress, whether the original thesis (trigger reason) still holds
13. **P1** Weakest-holding ranking — when portfolio heat is maxed and a new signal fires, tell which existing position is weakest and could be rotated out
14. **P2** Structured exit checklist per sell alert — market order vs limit, suggested limit price from current spread, expected slippage
15. **P2** Scale-out ladder generator — given a position, propose 3-tranche exits at 1R/1.5R/2R with quantities
16. **P2** Earnings-date exit rule — alert to exit/reduce positional holdings N days before earnings (event risk)
17. **P2** Correlated-crash alert — when index drops >1.5% intraday, list open positions ranked by beta and suggest which to cut first
18. **P2** Stop-hunt detector — price wicked below stop and recovered within the bar: alert "stop was probed, not broken — reassess before selling"
19. **P2** Sector-weakness exit filter — sell alert strengthened when the stock's sector index also broke down
20. **P2** Trailing by structure — trail stop under the most recent swing low (not just ATR), updated daily for positional
21. **P2** Profit-give-back guard — alert when an open winner has given back >50% of its peak open profit
22. **P2** Exit quality score after every close — how much of the move did you capture vs the theoretical max (MFE/MAE analysis)
23. **P3** Volatility-regime exit adaptation — widen/tighten trailing stops automatically when ATR% regime changes
24. **P3** Options-hedge suggestion instead of sell — for CNC winners before events, suggest protective put cost vs exiting
25. **P3** Tax-aware exit timing — LTCG vs STCG countdown per holding; alert when waiting N days changes tax treatment

## B. Live monitoring & alerts

26. **P1** Price-approach warnings — alert at 90% of the way to stop ("prepare to sell") not just at the touch
27. **P1** Re-alert policy — if you don't /sold within N minutes of a stop-hit alert, re-ping with escalating urgency
28. **P1** Alert acknowledgement — track which alerts you've seen; unacknowledged critical alerts repeat
29. **P1** Watchlist proximity alerts — "RELIANCE is 0.5% from triggering the ORB entry" so you're ready before the signal
30. **P2** Multi-channel escalation — Telegram first, then push notification, then (optional) phone call via Twilio for stop-hits
31. **P2** Quiet hours / do-not-disturb config with critical-only override
32. **P2** Custom price alerts — /alert RELIANCE 2950 from the phone
33. **P2** Volume-spike alert on holdings — unusual volume in a position often precedes news
34. **P2** 52-week high/low proximity alerts for holdings
35. **P2** Circuit-limit alert — position hits upper/lower circuit (can't exit; plan for tomorrow)
36. **P3** Configurable alert templates — choose what data appears in each alert type
37. **P3** Alert digest mode — batch non-critical alerts into hourly summaries
38. **P3** Web-push notifications from the dashboard (no Telegram needed)
39. **P3** Wearable-friendly short alerts (Apple Watch length)
40. **P3** Text-to-speech alert option for hands-free driving hours

## C. Data & market feeds

41. **P1** GrowwFeed WebSocket for real-time LTP+volume (replaces polling; true VWAP instead of SMA fallback; faster stop detection)
42. **P1** India VIX feed — display + use as position-sizing dampener (smaller size when VIX elevated)
43. **P1** NIFTY/BANKNIFTY index live quotes on dashboard (market context at a glance)
44. **P1** Market breadth: % of watchlist above 200-DMA / advancers-decliners as a regime input
45. **P2** Earnings calendar integration — flag symbols with results in next 5 sessions
46. **P2** Corporate actions feed — dividends, splits, bonuses (these break your candle history and stops)
47. **P2** News headlines per holding (RSS/GDELT) piped into Fable's avoid-list pass
48. **P2** Bulk/block deal disclosures for held stocks (institutions exiting = signal)
49. **P2** Delivery-percentage data — high delivery % on up days = conviction buying
50. **P2** FII/DII daily flow numbers as market-context input
51. **P2** Sector indices tracking — map each holding to its sector index for relative strength
52. **P3** Candle-data cache layer (SQLite) — stop re-fetching 320 days of history every scan
53. **P3** Data-quality monitor — alert when Groww returns stale/missing candles
54. **P3** Backup data source (Yahoo Finance .NS) with automatic failover
55. **P3** Pre-market/post-market session data where available
56. **P3** Futures open interest for held underlyings (OI buildup direction)
57. **P3** Intraday tick storage for later replay/analysis of your actual alert timings
58. **P3** Currency (USDINR) context for IT/pharma exporter holdings
59. **P3** Global cues snapshot — S&P futures, SGX Nifty at market open
60. **P3** Upper/lower circuit band data per symbol (know the exit constraint before entering)

## D. Signals & strategies

61. **P1** Relative-strength ranking — only take positional entries in the top-quartile RS stocks of the watchlist (best-evidenced momentum filter)
62. **P1** Volume confirmation on positional entries — breakout on >1.5× average volume is a different trade than on dry volume
63. **P2** Pullback-to-support entry — retest of broken Donchian/OR level (better R:R than chasing)
64. **P2** Gap-and-go intraday strategy — paper's companion setup to ORB (gap >2% with volume, first pullback entry)
65. **P2** 52-week-high breakout strategy (well-evidenced momentum anomaly)
66. **P2** Mean-reversion short-term dip buy (RSI(2) <10 above 200-DMA — Connors variant, strong equity evidence)
67. **P2** Inside-bar / NR7 volatility-contraction setups for positional
68. **P2** Multi-timeframe confirmation — weekly trend must agree with daily entry
69. **P2** Signal strength score 0-100 on every idea (how many optional confirmations aligned) instead of LOW/MED/HIGH
70. **P2** Strategy on/off switches from the phone — /disable macd, /enable donchian
71. **P3** Anchored VWAP from swing lows/highs as dynamic support/resistance
72. **P3** Opening range variations — 15-min/30-min OR backtested against 5-min
73. **P3** Sector-rotation overlay — overweight signals from the strongest 3 sectors
74. **P3** Pairs/relative-value ideas within sectors (long strongest vs avoid weakest)
75. **P3** Pre-earnings drift setup (well-documented anomaly, needs earnings calendar)
76. **P3** Short-side positional strategies behind an explicit toggle (currently long-only)
77. **P3** Weekly-chart positional strategies for longer holds (months)
78. **P3** Composite conviction score combining all strategies that agree on a symbol
79. **P3** Custom user-defined scan rules via simple config (EMA/RSI/volume thresholds)
80. **P3** Seasonality hints (budget month, results seasons) as context, not triggers

## E. Risk & position management

81. **P1** Live portfolio heat gauge on dashboard — total open risk as % of capital, colored green/amber/red
82. **P1** Per-position risk display — ₹ at risk if stop hits, as % of capital, everywhere positions are shown
83. **P1** Daily loss limit alert (recommend mode) — realized+unrealized down 3R today: "stop trading today" push
84. **P1** Sector concentration warning — >40% of open risk in one sector
85. **P1** Correlation warning — new idea correlates >0.8 with an existing position (you'd be doubling the same bet)
86. **P2** Volatility-adjusted sizing — size by ATR so every position risks equal ₹ per ATR move (replaces fixed % on price distance)
87. **P2** Consecutive-loss cooldown — after 3 straight losses, halve size for the next N ideas (automatic, from the diagnostics research)
88. **P2** Equity-curve-based size scaling — reduce size when account below its 20-day equity MA
89. **P2** Kelly-fraction calculator from journal stats (display only; suggest fraction of it)
90. **P2** Max-positions-per-sector cap alongside the global cap
91. **P2** Overnight vs intraday risk budgets tracked separately
92. **P2** Margin/capital tracker — how much capital is deployed vs free, factoring MIS leverage
93. **P3** Drawdown-based kill switch for recommend mode (pause new ideas at 10% account DD)
94. **P3** Risk parity weighting option across concurrent positions
95. **P3** Scenario stress test — "if every open position hit its stop tomorrow, account impact = X"
96. **P3** Beta-adjusted exposure — net portfolio beta to NIFTY displayed live
97. **P3** Event-risk calendar overlay — reduce size before RBI/Fed/budget days
98. **P3** Per-strategy risk budgets — cap how much total risk each strategy can deploy
99. **P3** Position pyramiding rules — add to winners at defined R levels with reduced size
100. **P3** Risk report card pushed weekly — heat usage, largest loss, rule violations

## F. Portfolio & holdings analytics

101. **P1** Actual Groww holdings sync — pull real positions/holdings from the API so the tool knows what you ACTUALLY own (not just what you told it)
102. **P1** Reconciliation alerts — position in Groww but not tracked here (or vice versa): "you own X untracked — /watch it?"
103. **P1** Unrealized PnL on ALL demat holdings, not just tool-originated trades
104. **P2** Average-cost tracking across multiple buys of the same symbol
105. **P2** Portfolio allocation view — pie by stock/sector/strategy/horizon
106. **P2** Benchmark comparison — your equity curve vs NIFTY50 over the same period, alpha number
107. **P2** Dividend tracking on CNC holdings
108. **P2** XIRR calculation (money-weighted return — the honest number when capital moves in/out)
109. **P3** Multi-account support (family accounts) with separate risk budgets
110. **P3** Cash-flow ledger — deposits/withdrawals so returns aren't distorted
111. **P3** Historical portfolio snapshots — what did I hold on any past date
112. **P3** Per-holding contribution-to-return analysis
113. **P3** What-if analyzer — "if I sold X and bought Y" impact on heat/correlation
114. **P3** Watchlist manager from phone/dashboard — /add SYMBOL, /remove SYMBOL, multiple named lists
115. **P3** Universe expansion — scan all NIFTY200 for positional (not just 10 names) with liquidity screen

## G. Backtesting & validation

116. **P1** Walk-forward analysis — split history into windows, report consistency rate (already researched; code in reference/vibe-trading)
117. **P1** Per-strategy attribution in backtest — which of the 5 cascade strategies actually makes money (currently aggregated)
118. **P1** Parameter sensitivity sweep — show ATR-multiplier/EMA-length neighborhoods, flag fragile cliff-edge parameters
119. **P2** Backtest from the dashboard — run/view backtests in the UI instead of CLI
120. **P2** Bootstrap Sharpe confidence intervals (code preserved in reference/)
121. **P2** Regime-segmented results — performance in bull/bear/range segments separately
122. **P2** Intraday backtest on 1-min data for exit precision (reduces ambiguous-bar rate)
123. **P2** Benchmark-relative metrics — information ratio vs NIFTY (reference/ has the formulas)
124. **P2** Survivorship-bias-safe universe — backtest against historical index constituents (the research flagged ~4.9pp/yr inflation on small caps)
125. **P2** Automated nightly backtest regression — strategies re-validated on latest data; alert if edge decays below threshold
126. **P3** Grid-search harness for parameter tuning with overfit guard (train/validate split)
127. **P3** Monte Carlo on returns (not just trade order) — richer risk-of-ruin estimates
128. **P3** Slippage sensitivity — re-run at 0/5/10/20bps to see edge fragility
129. **P3** Multi-symbol portfolio backtest with the heat caps applied (currently per-symbol sequential)
130. **P3** Backtest result archive with run-cards (config + data + code hash per run)
131. **P3** A/B comparison view — two parameter sets side by side
132. **P3** Trade-replay visualizer — step through any historical trade bar by bar on a chart
133. **P3** Execution-timing backtest — how much did the 20s polling delay cost vs instant fills
134. **P3** Costs-model validation — compare modeled costs vs actual Groww contract notes
135. **P3** Out-of-sample lockbox — auto-reserve the most recent 6 months, never tune on it

## H. Journal & performance review

136. **P1** Slippage tracking — alert price vs your actual /bought /sold fill price, per trade and aggregated (are alerts actionable in time?)
137. **P1** MFE/MAE per trade — max favorable/adverse excursion: were stops too tight? targets too close?
138. **P1** Exit-reason performance — stopped-out vs target-hit vs discretionary exits: which of YOUR exits add value vs the system's
139. **P2** Discipline score — how often you took ideas, skipped, overrode stops; correlated with outcomes
140. **P2** Weekly performance email/push — trades, win rate, R distribution, best/worst, vs NIFTY
141. **P2** Equity curve chart on dashboard (realized + open, daily granularity)
142. **P2** R-multiple distribution histogram
143. **P2** Per-strategy live performance vs its backtest expectation (drift detection)
144. **P2** Journal notes — attach a text note to any trade from the phone (/note RELIANCE exited early, felt weak)
145. **P2** Postgres journal option wired up (currently ephemeral SQLite on Render)
146. **P3** Trade screenshots — auto-capture the chart at entry and exit for every trade
147. **P3** Calendar heatmap of daily PnL
148. **P3** Time-of-day/day-of-week performance breakdown
149. **P3** Holding-period analysis — where does your edge peak (3 days? 3 weeks?)
150. **P3** CSV/Excel export of the journal
151. **P3** Monthly PDF report generation
152. **P3** Emotion tagging on trades (confident/fearful/FOMO) for behavioral review
153. **P3** Fable-written monthly review — narrative analysis of your trading patterns from the journal

## I. Dashboard & UX

154. **P1** Price charts — candlestick chart per symbol with entry/stop/target lines drawn (currently no charts at all!)
155. **P1** Position detail view — tap a position for full history: entry alert, fills, stop moves, all alerts
156. **P1** Manual /watch from the dashboard — add an untracked trade with a form (currently Telegram-only... exists via API but no UI form)
157. **P1** Edit stop/target from the dashboard — you decided to trail manually; tell the tool so alerts follow YOUR levels
158. **P2** Login/auth on the dashboard + API (currently anyone with the URL controls it)
159. **P2** Idea history view — all past SUGGESTED ideas incl. skipped/expired, with what happened after (did skipped ideas work?)
160. **P2** Watchlist live-quote grid — all 10 symbols with LTP, %change, distance-to-signal
161. **P2** Sparkline per position — today's price path vs your entry/stop/target
162. **P2** Dark/light theme toggle persistence + PWA installability (Add to Home Screen with icon)
163. **P2** Sound on critical alerts in the browser
164. **P2** Regime/bias history timeline — how Fable's read evolved through the day
165. **P3** Command palette — keyboard-driven actions on desktop
166. **P3** Customizable dashboard layout (reorder/hide cards)
167. **P3** Multi-day PnL calendar view
168. **P3** Correlation heatmap of holdings (code in reference/vibe-trading)
169. **P3** Onboarding tour for the dashboard
170. **P3** Offline-tolerant PWA shell with last-snapshot cache
171. **P3** Desktop layout — multi-column on wide screens (currently mobile-only design)
172. **P3** Live engine log viewer (tail the server log in the UI)
173. **P3** Localized number formats and IST/exchange-time toggles

## J. Telegram & command UX

174. **P1** Inline buttons on idea alerts — [Bought] [Skip] taps instead of typing /bought RELIANCE
175. **P1** /chart SYMBOL — send a rendered chart image to the phone
176. **P2** /why SYMBOL — re-explain any active idea's thesis on demand
177. **P2** /risk — portfolio heat summary on demand
178. **P2** Natural-language commands via Fable — "sold half my reliance at 2960" parsed into structured action
179. **P2** /quote SYMBOL — LTP + day stats for anything, not just watchlist
180. **P3** Morning briefing push — pre-market plan: regime, levels to watch, positions review
181. **P3** /backtest SYMBOL from the phone
182. **P3** Voice-note replies transcribed into commands
183. **P3** Multi-user support with roles (view-only for a friend/advisor)
184. **P3** /snooze SYMBOL 30m — pause alerts for one position briefly

## K. Fable / LLM analyst layer

185. **P1** News-driven avoid-list actually wired — feed real headlines (feature 47) into the pre-market pass; currently Fable guesses from prices alone
186. **P2** Exit-review pass — every evening Fable reviews each open position against fresh data: "thesis intact / weakening / broken"
187. **P2** Post-trade coach — after each close, one line on what the journal says about this pattern of yours
188. **P2** Anomaly narrator — when a holding moves >2σ intraday, Fable explains what's knowable (news, sector, index move)
189. **P3** Trade-idea devil's advocate — one-line strongest argument AGAINST each idea alongside the "why"
190. **P3** Weekly strategy-drift memo — Fable compares recent live results vs backtest stats and flags divergence in plain language
191. **P3** Config tuning suggestions in natural language from journal analysis
192. **P3** Chat-with-your-journal — ask "how do I do on Mondays?" in the dashboard
193. **P3** Model cost tracking + budget cap for the Fable layer
194. **P3** Prompt-injection hardening if news text ever flows into prompts (treat headlines as data, never instructions)

## L. Execution & broker integration (beyond recommend mode)

195. **P2** One-tap GTT order placement — on /bought, offer to place a Groww GTT stop-loss order server-side so the stop is REAL even when the tool sleeps
196. **P2** Order-status webhook/polling — see your actual Groww order fills inside the tool
197. **P2** Bracket-order helper for intraday (entry + stop + target as one instruction where supported)
198. **P3** Semi-auto mode — engine prepares the order, you approve with one tap, it places (needs SEBI/algo review)
199. **P3** Basket exit — "close all intraday" as one action at 15:15
200. **P3** Contract-note import — parse Groww contract notes to true-up fills/costs in the journal
201. **P3** Multi-broker abstraction (Zerodha Kite as alternate adapter)
202. **P3** Simulated-execution paper mode with realistic latency/slippage for forward-testing new strategies live

## M. Infrastructure & reliability

203. **P1** Keep-alive strategy for Render free tier OR paid tier — the engine MUST NOT sleep during market hours (stops go unmonitored!)
204. **P1** State persistence across restarts — pending/active positions rebuilt from journal on boot (currently in-memory; a Render restart forgets your open positions)
205. **P1** Health monitoring + uptime alerts — YOU get told when the engine is down (UptimeRobot ping + Telegram)
206. **P2** Render auto-deploy on push verified + deploy notifications to Telegram
207. **P2** Graceful shutdown — flush alerts, snapshot state before Render restarts the dyno
208. **P2** Structured logging with request IDs; error aggregation (Sentry free tier)
209. **P2** Config hot-reload — change watchlist/risk without restart
210. **P2** Rate-limit guard + exponential backoff on all Groww calls
211. **P3** Metrics endpoint (Prometheus-style) — loop latencies, API error rates, alert delivery times
212. **P3** Blue-green deploy or at least deploy-during-market-hours guard
213. **P3** Automated DB backups (journal to object storage nightly)
214. **P3** Docker compose for one-command local dev
215. **P3** CI on GitHub Actions — smoke test + backtest unit tests + frontend build on every push
216. **P3** pytest suite properly in tests/ (port the scratch tests)
217. **P3** Type checking (mypy) + linting (ruff) in CI
218. **P3** Load-test the WebSocket fan-out (N phones connected)
219. **P3** Timezone/holiday calendar — NSE holidays, half-days (Muhurat trading!) so loops don't run/alert on closed days
220. **P3** Secrets rotation reminder + .env validation on boot (fail fast on malformed config)

## N. Compliance, tax & records (India)

221. **P2** STCG/LTCG classification per closed trade with FY summaries
222. **P2** FY-end tax report — realized gains by category, ready for ITR
223. **P2** Audit-grade immutable journal (append-only, hash-chained) for your own records
224. **P3** Turnover calculation for tax-audit-applicability check (intraday = speculative business income)
225. **P3** SEBI algo-rules watcher — checklist gate before ever enabling execute mode
226. **P3** Contract-note vs journal reconciliation report
227. **P3** Advance-tax quarterly estimate from realized PnL

## O. Learning & adaptive (rule-based, no ML in the loop)

228. **P3** Strategy decay detection — rolling 30-trade window win-rate/PF control chart per strategy; auto-flag when below backtest confidence band
229. **P3** Adaptive parameter re-fit — quarterly re-run of the grid search on trailing data, with human approval before applying
230. **P3** Skipped-idea tracker — outcomes of ideas you DIDN'T take (is your discretion adding or destroying value?)
231. **P3** Signal-quality feedback loop — which confirmation combos (RVOL, regime, breadth) correlated with winners; re-weight confidence labels
232. **P3** Personal trading-hours analysis — your fill quality by time of day (are you slow to act after 14:00?)
233. **P3** Anti-overtrading governor — flag when idea frequency doubles vs baseline (usually regime chop, not opportunity)

---

### If you only build ten of these

The ten that most directly answer "which stock to sell, when, and how":

1. Trailing-stop engine with "raise your stop to ₹X" alerts (#1)
2. Exit-signal detection — entry conditions reversed (#5)
3. Real Groww holdings sync + reconciliation (#101, #102)
4. State persistence across restarts (#204) — without this, a Render restart silently stops monitoring your stops
5. Keep-alive/paid tier during market hours (#203) — same reason
6. Break-even + partial-exit alerts (#2, #3)
7. End-of-day hold/tighten/exit review per position (#6)
8. GTT stop-loss placement so stops are real even offline (#195)
9. Price charts with your levels drawn on them (#154)
10. Slippage tracking — proves whether alerts are actionable in time (#136)
