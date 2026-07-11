# 200 Common Baseline Features Every Trading Bot Needs

A generic checklist of the fundamentals a production trading bot should cover, each with a
one-line note. Use it to audit any bot (yours included). Grouped by subsystem.

> Fit to this project: items are framed to respect a deterministic, **no-LLM-in-runtime**,
> human-in-the-loop, fail-soft design. Where an item assumes auto-execution, the manual/
> signal-only equivalent is noted.

---

## 1. Market data & feeds (20)
1. **Live price feed (LTP)** — Real-time last-traded price for every watched symbol.
2. **OHLCV candles** — Intraday and daily bars as the base for indicators.
3. **Historical data access** — Enough history to warm up indicators and backtest.
4. **Multiple timeframes** — 1m/5m/15m/daily/weekly from one source.
5. **Depth / order book (L2)** — Bid/ask sizes for spread and liquidity checks.
6. **Corporate-action adjustment** — Splits/bonus/dividends adjusted in price history.
7. **Symbol master / instrument list** — Canonical tradable-symbol reference.
8. **Exchange token / ISIN mapping** — Stable identifiers, not just tickers.
9. **Market-hours awareness** — Know open/close/pre-open/post-close windows.
10. **Trading-holiday calendar** — Skip non-trading days automatically.
11. **Data staleness detection** — Flag/halt when quotes stop updating.
12. **Gap & missing-candle handling** — Detect and policy-handle absent bars.
13. **Duplicate-tick dedup** — Ignore repeated/late ticks.
14. **Timezone normalisation** — Consistent exchange-local time (IST) with labels.
15. **Data source failover** — Secondary feed when primary fails.
16. **Reconnect with backoff** — Resilient websocket/API reconnection.
17. **Rate-limit handling (429)** — Detect and cool down on throttling.
18. **Circuit-limit / band awareness** — Know upper/lower price bands.
19. **Data caching layer** — Cache history to cut API calls.
20. **EOD reconciliation** — Verify intraday data against official close.

## 2. Strategy & signal generation (20)
21. **Rule-based signal engine** — Deterministic entry/exit logic.
22. **Multiple strategies** — Support more than one concurrent approach.
23. **Strategy priority/ordering** — Defined precedence when signals conflict.
24. **One-idea-per-symbol guard** — Avoid duplicate signals on the same name.
25. **Configurable parameters** — Tunable thresholds without code edits.
26. **Indicator library** — RSI, ATR, VWAP, moving averages, etc.
27. **Market-regime classifier** — Trend/range/high-vol context gate.
28. **Entry-condition gating** — Only fire when all conditions align.
29. **Signal confidence/score** — Rank signals deterministically.
30. **Signal expiry** — Ideas go stale after a window.
31. **Index/breadth filter** — Suppress longs in a weak market.
32. **Liquidity/volume filter** — Skip illiquid names.
33. **Price/tick-size validity** — Round to valid ticks.
34. **Long & short support** — Both directions where allowed.
35. **Intraday vs positional modes** — Separate horizons.
36. **Signal deduplication** — No repeated alerts for one setup.
37. **Cooldown after loss/stop** — Avoid immediate re-entry.
38. **Reason/explanation per signal** — Which rules fired.
39. **Paper/live signal separation** — Clearly label non-live ideas.
40. **Strategy enable/disable toggle** — Turn strategies off individually.

## 3. Order management (20)
41. **Order ticket construction** — Symbol, side, qty, type, price assembled cleanly.
42. **Market orders** — Immediate execution type.
43. **Limit orders** — Price-capped orders.
44. **Stop-loss orders** — Protective exit orders.
45. **Stop-limit orders** — Stop with price cap.
46. **Bracket / OCO orders** — Entry + stop + target grouped.
47. **GTT / conditional orders** — Trigger-based orders.
48. **Order validation** — Reject bad qty/price before sending.
49. **Quantity sizing** — Compute qty from capital and risk.
50. **Tick-size rounding** — Prices snapped to exchange increments.
51. **Lot-size handling** — Respect F&O/lot constraints.
52. **Duplicate-order guard** — Prevent double submits.
53. **Idempotency keys** — Safe retries without double orders.
54. **Order status tracking** — Open/filled/partial/cancelled/rejected.
55. **Partial-fill handling** — Track remainder correctly.
56. **Order modification** — Amend price/qty/stop.
57. **Order cancellation** — Cancel working orders.
58. **Rejection reason capture** — Surface broker error messages.
59. **Manual-confirm flow** — (This bot) human places trade, bot records fill.
60. **Order audit trail** — Every order/command logged.

## 4. Execution & broker integration (15)
61. **Broker adapter abstraction** — Broker code isolated in one module.
62. **Authentication / token refresh** — Handle broker login + TOTP/session renewal.
63. **Fail-soft on broker errors** — Degrade, never crash the idea flow.
64. **Slippage awareness** — Model/limit adverse fills.
65. **Fill-price recording** — Capture actual execution price.
66. **Timeout handling** — Bound broker API waits.
67. **Retry with backoff** — Transient error resilience.
68. **Rate-limit compliance** — Stay under broker request caps.
69. **Order-to-position reconciliation** — Match fills to positions at boot.
70. **Multi-account support** — Optional, route by account.
71. **Sandbox / paper broker** — Test without real money.
72. **Funds/margin check** — Verify buying power before signalling.
73. **Contract-note ingestion** — Reconcile against broker records.
74. **Broker uptime monitoring** — Alert when the broker API is down.
75. **Credential isolation** — Only the adapter touches broker secrets.

## 5. Risk management (20)
76. **Per-trade risk cap** — Fixed % of capital at risk per idea.
77. **Position sizing by stop distance** — Qty from risk ÷ (entry − stop).
78. **Max positions cap** — Limit concurrent open trades.
79. **Portfolio heat cap** — Total open risk ceiling.
80. **Max daily loss / kill switch** — Halt after a loss threshold.
81. **Max ideas per day** — Cap signal volume.
82. **Per-symbol exposure limit** — No overconcentration in one name.
83. **Sector exposure limit** — Cap sector concentration.
84. **Correlated-position warning** — Flag highly correlated adds.
85. **Leverage/margin limit** — Bound borrowed exposure.
86. **Stop-loss enforcement** — Every position has a stop.
87. **Trailing stop** — Ratchet stops with favourable moves.
88. **Break-even move** — Shift stop to entry after a trigger.
89. **Give-back / profit-protect alert** — Warn when giving back gains.
90. **Time-based stop** — Exit stale positions after N days.
91. **Target/take-profit levels** — Defined exits.
92. **Reward:risk minimum** — Reject setups below an R threshold.
93. **Drawdown monitor** — Track equity peak-to-trough.
94. **Emergency flatten-all** — One action to exit everything.
95. **Circuit-breaker/halt awareness** — Don't trade halted names.

## 6. Position & portfolio management (15)
96. **Live position tracking** — Qty, avg price, current value.
97. **Unrealised PnL** — In currency and R-multiple.
98. **Realised PnL** — On closed trades.
99. **Average-down / pyramid handling** — Correct avg-price math.
100. **Scale-out / partial exit** — Reduce position in steps.
101. **Cost-basis tracking** — Net of charges.
102. **Portfolio value & cash** — Total equity and free capital.
103. **Exposure by sector/asset** — Allocation breakdown.
104. **Position aging** — Days held per trade.
105. **Stop/target proximity** — Distance to exits per position.
106. **Multi-asset support** — Equity/F&O/US as applicable.
107. **State restore on restart** — Rebuild positions after reboot.
108. **Reconciliation at boot** — Match internal state to broker.
109. **Open-risk summary** — Total risk currently live.
110. **Benchmark comparison** — Portfolio vs index.

## 7. Backtesting & research (15)
111. **Historical replay engine** — Bar-by-bar strategy simulation.
112. **Realistic fill model** — Next-bar-open or similar convention.
113. **Cost modelling** — Brokerage, STT, slippage in PnL.
114. **Same code as live** — Backtest reuses live strategy logic.
115. **Deterministic/reproducible** — Same inputs → same results.
116. **Performance metrics** — Win rate, expectancy, profit factor.
117. **Equity curve & drawdown** — Visual + max-DD stat.
118. **Sharpe/Sortino/Calmar** — Risk-adjusted returns.
119. **Parameter optimisation** — Grid/sweep with overfit caution.
120. **Walk-forward testing** — Out-of-sample validation.
121. **Benchmark-relative stats** — Alpha vs index.
122. **Trade-by-trade log** — Every simulated trade recorded.
123. **Multi-symbol portfolio backtest** — With risk caps enforced.
124. **Fixture data for CI** — Run tests without live creds.
125. **Backtest-vs-live parity check** — Assert identical replay.

## 8. Monitoring, alerts & observability (20)
126. **Health-check endpoint** — Liveness + component status.
127. **Engine heartbeat** — Prove the loop is running.
128. **Stall watchdog** — Alert when the data loop stops in-hours.
129. **Structured logging** — Machine-parseable logs.
130. **Log retention/rotation** — Bounded log growth.
131. **Error tracking** — Capture and surface exceptions.
132. **Trade/signal alerts** — Notify on new ideas.
133. **Fill/exit alerts** — Notify on entries and exits.
134. **Stop-hit / target-hit alerts** — Critical event notifications.
135. **Alert channel (Telegram/email/push)** — Reliable delivery path.
136. **Alert deduplication/throttling** — No spam.
137. **Alert acknowledgement** — Mark alerts handled.
138. **Missed-alert reconciliation** — Recover alerts after downtime.
139. **Daily EOD digest** — Summary of the session.
140. **Morning pre-open self-test** — Verify data/creds before open.
141. **Latency metrics** — Signal-to-notification timing.
142. **Uptime monitoring** — External ping of the service.
143. **Resource monitoring** — CPU/memory/disk.
144. **Deploy notification** — Announce new versions.
145. **Version display** — Show running build/commit.

## 9. Security & authentication (15)
146. **Login / auth on all surfaces** — Dashboard, API, websocket.
147. **Password hashing** — bcrypt/argon2, never plaintext.
148. **Session tokens with TTL** — Expiring, revocable sessions.
149. **Logout & revocation** — Kill sessions server-side.
150. **Login rate-limit / lockout** — Brute-force protection.
151. **2FA / TOTP** — Second factor on login.
152. **Secret management** — Encrypted/managed credentials, not plaintext.
153. **No hardcoded defaults** — No shipped default passwords.
154. **Security headers** — CSP, HSTS, nosniff, frame-deny.
155. **CORS restriction** — Allowlist origins only.
156. **CSRF protection** — On mutating endpoints.
157. **Audit log of logins** — Who/when/where.
158. **Alert on suspicious login** — New device/failed attempts.
159. **Role separation** — View-only vs trade-confirm.
160. **Chat-ID / source allowlist** — Only trusted command senders.

## 10. Configuration & deployment (15)
161. **Centralised config** — One place for all settings.
162. **Env-var / secrets loading** — Config from environment.
163. **Config validation at startup** — Fail early on bad values.
164. **Safe defaults** — Sensible fallbacks with override.
165. **Settings UI or command** — Change config without redeploy.
166. **Settings persistence** — Survive restarts.
167. **Feature flags** — Toggle features safely.
168. **Paper/live mode switch** — Explicit environment flag.
169. **Dependency pinning / lockfile** — Reproducible builds.
170. **CI pipeline** — Automated tests + build on push.
171. **Automated tests** — Unit + integration coverage.
172. **Smoke test** — Offline end-to-end sanity check.
173. **Graceful shutdown** — Clean stop, no orphaned state.
174. **Database migrations** — Versioned schema changes.
175. **Backup & restore** — Journal/state backup procedure.

## 11. Journaling, reporting & compliance (15)
176. **Trade journal** — Every idea/fill/exit persisted.
177. **Immutable audit trail** — Tamper-evident command history.
178. **Exit-reason capture** — Why each trade closed.
179. **PnL reporting** — Gross and net of costs.
180. **Per-strategy performance** — Attribution by strategy.
181. **Per-symbol stats** — History and outcomes per name.
182. **Win/loss & expectancy summary** — Headline performance.
183. **CSV/Excel export** — Portable trade history.
184. **Financial-year (Indian FY) report** — Tax-period PnL.
185. **Capital-gains STCG/LTCG split** — Holding-period classification.
186. **Charges breakdown** — Brokerage/STT/fees per trade.
187. **Regulatory disclaimer** — Risk/SEBI-context notice.
188. **Data-retention policy** — How long records are kept.
189. **Skipped/rejected-idea log** — What was passed on and why.
190. **Benchmark-relative reporting** — Performance vs NIFTY.

## 12. UX & dashboard (10)
191. **Live dashboard** — Positions, ideas, PnL at a glance.
192. **Order ticket UI** — Guided entry with validation.
193. **Charts with indicators** — Visual context for decisions.
194. **Confirmation dialogs** — On destructive/trade actions.
195. **Loading/empty/error states** — Clear UI feedback.
196. **Mobile-responsive layout** — Usable on phones.
197. **Real-time updates** — Websocket-driven refresh.
198. **Disconnect/stale banners** — Warn when data is unreliable.
199. **Watchlist management** — Add/remove/organise symbols.
200. **Toasts / notifications history** — Non-blocking feedback log.

---

### How to use this
Treat sections 1–6 as **non-negotiable core** for any bot that touches real money,
7 as essential before trusting a strategy, and 8–12 as what separates a hobby script
from something you'd run unattended. Cross-referenced against your repo, most of 1–7 exist;
the open gaps concentrate in 8–12 (see BACKLOG.md / MISSING-FEATURES.md).
