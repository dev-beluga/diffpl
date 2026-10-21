"""Live planner: free transfers rebuilt from an entry's history."""

from diffpl.optim.live import free_transfers
from diffpl.replay.types import ChipName
from diffpl.rules import load_rules

RULES = load_rules("2026-27")


def test_no_transfers_banks_up_to_the_cap() -> None:
    assert free_transfers(RULES, [], 2) == 1
    assert free_transfers(RULES, [], 3) == 2
    assert free_transfers(RULES, [], 30) == RULES.transfers.max_banked


def test_gw1_moves_are_free_and_later_moves_use_the_bank() -> None:
    history: list[tuple[int, int, ChipName | None]] = [
        (1, 9, None),
        (2, 0, None),
        (3, 2, None),
    ]  # 2 banked at GW3, both used
    assert free_transfers(RULES, history, 4) == 1


def test_hits_do_not_go_negative() -> None:
    assert free_transfers(RULES, [(2, 3, None)], 3) == 1


def test_wildcard_keeps_the_bank() -> None:
    history: list[tuple[int, int, ChipName | None]] = [(2, 0, None), (3, 6, "wildcard")]
    assert free_transfers(RULES, history, 4) == 3
