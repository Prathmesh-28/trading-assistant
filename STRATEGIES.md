# Strategy & Backtesting Catalog — what's missing

Companion to [ROADMAP.md](ROADMAP.md) (product features). This is the trading
brain: every meaningful **algorithmic strategy** and **backtesting/validation
method** the tool doesn't have yet.

Tags on every entry:
- Evidence: **[strong]** published/replicated results · **[mixed]** works in some tests/regimes · **[weak]** anecdotal, popular but unproven
- Fit: **[ready]** implementable now with Groww cash-equity daily/5-min data · **[needs-feed]** needs new data (options OI, news, index futures, constituents history) · **[needs-fo]** needs an F&O account / shorting

## What you already have (for contrast)

Intraday: ORB+VWAP+Supertrend (SSRN 4729284), squeeze-release secondary.
Positional cascade: EMA20/50 cross (+EMA200/ADX/RSI filters), Donchian-55,
RSI dip-buy in uptrend, Golden Cross, MACD cross — gated by a deterministic
regime classifier and a Faber 200-DMA index gate. Backtester: bar-by-bar
production-code replay, no lookahead, stop-wins-on-ambiguous-bar, next-bar-open
fills, net Indian costs, Monte-Carlo trade-reshuffle, exit attribution,
buy-&-hold benchmark, rule-based diagnostics.

---

## 1. Intraday strategies missing (cash market)

1. **Gap-and-Go** — gap up >2% on RVOL>2, buy break of first 5-min high; the ORB paper's companion setup [strong] [ready]
2. **Gap-fill fade** — gap >3% *into* yesterday's range with weak first bar → fade toward gap fill [mixed] [ready]
3. **VWAP mean-reversion** — in `range` regime, fade 2σ deviations from VWAP back to VWAP [mixed] [ready]
4. **VWAP pullback continuation** — after a confirmed ORB, buy the first successful VWAP retest [mixed] [ready]
5. **Failed-ORB reversal** — breakout bar closes back inside the range → trade the opposite direction (trap reversal) [mixed] [ready]
6. **60-min opening range** — same logic, wider range; fewer, cleaner signals; backtest against the 5-min variant [strong] [ready]
7. **Previous-day-high/low break** — classic continuation levels with volume confirmation [mixed] [ready]
8. **Pivot-point plays** — R4/S4 Camarilla breakouts and R3/S3 fades [weak] [ready]
9. **NR7 / inside-day next-open breakout** — volatility contraction begets expansion [mixed] [ready]
10. **High-of-day momentum scalp** — new HOD after 11:00 with RVOL>3 [weak] [ready]
11. **Late-day trend continuation** — 14:30 entry in the day's dominant direction, exit at close (documented time-of-day drift) [mixed] [ready]
12. **Short-side ORB** — breakdown mirror (code exists behind ALLOW_SHORTS; never backtested) [strong] [ready]
13. **Anchored-VWAP reclaim** — anchor at gap/open; reclaim after undercut = entry [weak] [ready]
14. **Liquidity-sweep reversal** — wick through prior low + full-bar reclaim (stop-run pattern) [weak] [ready]
15. **Index lead-lag** — NIFTY futures thrust leads large-cap cash basket by minutes [mixed] [needs-feed]
16. **Sector sympathy** — sector leader gaps/breaks out → trade the strongest laggard [weak] [ready]
17. **Time-of-day seasonality filter** — suppress signals in the 12:00–13:30 lull (improves every intraday strategy above) [mixed] [ready]
18. **Circuit-approach momentum** — names heading into upper circuit with expanding volume (entry only if exit-liquidity rules pass) [weak] [ready]

## 2. Swing / positional — trend & momentum

19. **52-week-high breakout** — one of the best-documented momentum anomalies [strong] [ready]
20. **Cross-sectional momentum rotation** — rank NIFTY200 by 12-1-month return, hold top 10, monthly rebalance; the single most replicated equity anomaly [strong] [ready]
21. **Dual momentum (Antonacci)** — absolute + relative momentum switch between equity/gold/liquid ETFs [strong] [ready]
22. **Weekly Donchian (20-week)** — Turtle System 1 on weekly bars for multi-month holds [strong] [ready]
23. **Post-earnings-announcement drift (PEAD)** — buy strong beats, hold 1–3 weeks; robust anomaly [strong] [needs-feed]
24. **ADX pullback ("Holy Grail")** — ADX>30 uptrend, buy pullback to EMA20 [mixed] [ready]
25. **Volatility-contraction pattern (Minervini VCP)** — tightening pullback sequence + volume dry-up, buy pivot break [mixed] [ready]
26. **Flat-base / cup-with-handle breakout** (O'Neil) — needs pattern-detection code [mixed] [ready]
27. **Stage-2 breakout (Weinstein)** — 30-week MA turning up + price breakout on volume [mixed] [ready]
28. **MA-ribbon alignment** — 8>21>50>200 stack as trend filter/entry [weak] [ready]
29. **Elder triple screen** — weekly trend + daily oscillator pullback + intraday trigger [mixed] [ready]
30. **Momentum burst (3-5 day thrust)** — +8% in 3 days from a base, small position, quick exit [weak] [ready]
31. **High-tight-flag** — 100% run then <25% pullback flag; rare but historically powerful [mixed] [ready]
32. **Darvas box** — trailing box breakouts [weak] [ready]
33. **Ichimoku cloud break + Kijun trail** [weak] [ready]
34. **Heikin-Ashi trend continuation** — HA color-run persistence [weak] [ready]
35. **Linear-regression channel breakout** — you already have `linreg_endpoint`; unused for entries [weak] [ready]
36. **Relative-strength new-leader entry** — stocks making 52w highs within days of an index correction low [mixed] [ready]
37. **IPO base breakout** — first consolidation break of recent listings [mixed] [ready]
38. **Pocket pivot** (Kacher/Morales) — up-day volume > any down-day volume in prior 10 days, within a base [weak] [ready]

## 3. Mean-reversion (the missing counterweight — everything current is trend-following)

39. **RSI(2) < 10 above 200-DMA** (Connors) — buy next open, exit on RSI>70 or 5 days; among the best-tested US equity MR rules; validate on NSE [strong] [ready]
40. **Double-7s** (Connors) — 7-day low above 200-DMA, exit at 7-day high [mixed] [ready]
41. **3-consecutive-down-days in uptrend** — simple, robust pullback buy [mixed] [ready]
42. **Bollinger %B < 0 snapback** — close below lower band above 200-DMA, exit at mid-band [mixed] [ready]
43. **Extreme deviation-from-MA** — >10% below 50-DMA in a structural uptrend, staged entry [mixed] [ready]
44. **Quality-large-cap panic-gap buy** — gap down >4% on no fundamental news in a NIFTY50 name [mixed] [needs-feed]
45. **Overnight edge** — buy at close, sell at open (documented US overnight premium; needs NSE validation before use) [mixed] [ready]
46. **Turn-of-month effect** — long index T-3 through T+2 of month end [mixed] [ready]
47. **Leader-dip accumulation** — top-decile RS stock's first touch of 50-DMA [mixed] [ready]

## 4. Volatility-based

48. **Daily-timeframe squeeze breakout** — your squeeze code runs only intraday; the daily version is the standard use [mixed] [ready]
49. **ATR-percentile expansion filter** — only take breakouts when ATR% is rising from a low percentile (compression→expansion) [mixed] [ready]
50. **India VIX spike contrarian** — staged index-ETF buying when VIX > 90th percentile (evidence says VIX spikes cluster at bottoms — use as BUY context, never as a sell trigger) [mixed] [needs-feed]
51. **Volatility targeting overlay** — scale all position sizes to hit constant portfolio vol (well-evidenced smoother) [strong] [ready]
52. **Low-volatility anomaly tilt** — overweight boring low-vol names for the core book [strong] [ready]

## 5. Event-driven

53. **Earnings momentum** — beat+guidance-raise continuation [strong] [needs-feed]
54. **Index inclusion/exclusion** — buy announced inclusions before effective date [mixed] [needs-feed]
55. **Buyback announcement drift** [mixed] [needs-feed]
56. **Bulk/block-deal follow** — enter alongside disclosed institutional buys [weak] [needs-feed]
57. **Promoter-buying signal** — insider accumulation disclosures [mixed] [needs-feed]
58. **Split/bonus announcement effect** [weak] [needs-feed]
59. **Policy-day playbook** — RBI/budget-day reduced size + post-event trend entry [weak] [ready]

## 6. Pairs & statistical arbitrage

60. **Sector pairs** — cointegrated pairs (e.g., two private banks), z-score >2 entry, mean exit; long-only leg possible but true pairs [needs-fo] [strong evidence historically, decayed in liquid markets]
61. **ETF-vs-basket arbitrage** — NIFTYBEES vs constituent basket divergence [mixed] [needs-fo]
62. **Cash-futures basis** — extreme basis as sentiment/carry signal [mixed] [needs-feed]
63. **Holding-company discount trades** — discount extremes vs history [weak] [ready]

## 7. Options strategies (require F&O activation — different risk universe entirely)

64. **Covered calls on CNC holdings** — yield on positional winners [strong] [needs-fo]
65. **Cash-secured puts** — get paid to enter names your scanner likes at lower prices [strong] [needs-fo]
66. **Protective puts pre-event** — hedge instead of selling winners before earnings [strong] [needs-fo]
67. **Index credit spreads** — defined-risk premium selling in low-vol regimes [mixed] [needs-fo]
68. **Iron condors on range regimes** — your regime classifier already detects the right conditions [mixed] [needs-fo]
69. **Pre-event long straddles** — buy vol before binary events when IV underprices [mixed] [needs-fo]
70. **PCR / OI-change signals** — options positioning as a reversal/confirmation input to equity signals [weak] [needs-feed]
71. **Max-pain expiry reversion** [weak] [needs-feed]

## 8. Portfolio-construction strategies

72. **Core-satellite** — index ETF core + your signals as satellite (caps strategy risk structurally) [strong] [ready]
73. **Faber GTAA** — 200-DMA timing across equity/gold/bond ETFs (you have the gate; apply it per-asset) [strong] [ready]
74. **Equal-weight rebalancing premium** — periodic rebalance of a quality basket [mixed] [ready]
75. **Risk-parity mini** — inverse-vol weights across 3-4 asset ETFs (code preserved in reference/vibe-trading) [mixed] [ready]
76. **Kelly-fraction strategy allocation** — allocate capital across your 5+ strategies by their journal-measured edge [mixed] [ready]
77. **Seasonal tilts** — Nov–Apr overweight etc.; evidence weak for India, test before believing [weak] [ready]

---

## 9. Backtesting methodologies missing

### Validation & anti-overfitting (the ones that keep you honest)

78. **Walk-forward optimization** — tune on window N, test on N+1, roll; the standard anti-overfit protocol [strong] (skeleton exists in reference/vibe-trading)
79. **Out-of-sample lockbox** — auto-reserve the latest 6 months; parameters may NEVER touch it
80. **Parameter-plateau analysis** — heatmap the neighborhood; accept only parameters whose neighbors also profit (cliff-edge optimum = overfit)
81. **Deflated Sharpe ratio** — corrects for how many parameter combos you tried (Bailey/López de Prado)
82. **Probability of Backtest Overfitting (PBO/CSCV)** — combinatorially split data, measure rank stability
83. **Monte Carlo permutation test (MCPT)** — does your ENTRY beat random entries using the same exit logic? Isolates where the edge actually lives
84. **Block bootstrap of returns** — confidence intervals on Sharpe/CAGR preserving autocorrelation
85. **White's Reality Check / Hansen SPA** — multiple-strategy selection bias correction when picking the "best" of your cascade
86. **Regime-segmented reporting** — every metric split by bull/bear/range/high-vol (your classifier already labels days)
87. **Multi-symbol robustness sweep** — a rule that only works on 3 of 50 liquid names is curve-fit; run every strategy across NIFTY100
88. **Look-ahead audit harness** — automated test: shift all signals +1 bar; if results IMPROVE, you have leakage somewhere
89. **Trade-clustering analysis** — flag when all profit comes from one month/regime cluster
90. **Live-vs-backtest divergence tracking** — paper-trade forward and continuously compare to backtest expectation (deviation report code preserved in reference/quantdinger)

### Fill & cost realism

91. **Fill-assumption stress grid** — pessimistic/optimistic/mid same-bar ordering as a config knob; report the spread between them (pattern from StockSharp's MarketEmulatorSettings)
92. **Intra-bar path inference option** — bullish bar → O-L-H-C ordering (QuantDinger pattern) as an alternative to always-stop-wins
93. **1-minute exit simulation** — run entries on 5-min but exits on 1-min data; slashes the ambiguous-bar rate
94. **Spread-based slippage model** — slippage as f(bid-ask, order size) instead of flat %
95. **Volume-participation cap** — refuse fills >2% of bar volume (your qty vs reality)
96. **Square-root market-impact model** — for when capital grows
97. **Execution-lag sweep** — simulate 0s/30s/2min/5min delay between alert and your manual fill; quantifies the recommend-mode tax
98. **Partial-fill modeling** — thin names may not fill full qty at the level
99. **Circuit-day exit modeling** — you skip locked bars; also model the NEXT day's forced exit price
100. **Costs-model true-up** — reconcile modeled costs vs actual Groww contract notes monthly

### Data hygiene

101. **Point-in-time index constituents** — survivorship-bias-free universes (research measured ~4.9pp/yr inflation on NSE small caps)
102. **Delisting/suspension handling** — positions in halted names must resolve realistically
103. **Corporate-action adjustment verification** — splits/bonuses silently corrupt raw candle history and every ATR/stop computed from it
104. **Holiday/half-day calendar** — Muhurat sessions and half-days break "bars per day" assumptions
105. **Data-revision detection** — exchanges occasionally republish candles; hash and diff your cache

### Exit & sizing optimization (directly serves "when to sell")

106. **MAE-based stop optimization** — distribution of max adverse excursion of WINNING trades tells you the widest stop that keeps winners
107. **MFE-based target optimization** — how much favorable excursion do trades give before reverting; sets evidence-based targets
108. **Edge-decay-by-holding-period curve** — expectancy vs days held; tells the time stop empirically
109. **Trailing-stop parameter sweep** — Chandelier 2.5/3.0/3.5×ATR, 14/22-day, vs swing-low trailing, vs no trail
110. **Partial-exit backtests** — half-at-1R vs all-at-2R vs trail-everything, on YOUR strategies
111. **Kelly / optimal-f sizing backtest** — growth-optimal vs fixed-fractional, with drawdown overlay
112. **Portfolio-level concurrent simulation** — all strategies together under the real heat caps and correlations (current backtests are per-symbol sequential)
113. **Re-entry rules testing** — after a stop-out, when is re-entry +EV vs revenge trading
114. **Stop-placement A/B: structural vs volatility** — swing-low stops vs ATR stops, measured, not argued

---

### The five to build first

By evidence × fit × effort, in order:

1. **RSI(2) mean-reversion** (#39) — best-evidenced missing strategy, trivially implementable, diversifies your all-trend book
2. **Cross-sectional momentum rotation** (#20) — the most replicated anomaly in equities; monthly cadence suits manual execution perfectly
3. **Walk-forward + parameter-plateau + lockbox** (#78-80) — before adding ANY more strategies, make the validation honest or the catalog above just manufactures overfit
4. **MAE/MFE exit optimization** (#106-108) — directly answers "when to sell" with your own trade data instead of folklore multipliers
5. **Gap-and-Go** (#1) — highest-evidence intraday addition, shares 90% of its plumbing with the existing ORB code
