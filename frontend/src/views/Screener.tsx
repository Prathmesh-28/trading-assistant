import { ScreenerPanel } from "../components/ScreenerPanel";

/** Top-level screener tab — find stocks by rules (quality, value, momentum,
 * promoter holding…), tap a match to open its full stock page. */
export function Screener({ onOpen }: { onOpen?: (s: string) => void }) {
  return (
    <div className="screener-view">
      <header className="view-head">
        <h1>Find stocks</h1>
        <p>Pick a lens — the engine scans real fundamentals and ranks what passes.</p>
      </header>
      <ScreenerPanel onOpen={onOpen} />
    </div>
  );
}
