"""Builds the Telegram message text (HTML) for one post.

Layout, made for reading on a phone:

    🐦 @user
    📝 Summary of the post

    🟢 QQQ 512.30 (+0.40%) · Bullish
    One-line reason
    Prev day 505.10–514.20 · 20d 498.00–520.00 · 50d 505.00

    🏷 $NVDA 🟢 note
    💬 "original post…"
    🔗 Open on X

Every part is optional: if the AI or IBKR is down, the message still
goes out with whatever is available.
"""

from __future__ import annotations

import html

from notifier.analysis import Analysis
from notifier.market_data import Levels
from notifier.x_client import Tweet

BIAS_ICONS = {"bullish": "🟢", "bearish": "🔴", "neutral": "⚪"}
MAX_ORIGINAL_CHARS = 1200     # keeps every message well under Telegram's 4096 limit
MAX_ORIGINAL_WITH_AI = 400    # shorter quote when a summary is shown


def _esc(text: str) -> str:
    return html.escape(text, quote=False)


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _levels_line(lv: Levels) -> str:
    parts = [
        f"Prev day {lv.prev_low:.2f}–{lv.prev_high:.2f}",
        f"20d {lv.low_20d:.2f}–{lv.high_20d:.2f}",
    ]
    if lv.sma_50 is not None:
        parts.append(f"50d {lv.sma_50:.2f}")
    if lv.sma_200 is not None:
        parts.append(f"200d {lv.sma_200:.2f}")
    return " · ".join(parts)


def _price(lv: Levels | None) -> str:
    return f" {lv.last:.2f} ({lv.change_pct:+.2f}%)" if lv else ""


def _market_section(analysis: Analysis, levels: dict[str, Levels]) -> list[str]:
    if not analysis.market_relevant:
        return ["⚪ <i>No clear market impact</i>"]
    lines: list[str] = []
    for view in analysis.market:
        lv = levels.get(view.symbol)
        lines.append(
            f"{BIAS_ICONS[view.bias]} <b>{_esc(view.symbol)}</b>{_price(lv)} · {view.bias.capitalize()}"
        )
        if view.reason:
            lines.append(_esc(view.reason))
        if lv:
            lines.append(f"<i>{_levels_line(lv)}</i>")
        lines.append("")
    return lines[:-1] if lines else lines


def format_message(
    tweet: Tweet,
    analysis: Analysis | None = None,
    levels: dict[str, Levels] | None = None,
    notes: list[str] | None = None,
) -> str:
    levels = levels or {}
    lines = [f"🐦 <b>@{_esc(tweet.username)}</b>"]

    if analysis:
        lines += [f"📝 {_esc(analysis.summary)}", ""]
        lines += _market_section(analysis, levels)
        if analysis.tickers:
            lines.append("")
            lines += [
                f"🏷 <b>${_esc(t.symbol)}</b> {BIAS_ICONS[t.bias]} {_esc(t.note)}".rstrip()
                for t in analysis.tickers
            ]
        lines += ["", f"💬 <i>{_esc(_truncate(tweet.text, MAX_ORIGINAL_WITH_AI))}</i>"]
    else:
        lines += ["", _esc(_truncate(tweet.text, MAX_ORIGINAL_CHARS))]
        if levels:
            lines.append("")
            lines += [f"📊 <b>{_esc(s)}</b>{_price(lv)}" for s, lv in levels.items()]

    for note in notes or []:
        lines.append(f"⚠️ <i>{_esc(note)}</i>")

    lines.append(f'🔗 <a href="{tweet.url}">Open on X</a>')
    return "\n".join(lines)
