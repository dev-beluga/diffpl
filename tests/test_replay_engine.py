import pytest

from diffpl.replay.engine import (
    InvalidDecision,
    Market,
    apply_transfers,
    check_lineup,
    chip_available,
    next_free_transfers,
    score_gw,
    selling_price,
)
from diffpl.replay.types import ChipName, Decision, Pick, SquadState, Transfer
from diffpl.rules import Position, load_rules

R = load_rules("2025-26")
R24 = load_rules("2024-25")

# Squad: ids 1-2 GKP, 3-7 DEF, 8-12 MID, 13-15 FWD, one per team. 16-18 spare players.
POS: dict[int, Position] = {
    **{i: "GKP" for i in (1, 2, 16)},
    **{i: "DEF" for i in range(3, 8)},
    **{i: "MID" for i in (*range(8, 13), 17)},
    **{i: "FWD" for i in (13, 14, 15, 18)},
}
MARKET = Market(price={i: 50 for i in POS}, team={i: f"T{i}" for i in POS}, position=POS)
STATE = SquadState(picks=tuple(Pick(i, 50) for i in range(1, 16)), bank=0, free_transfers=1)
# 4-4-2: bench is GK 2, MID 12, DEF 7, FWD 15.
LINEUP = (1, 3, 4, 5, 6, 8, 9, 10, 11, 13, 14)
BENCH = (2, 12, 7, 15)
DEC = Decision(lineup=LINEUP, bench=BENCH, captain=13, vice_captain=8)


def test_selling_price_keeps_half_the_rise_rounded_down() -> None:
    assert selling_price(50, 53, 0.5) == 51
    assert selling_price(50, 54, 0.5) == 52
    assert selling_price(50, 47, 0.5) == 47


def test_chip_slots_by_half() -> None:
    assert chip_available(R, (), "wildcard", 5)
    assert not chip_available(R, (), "wildcard", 1)
    used: tuple[tuple[ChipName, int], ...] = (("wildcard", 5),)
    assert not chip_available(R, used, "wildcard", 10)
    assert chip_available(R, used, "wildcard", 25)
    assert not chip_available(R, (("bboost", 7),), "3xc", 7)  # one chip per GW


def test_2024_25_has_single_free_hit() -> None:
    assert not chip_available(R24, (("freehit", 3),), "freehit", 30)


def test_extra_transfer_costs_a_hit() -> None:
    d = Decision(LINEUP, BENCH, 13, 8, transfers=(Transfer(14, 18), Transfer(12, 17)))
    applied = apply_transfers(R, STATE, d, MARKET, gw=5, unlimited=False)
    assert applied.hits == 4
    assert applied.n_transfers == 2


def test_wildcard_and_unlimited_transfers_are_free() -> None:
    moves = (Transfer(14, 18), Transfer(12, 17))
    wc = Decision(LINEUP, BENCH, 13, 8, transfers=moves, chip="wildcard")
    assert apply_transfers(R, STATE, wc, MARKET, gw=5, unlimited=False).hits == 0
    plain = Decision(LINEUP, BENCH, 13, 8, transfers=moves)
    assert apply_transfers(R, STATE, plain, MARKET, gw=17, unlimited=True).hits == 0


def test_budget_and_ownership_enforced() -> None:
    rich = Market(price={**MARKET.price, 18: 60}, team=MARKET.team, position=POS)
    with pytest.raises(InvalidDecision, match="over budget"):
        apply_transfers(
            R, STATE, Decision(LINEUP, BENCH, 13, 8, (Transfer(14, 18),)), rich, 5, False
        )
    with pytest.raises(InvalidDecision, match="does not own"):
        apply_transfers(
            R, STATE, Decision(LINEUP, BENCH, 13, 8, (Transfer(18, 17),)), MARKET, 5, False
        )


def test_position_and_club_limits_enforced() -> None:
    with pytest.raises(InvalidDecision, match="need"):
        apply_transfers(
            R, STATE, Decision(LINEUP, BENCH, 13, 8, (Transfer(3, 18),)), MARKET, 5, False
        )
    crowded = Market(
        price=MARKET.price, team={**MARKET.team, 18: "T13", 14: "T13", 12: "T13"}, position=POS
    )
    with pytest.raises(InvalidDecision, match="more than 3"):
        apply_transfers(
            R, STATE, Decision(LINEUP, BENCH, 13, 8, (Transfer(15, 18),)), crowded, 5, False
        )


def test_free_transfers_bank_up_to_cap() -> None:
    assert next_free_transfers(R, 1, 0, None, False) == 2
    assert next_free_transfers(R, 5, 0, None, False) == 5
    assert next_free_transfers(R, 2, 3, None, False) == 1
    assert next_free_transfers(R, 3, 9, "wildcard", False) == 4
    assert next_free_transfers(R24.model_copy(), 1, 0, None, False) == 2


def test_lineup_validation() -> None:
    squad = set(range(1, 16))
    check_lineup(R, squad, DEC, POS)
    bad_bench = Decision(LINEUP, (12, 2, 7, 15), 13, 8)
    with pytest.raises(InvalidDecision, match="goalkeeper"):
        check_lineup(R, squad, bad_bench, POS)
    two_dm = Decision((1, 3, 4, 8, 9, 10, 11, 12, 13, 14, 15), (2, 5, 6, 7), 13, 8)
    with pytest.raises(InvalidDecision, match="formation"):
        check_lineup(R, squad, two_dm, POS)


def everyone(points: int = 2) -> tuple[dict[int, int], dict[int, int]]:
    return {i: points for i in range(1, 16)}, {i: 90 for i in range(1, 16)}


def test_captain_doubles() -> None:
    pts, mins = everyone()
    pts[13] = 10
    s = score_gw(R, DEC, POS, pts, mins)
    assert s.points == 10 * 2 + 2 * 10
    assert s.armband == 13


def test_vice_takes_armband_when_captain_misses() -> None:
    pts, mins = everyone()
    mins[13] = 0
    pts[13] = 0
    pts[8] = 6
    s = score_gw(R, DEC, POS, pts, mins)
    assert s.armband == 8
    assert s.auto_subs == [(13, 12)]  # 4-5-1 is valid, so the first bench outfielder comes on
    assert s.points == 9 * 2 + 6 * 2 + 2  # 9 starters at 2, vice 6 doubled, sub 2


def test_auto_sub_respects_formation_and_order() -> None:
    pts, mins = everyone()
    del mins[3], pts[3]  # a DEF blanks; first bench outfield is MID 12
    s = score_gw(R, DEC, POS, pts, mins)
    # Removing DEF 3 leaves 3 DEF: still valid, so MID 12 (first in bench order) comes on.
    assert s.auto_subs == [(3, 12)]


def test_goalkeeper_only_replaced_by_goalkeeper() -> None:
    pts, mins = everyone()
    mins[1] = 0
    s = score_gw(R, DEC, POS, pts, mins)
    assert s.auto_subs == [(1, 2)]


def test_bench_boost_scores_all_fifteen() -> None:
    pts, mins = everyone()
    d = Decision(LINEUP, BENCH, 13, 8, chip="bboost")
    assert score_gw(R, d, POS, pts, mins).points == 15 * 2 + 2


def test_triple_captain() -> None:
    pts, mins = everyone()
    d = Decision(LINEUP, BENCH, 13, 8, chip="3xc")
    assert score_gw(R, d, POS, pts, mins).points == 11 * 2 + 2 * 2


def test_bench_player_booked_without_playing_does_not_count() -> None:
    pts, mins = everyone()
    pts[12], mins[12] = -1, 0
    assert score_gw(R, DEC, POS, pts, mins).points == 11 * 2 + 2
