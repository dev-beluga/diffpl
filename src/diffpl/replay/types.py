"""Squad state, decisions and the Manager interface for the replay env."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol

from diffpl.replay.data import Observation

ChipName = Literal["wildcard", "freehit", "bboost", "3xc"]


@dataclass(frozen=True)
class Pick:
    element_id: int
    purchase_price: int  # tenths of a million


@dataclass(frozen=True)
class Transfer:
    out_id: int
    in_id: int


@dataclass(frozen=True)
class SquadState:
    """What the manager owns going into a deadline."""

    picks: tuple[Pick, ...]  # 15 players, no order
    bank: int  # tenths
    free_transfers: int
    chips_used: tuple[tuple[ChipName, int], ...] = ()  # (chip, gw)

    def owns(self, element_id: int) -> bool:
        return any(p.element_id == element_id for p in self.picks)


@dataclass(frozen=True)
class Decision:
    """One deadline's moves. `lineup` is 11 starters; `bench` is 4 in substitution order,
    goalkeeper first. Transfers apply before the lineup is checked."""

    lineup: tuple[int, ...]
    bench: tuple[int, ...]
    captain: int
    vice_captain: int
    transfers: tuple[Transfer, ...] = ()
    chip: ChipName | None = None


@dataclass(frozen=True)
class ManagerView:
    """Everything a manager may see at a deadline."""

    obs: Observation
    squad: SquadState | None  # None before GW1: the manager picks an initial squad


@dataclass(frozen=True)
class InitialSquad:
    picks: tuple[int, ...]  # 15 element ids
    decision: Decision  # GW1 lineup, bench and captain


class Manager(Protocol):
    @property
    def name(self) -> str: ...

    def pick_squad(self, view: ManagerView) -> InitialSquad: ...

    def act(self, view: ManagerView) -> Decision: ...


@dataclass
class GwResult:
    gw: int
    points: int  # after hits
    hit_cost: int
    transfers: int
    chip: ChipName | None
    captain: int
    auto_subs: list[tuple[int, int]] = field(default_factory=list)  # (out, in)
