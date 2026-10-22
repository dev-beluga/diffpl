"""Pitch cards: layout by position, captain points, and escaped names."""

from diffpl.ui.pitch import CLUB_COLOURS, Card, card_html, pitch_html, shirt_svg


def card(i: int, pos: str = "MID", **kw: object) -> Card:
    base: dict[str, object] = {
        "element_id": i,
        "name": f"P{i}",
        "team": "ARS",
        "position": pos,
        "xp": 4.0,
        "fixture": "NEW (H)",
        "price_tenths": 65,
    }
    return Card(**{**base, **kw})  # type: ignore[arg-type]


def test_captain_shows_doubled_points_and_badge() -> None:
    html = card_html(card(1, captain=True))
    assert "8.0" in html and 'class="badge cap"' in html


def test_names_and_fixtures_are_escaped() -> None:
    html = card_html(card(1, name="<script>x</script>", fixture="<b>"))
    assert "<script>" not in html and "&lt;script&gt;" in html and "<b>" not in html


def test_blank_gw_says_no_match() -> None:
    assert "No match" in card_html(card(1, fixture=""))


def test_rows_follow_position_order_and_bench_is_separate() -> None:
    starters = [card(1, "GKP"), card(2, "DEF"), card(3, "MID"), card(4, "FWD")]
    html = pitch_html(starters, [card(5, "GKP", name="Sub")])
    pitch, bench = html.split('class="bench"')
    assert pitch.index("P1") < pitch.index("P2") < pitch.index("P3") < pitch.index("P4")
    assert "Sub" in bench and "Sub" not in pitch


def test_every_club_and_unknown_clubs_get_a_shirt() -> None:
    for team in [*CLUB_COLOURS, "XYZ"]:
        assert shirt_svg(team, goalkeeper=False).startswith("<svg")
    assert "url(#s-NEW-0)" in shirt_svg("NEW", goalkeeper=False)  # striped kit
