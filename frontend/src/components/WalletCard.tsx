import { useState } from "react";
import { api } from "../api";
import { rupees } from "../lang";
import { toast } from "../toast";
import type { Wallet } from "../types";

/** Groww-style balance card: total value big, cash/invested/PnL underneath,
 * add-money inline. One pool — the bot and you trade from the same wallet. */
export function WalletCard({ wallet, paper }: { wallet: Wallet; paper: boolean }) {
  const [adding, setAdding] = useState(false);
  const [amount, setAmount] = useState("");
  const [busy, setBusy] = useState(false);
  const up = wallet.open_pnl >= 0;

  const deposit = async () => {
    const v = Number(amount);
    if (!Number.isFinite(v) || v <= 0) {
      toast("warning", "Enter a positive amount.");
      return;
    }
    setBusy(true);
    try {
      const r = await api.walletDeposit(v);
      toast(r.ok ? "success" : "warning", r.reply);
      setAdding(false);
      setAmount("");
    } catch {
      toast("danger", "Couldn't add money — try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="wallet-card">
      <div className="wallet-top">
        <div>
          <span className="sum-label">{paper ? "Practice wallet" : "Trading wallet"}</span>
          <strong className="wallet-total">{rupees(wallet.current_value, 0)}</strong>
          <span className={`wallet-pnl ${up ? "good" : "critical"}`}>
            {up ? "▲" : "▼"} {rupees(Math.abs(wallet.open_pnl), 0)} open P&L
          </span>
        </div>
        <button className="btn-big btn-addmoney" onClick={() => setAdding((a) => !a)}>
          {adding ? "Close" : "+ Add money"}
        </button>
      </div>

      {adding && (
        <div className="wallet-add">
          <input
            type="number"
            inputMode="decimal"
            placeholder="Amount (₹)"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            aria-label="Amount to add"
          />
          <button className="btn-big btn-buy" disabled={busy} onClick={deposit}>
            {busy ? "Adding…" : "Add"}
          </button>
        </div>
      )}

      <div className="wallet-split">
        <div>
          <span className="sum-label">Cash free</span>
          <strong>{rupees(wallet.cash, 0)}</strong>
        </div>
        <div>
          <span className="sum-label">Invested</span>
          <strong>{rupees(wallet.invested, 0)}</strong>
        </div>
      </div>
    </div>
  );
}
