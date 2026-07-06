import { useEffect, useRef, useState } from "react";
import {
  CandlestickSeries,
  ColorType,
  HistogramSeries,
  LineSeries,
  LineStyle,
  createChart,
  type CandlestickData,
  type IChartApi,
  type IPriceLine,
  type ISeriesApi,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";
import { api } from "../api";
import type { Idea, Snapshot } from "../types";

interface Props {
  symbol: string;
  snapshot: Snapshot;
  prices: Record<string, number>;
}

type Interval = "5m" | "1d";

const BUCKET_SECONDS = 5 * 60; // mirrors the backend's default BAR_MINUTES=5

function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || "#888";
}

function todayIST(): string {
  return new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" });
}

const OVERLAY_STYLE: Record<string, { color: () => string; title: string }> = {
  vwap: { color: () => cssVar("--warning"), title: "VWAP" },
  ema20: { color: () => cssVar("--series-blue"), title: "EMA 20" },
  ema50: { color: () => "#a26bf7", title: "EMA 50" },
};

/** TradingView-style live candlestick chart with volume, VWAP/EMA overlays and
 * the active idea's entry/stop/target levels drawn as price lines. */
export function ChartPanel({ symbol, snapshot, prices }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candlesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const overlayRefs = useRef<Record<string, ISeriesApi<"Line">>>({});
  const priceLinesRef = useRef<IPriceLine[]>([]);
  const lastCandleRef = useRef<CandlestickData | null>(null);

  const [interval, setInterval_] = useState<Interval>("5m");
  const [synthetic, setSynthetic] = useState(false);
  const [error, setError] = useState("");
  const [loaded, setLoaded] = useState(false);

  // ---- create the chart once ------------------------------------------------
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const chart = createChart(el, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: cssVar("--text-muted"),
        attributionLogo: false,
      },
      grid: {
        vertLines: { color: cssVar("--gridline") },
        horzLines: { color: cssVar("--gridline") },
      },
      rightPriceScale: { borderColor: cssVar("--baseline") },
      timeScale: { borderColor: cssVar("--baseline"), timeVisible: true, secondsVisible: false },
      crosshair: { horzLine: { labelBackgroundColor: cssVar("--baseline") }, vertLine: { labelBackgroundColor: cssVar("--baseline") } },
    });
    const candles = chart.addSeries(CandlestickSeries, {
      upColor: cssVar("--good"),
      downColor: cssVar("--critical"),
      borderVisible: false,
      wickUpColor: cssVar("--good"),
      wickDownColor: cssVar("--critical"),
    });
    const volume = chart.addSeries(HistogramSeries, {
      priceScaleId: "vol",
      priceFormat: { type: "volume" },
      lastValueVisible: false,
      priceLineVisible: false,
    });
    chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 }, visible: false });
    chartRef.current = chart;
    candlesRef.current = candles;
    volumeRef.current = volume;
    return () => {
      chart.remove();
      chartRef.current = null;
      candlesRef.current = null;
      volumeRef.current = null;
      overlayRefs.current = {};
      priceLinesRef.current = [];
      lastCandleRef.current = null;
    };
  }, []);

  // ---- load history on symbol / interval change ------------------------------
  useEffect(() => {
    let cancelled = false;
    setLoaded(false);
    setError("");
    lastCandleRef.current = null;
    api
      .chart(symbol, interval, interval === "5m" ? 5 : 365)
      .then((data) => {
        if (cancelled || !chartRef.current || !candlesRef.current || !volumeRef.current) return;
        setSynthetic(data.synthetic);
        const up = cssVar("--good"), down = cssVar("--critical");
        const candleData = data.candles.map((c) => ({
          time: c.time as Time, open: c.open, high: c.high, low: c.low, close: c.close,
        }));
        candlesRef.current.setData(candleData);
        volumeRef.current.setData(
          data.candles.map((c) => ({
            time: c.time as Time,
            value: c.volume,
            color: (c.close >= c.open ? up : down) + "55",
          })),
        );
        // overlays: drop stale series, then set the new ones
        for (const [key, series] of Object.entries(overlayRefs.current)) {
          chartRef.current.removeSeries(series);
          delete overlayRefs.current[key];
        }
        for (const [key, values] of Object.entries(data.overlays)) {
          const style = OVERLAY_STYLE[key];
          if (!style) continue;
          const series = chartRef.current.addSeries(LineSeries, {
            color: style.color(),
            lineWidth: 1,
            priceLineVisible: false,
            lastValueVisible: false,
            crosshairMarkerVisible: false,
          });
          series.setData(
            values
              .map((v, i) => (v == null ? null : { time: data.candles[i].time as Time, value: v }))
              .filter((p): p is { time: Time; value: number } => p !== null),
          );
          overlayRefs.current[key] = series;
        }
        lastCandleRef.current = candleData.length ? { ...candleData[candleData.length - 1] } : null;
        chartRef.current.timeScale().fitContent();
        setLoaded(true);
      })
      .catch((e) => !cancelled && setError(String(e)));
    return () => {
      cancelled = true;
    };
  }, [symbol, interval]);

  // ---- entry / stop / target price lines for this symbol's idea --------------
  const idea: Idea | undefined =
    snapshot.positions.find((i) => i.symbol === symbol) ?? snapshot.pending.find((i) => i.symbol === symbol);
  const levelsKey = idea ? `${idea.idea_id}:${idea.status}:${idea.stop}:${idea.target}` : "";
  useEffect(() => {
    const series = candlesRef.current;
    if (!series || !loaded) return;
    priceLinesRef.current.forEach((l) => series.removePriceLine(l));
    priceLinesRef.current = [];
    if (!idea) return;
    const mk = (price: number, color: string, title: string) =>
      series.createPriceLine({ price, color, lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title });
    priceLinesRef.current = [
      mk(idea.fill_price || idea.entry, cssVar("--series-blue"), idea.status === "ACTIVE" ? "avg" : "entry"),
      mk(idea.stop, cssVar("--critical"), "stop"),
      mk(idea.target, cssVar("--good"), "target"),
    ];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [levelsKey, loaded, symbol]);

  // ---- fold live ticks into the last candle ----------------------------------
  const ltp = prices[symbol];
  useEffect(() => {
    const series = candlesRef.current;
    const last = lastCandleRef.current;
    if (!series || !loaded || ltp == null || !last) return;
    let candle: CandlestickData;
    if (interval === "5m") {
      const bucket = (Math.floor(Date.now() / 1000 / BUCKET_SECONDS) * BUCKET_SECONDS) as UTCTimestamp;
      candle =
        typeof last.time === "number" && bucket > last.time
          ? { time: bucket as Time, open: ltp, high: ltp, low: ltp, close: ltp }
          : { ...last, high: Math.max(last.high, ltp), low: Math.min(last.low, ltp), close: ltp };
    } else {
      const today = todayIST();
      candle =
        last.time === today
          ? { ...last, high: Math.max(last.high, ltp), low: Math.min(last.low, ltp), close: ltp }
          : { time: today as Time, open: ltp, high: ltp, low: ltp, close: ltp };
    }
    lastCandleRef.current = candle;
    series.update(candle);
  }, [ltp, loaded, interval]);

  const quote = snapshot.quotes?.[symbol];
  const shownLtp = ltp ?? quote?.ltp ?? null;
  const chg =
    shownLtp != null && quote?.prev_close
      ? Math.round(((shownLtp - quote.prev_close) / quote.prev_close) * 10000) / 100
      : (quote?.change_pct ?? null);

  return (
    <div className="chart-panel">
      <div className="chart-head">
        <div className="chart-title">
          <span className="chart-symbol">{symbol}</span>
          {shownLtp != null && (
            <span className="chart-ltp tabular">₹{shownLtp.toLocaleString("en-IN", { minimumFractionDigits: 2 })}</span>
          )}
          {chg != null && (
            <span className={`chart-chg tabular ${chg >= 0 ? "good" : "critical"}`}>
              {chg >= 0 ? "+" : ""}
              {chg.toFixed(2)}%
            </span>
          )}
          {synthetic && <span className="mode-badge warning">SYNTHETIC</span>}
        </div>
        <div className="chart-controls">
          {(["5m", "1d"] as const).map((iv) => (
            <button
              key={iv}
              className={`btn btn-ghost interval-btn ${interval === iv ? "active" : ""}`}
              onClick={() => setInterval_(iv)}
            >
              {iv === "5m" ? "5m" : "1D"}
            </button>
          ))}
        </div>
      </div>
      <div className="chart-legend text-muted">
        {interval === "5m" ? (
          <>
            <span style={{ color: cssVar("--warning") }}>— VWAP</span>
            <span style={{ color: cssVar("--series-blue") }}>— EMA 20</span>
          </>
        ) : (
          <>
            <span style={{ color: cssVar("--series-blue") }}>— EMA 20</span>
            <span style={{ color: "#a26bf7" }}>— EMA 50</span>
          </>
        )}
        {idea && <span>· levels: entry / stop / target</span>}
      </div>
      <div className="chart-container" ref={containerRef}>
        {error && <p className="chart-error text-muted">Chart unavailable — {error}</p>}
      </div>
    </div>
  );
}
