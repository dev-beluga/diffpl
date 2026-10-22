"""Player cards on a pitch, as HTML for the dashboard.

Pure functions from card data to an HTML string, so layout is testable without Streamlit.
Shirts are drawn as SVG in club colours; no club or FPL artwork is used. Player and club
names come from the FPL API and are escaped before they reach the page.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape

from diffpl.rules import Position

# (body, sleeves or second stripe, stripes). Approximate home colours, 2026-27 clubs.
CLUB_COLOURS: dict[str, tuple[str, str, bool]] = {
    "ARS": ("#EF0107", "#FFFFFF", False),
    "AVL": ("#670E36", "#95BFE5", False),
    "BOU": ("#DA291C", "#111111", True),
    "BRE": ("#E30613", "#FFFFFF", True),
    "BHA": ("#0057B8", "#FFFFFF", True),
    "CHE": ("#034694", "#034694", False),
    "COV": ("#59CBE8", "#FFFFFF", False),
    "CRY": ("#1B458F", "#C4122E", True),
    "EVE": ("#003399", "#003399", False),
    "FUL": ("#FFFFFF", "#111111", False),
    "HUL": ("#F5A12D", "#111111", True),
    "IPS": ("#3A64A3", "#FFFFFF", False),
    "LEE": ("#FFFFFF", "#1D428A", False),
    "LIV": ("#C8102E", "#C8102E", False),
    "MCI": ("#6CABDD", "#6CABDD", False),
    "MUN": ("#DA291C", "#DA291C", False),
    "NEW": ("#241F20", "#FFFFFF", True),
    "NFO": ("#DD0000", "#FFFFFF", False),
    "TOT": ("#FFFFFF", "#132257", False),
    "SUN": ("#EB172B", "#FFFFFF", True),
}
GK_COLOURS = ("#F2C300", "#1E1E1E", False)
UNKNOWN_COLOURS = ("#9AA5B1", "#6B7785", False)
ROWS: tuple[Position, ...] = ("GKP", "DEF", "MID", "FWD")


@dataclass(frozen=True)
class Card:
    element_id: int
    name: str
    team: str  # club short name, e.g. "ARS"
    position: Position
    xp: float  # expected points this GW, before the captain multiplier
    fixture: str  # e.g. "NEW (H)", "ARS (A), LIV (H)", or "" for a blank GW
    price_tenths: int
    captain: bool = False
    vice: bool = False
    new: bool = False  # transferred in by this plan


def shirt_svg(team: str, goalkeeper: bool) -> str:
    body, second, stripes = GK_COLOURS if goalkeeper else CLUB_COLOURS.get(team, UNKNOWN_COLOURS)
    pid = f"s-{escape(team)}-{int(goalkeeper)}"
    fill = f"url(#{pid})" if stripes else body
    pattern = (
        f'<defs><pattern id="{pid}" width="12" height="10" patternUnits="userSpaceOnUse">'
        f'<rect width="6" height="10" fill="{body}"/><rect x="6" width="6" height="10" '
        f'fill="{second}"/></pattern></defs>'
        if stripes
        else ""
    )
    sleeves = body if stripes else second
    return (
        f'<svg class="shirt" viewBox="0 0 60 56" aria-hidden="true">{pattern}'
        f'<path d="M14 6 L2 16 L8 26 L14 22 Z" fill="{sleeves}" stroke="#0003"/>'
        f'<path d="M46 6 L58 16 L52 26 L46 22 Z" fill="{sleeves}" stroke="#0003"/>'
        f'<path d="M14 6 L23 3 Q30 9 37 3 L46 6 L46 54 L14 54 Z" fill="{fill}" '
        f'stroke="#0003"/>'
        f'<path d="M23 3 Q30 9 37 3" fill="none" stroke="#0004" stroke-width="2"/></svg>'
    )


def card_html(c: Card) -> str:
    badge = ""
    if c.captain:
        badge = '<span class="badge cap" title="Captain">C</span>'
    elif c.vice:
        badge = '<span class="badge vice" title="Vice-captain">V</span>'
    new = '<span class="badge new" title="Transferred in">IN</span>' if c.new else ""
    shown = c.xp * (2 if c.captain else 1)
    fixture = escape(c.fixture) if c.fixture else "No match"
    return (
        f'<div class="card{" is-new" if c.new else ""}" '
        f'title="{escape(c.name)} · {c.team} · £{c.price_tenths / 10:.1f}m">'
        f"{badge}{new}{shirt_svg(c.team, c.position == 'GKP')}"
        f'<div class="name">{escape(c.name)}</div>'
        f'<div class="fixture">{fixture}</div>'
        f'<div class="xp">{shown:.1f} <span>xP</span></div></div>'
    )


def pitch_html(starters: list[Card], bench: list[Card]) -> str:
    rows = "".join(
        f'<div class="row">{"".join(card_html(c) for c in starters if c.position == pos)}</div>'
        for pos in ROWS
    )
    subs = "".join(card_html(c) for c in bench)
    return (
        f"<style>{CSS}</style>"
        f'<div class="pitch"><div class="lines"></div>{rows}</div>'
        f'<div class="bench"><div class="bench-label">Bench</div>'
        f'<div class="row">{subs}</div></div>'
    )


CSS = """
.pitch { position: relative; padding: 18px 8px 10px; border-radius: 14px;
  background: repeating-linear-gradient(180deg, #1f8a4c 0 44px, #23964f 44px 88px);
  box-shadow: inset 0 0 0 2px #ffffff2e; overflow: hidden; }
.pitch .lines { position: absolute; inset: 10px; border: 2px solid #ffffff40;
  border-radius: 6px; pointer-events: none; }
.pitch .lines::before { content: ""; position: absolute; left: 30%; right: 30%; top: -2px;
  height: 14%; border: 2px solid #ffffff40; border-top: none; }
.row { position: relative; display: flex; justify-content: center; gap: 10px;
  margin: 10px 0; flex-wrap: nowrap; }
.card { position: relative; width: 84px; text-align: center; font-family: inherit; }
.card .shirt { width: 54px; height: 50px; display: block; margin: 0 auto 2px;
  filter: drop-shadow(0 2px 2px #0005); }
.card .name { background: #10273b; color: #fff; font-size: 12px; font-weight: 600;
  padding: 3px 4px; border-radius: 6px 6px 0 0; white-space: nowrap; overflow: hidden;
  text-overflow: ellipsis; }
.card .fixture { background: #f1f4f7; color: #10273b; font-size: 11px; padding: 2px 4px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.card .xp { background: #00c26f; color: #062b18; font-size: 12px; font-weight: 700;
  padding: 2px 4px; border-radius: 0 0 6px 6px; }
.card .xp span { font-weight: 500; font-size: 10px; }
.card.is-new .name { background: #0b6e4f; }
.badge { position: absolute; top: 0; right: 10px; width: 20px; height: 20px;
  border-radius: 50%; font-size: 11px; font-weight: 800; line-height: 20px; z-index: 1;
  box-shadow: 0 1px 3px #0006; }
.badge.cap { background: #111; color: #fff; }
.badge.vice { background: #fff; color: #111; }
.badge.new { left: 8px; right: auto; width: auto; padding: 0 5px; border-radius: 10px;
  background: #00c26f; color: #062b18; font-size: 9px; }
.bench { margin-top: 10px; padding: 8px; border-radius: 14px; background: #e8eef3; }
.bench-label { font-size: 12px; font-weight: 700; color: #10273b; margin-left: 6px; }
@media (max-width: 640px) {
  .row { gap: 4px; }
  .card { width: 62px; }
  .card .shirt { width: 40px; height: 37px; }
  .card .name { font-size: 10px; }
  .card .fixture, .card .xp { font-size: 9px; }
}
"""
