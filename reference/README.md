# Reference material (third-party, not part of the app)

Hand-picked source files preserved from four studied repos before the full
checkouts were deleted. **Nothing in this folder is imported by the app** —
these are the originals the following adaptations were based on, kept for
future reading:

| Folder | Upstream repo | License | What was adapted into the app |
|---|---|---|---|
| `quantdinger/` | QuantDinger | Apache-2.0 | Rule-based market-regime classifier → `indicators.market_regime`; post-backtest diagnostics thresholds → `BacktestResult._diagnostics`; also kept: regime-aware strategy scoring, live-vs-backtest deviation report, hybrid ATR+structural stops, DE optimizer, fee-aware trailing-stop guard |
| `intelligent-trading-bot/` | asavinov/intelligent-trading-bot | MIT | Kept for: relative/normalized feature convention, slope & area-ratio trend filters, band-hysteresis notification throttling, grid-search tuning harness (`simulate.py`) |
| `vibe-trading/` | HKUDS/Vibe-Trading | MIT | Monte-Carlo trade-reshuffle drawdown test → `backtest._monte_carlo_dd`; OHLC sanity gate → `backtest._clean_candles`; exit-reason attribution → `summary()["by_exit_reason"]`; also kept: bootstrap Sharpe CI, walk-forward analysis, benchmark/information-ratio metrics, correlation matrix, inverse-vol weighting, live halt-file kill switch + fail-closed order guard |
| `stocksharp/` | StockSharp | Apache-2.0 | Portfolio risk-rule pattern → `risk_manager.portfolio_allows`; statistics formulas (expectancy, profit factor, recovery factor, Calmar, Sortino, max-DD) → `backtest.summary()`; also kept: configurable fill-assumption emulator settings, protective stop with timeout exit (C# — pattern reference only) |

Other ideas adopted from the study but implemented from the published source
rather than these files: Indian transaction-cost model (`costs.py`, from
Zerodha/Groww published charges), Faber 200-DMA index gate
(`positional.index_allows_entries`, SSRN), evidence-ranked strategy cascade
(arXiv:2206.12282 and related backtest literature).

All four upstream licenses (Apache-2.0 / MIT) permit this copying with
attribution; each file retains its original header where one existed.
