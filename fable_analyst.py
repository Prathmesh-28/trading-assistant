"""Claude Fable 5 sits BESIDE the rule engine, never inside it.

It writes a MarketContext (regime / bias / symbols to avoid) that the
deterministic strategies read as a filter, and it adds a one-line "why" to each
idea. If the API is slow, down, or unauthenticated the engine keeps working on
neutral defaults — every method here fails soft.

Fable 5 API notes (see claude-api skill):
  - thinking is always on; do NOT send a `thinking` param
  - no temperature/top_p/top_k
  - safety classifiers can return stop_reason "refusal"; we opt into
    server-side fallbacks so a benign-finance false positive is transparently
    re-served by claude-opus-4-8 inside the same call
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

import anthropic

from config import IST, Settings
from recommendation import Recommendation
from strategy import MarketContext

log = logging.getLogger("fable")

_CONTEXT_SCHEMA = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "properties": {
            "regime": {"type": "string", "enum": ["trending", "choppy", "volatile", "unknown"]},
            "bias": {"type": "string", "enum": ["long", "short", "neutral"]},
            "confidence": {"type": "string", "enum": ["LOW", "MEDIUM", "HIGH"]},
            "avoid_symbols": {"type": "array", "items": {"type": "string"}},
            "notes": {"type": "string"},
        },
        "required": ["regime", "bias", "confidence", "avoid_symbols", "notes"],
        "additionalProperties": False,
    },
}

_SYSTEM = (
    "You are the market-context analyst inside a personal NSE-equity signal tool. "
    "A deterministic rule engine makes all entry/exit calls; you only classify the "
    "current session (regime, directional bias, symbols to avoid on news risk) and "
    "explain ideas in one line. You never place orders and never invent prices. "
    "Be conservative: when unsure, say regime=unknown and bias=neutral."
)


class FableAnalyst:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._disabled = not settings.fable_enabled
        # Zero-arg client resolves ANTHROPIC_API_KEY / AUTH_TOKEN / `ant auth login`
        self._client = anthropic.AsyncAnthropic(timeout=60.0, max_retries=2)

    @property
    def available(self) -> bool:
        return not self._disabled

    async def _create(self, **kwargs):
        return await self._client.beta.messages.create(
            model=self._settings.fable_model,
            betas=["server-side-fallback-2026-06-01"],
            fallbacks=[{"model": self._settings.fable_fallback_model}],
            **kwargs,
        )

    @staticmethod
    def _is_auth_failure(e: Exception) -> bool:
        """The SDK raises AuthenticationError for a BAD key but a plain
        TypeError('Could not resolve authentication method…') for a MISSING
        one — both mean the same thing here: turn the layer off."""
        return isinstance(e, anthropic.AuthenticationError) or (
            isinstance(e, TypeError) and "authentication" in str(e).lower()
        )

    @staticmethod
    def _text(response) -> str:
        if response.stop_reason == "refusal":
            return ""
        return next((b.text for b in response.content if b.type == "text"), "")

    async def market_context(
        self, watchlist: list[str], snapshot: dict[str, float], previous: MarketContext | None
    ) -> MarketContext | None:
        """Pre-market plan / ~15-min refresh. Returns None on any failure so the
        caller keeps the previous (or neutral) context."""
        if self._disabled:
            return None
        now = datetime.now(IST)
        prev = ""
        if previous and previous.regime != "unknown":
            prev = (
                f"Your previous read: regime={previous.regime}, bias={previous.bias}, "
                f"notes={previous.notes!r}. Update it only if the tape changed."
            )
        prices = ", ".join(f"{s}={p:,.1f}" for s, p in snapshot.items()) or "no live prices yet"
        prompt = (
            f"Time: {now:%A %d %b %Y %H:%M} IST (NSE cash session 09:15-15:30).\n"
            f"Watchlist: {', '.join(watchlist)}.\n"
            f"Latest prices: {prices}.\n{prev}\n"
            "Classify the current session for an intraday breakout + positional trend "
            "system. avoid_symbols = watchlist names with obvious event/news risk you "
            "are confident about (earnings day, regulatory action); leave empty if unsure. "
            "notes = one sentence a trader reads on the phone."
        )
        try:
            resp = await self._create(
                max_tokens=1000,
                output_config={"effort": "low", "format": _CONTEXT_SCHEMA},
                system=_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = self._text(resp)
            if not raw:
                return None
            data = json.loads(raw)
            return MarketContext(
                regime=data["regime"],
                bias=data["bias"],
                confidence=data["confidence"],
                avoid_symbols={s.strip().upper() for s in data["avoid_symbols"]},
                notes=data["notes"][:200],
                updated_at=now,
            )
        except Exception as e:  # noqa: BLE001 — this layer's contract is fail-soft, always
            log.warning("market_context failed (engine continues on defaults): %s", e)
            if self._is_auth_failure(e):
                log.warning("Anthropic auth missing — Fable layer disabled for this run")
                self._disabled = True
            return None

    async def why_line(self, rec: Recommendation, ctx: MarketContext) -> str:
        """One phone-friendly line explaining the idea. '' on failure."""
        if self._disabled:
            return ""
        prompt = (
            f"Rule engine idea: {rec.side.value} {rec.symbol} ({rec.horizon.value}), "
            f"entry {rec.entry}, stop {rec.stop}, target {rec.target}. "
            f"Trigger: {rec.reason}. Session context: regime={ctx.regime}, bias={ctx.bias}. "
            "Write ONE line (max 15 words) telling the trader why this setup makes sense "
            "right now. No preamble, no emoji, no disclaimers."
        )
        try:
            resp = await self._create(
                max_tokens=200,
                output_config={"effort": "low"},
                system=_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
            )
            text = self._text(resp).strip()
            return text.splitlines()[0][:160] if text else ""
        except Exception as e:  # noqa: BLE001 — fail-soft, the idea must still go out
            log.warning("why_line failed: %s", e)
            if self._is_auth_failure(e):
                self._disabled = True
            return ""

    async def close(self) -> None:
        await self._client.close()
