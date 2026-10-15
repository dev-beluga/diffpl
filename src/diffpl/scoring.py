"""FPL points for one player in one match, from a season's rules.

Bonus is an input, not computed: BPS tables are not encoded (see config/rules).
"""

from __future__ import annotations

from dataclasses import dataclass

from diffpl.rules import Position, Rules


@dataclass(frozen=True)
class MatchStats:
    minutes: int
    goals_scored: int = 0
    assists: int = 0
    clean_sheets: int = 0
    goals_conceded: int = 0
    saves: int = 0
    penalties_saved: int = 0
    penalties_missed: int = 0
    yellow_cards: int = 0
    red_cards: int = 0
    own_goals: int = 0
    bonus: int = 0
    defensive_contribution: int = 0


def player_points(rules: Rules, position: Position, s: MatchStats) -> int:
    sc = rules.scoring
    # No early return for 0 minutes: an unused substitute can still be booked.
    long_play = s.minutes >= sc.minutes.long_play_threshold
    pts = 0
    if s.minutes > 0:
        pts = sc.minutes.long_play if long_play else sc.minutes.short_play
    pts += s.goals_scored * sc.goals_scored[position]
    pts += s.assists * sc.assists
    if long_play:
        pts += s.clean_sheets * sc.clean_sheets[position]
    pts += (s.goals_conceded // sc.goals_conceded_per) * sc.goals_conceded[position]
    pts += (s.saves // sc.saves_per) * sc.saves
    pts += s.penalties_saved * sc.penalties_saved
    pts += s.penalties_missed * sc.penalties_missed
    pts += s.yellow_cards * sc.yellow_cards
    pts += s.red_cards * sc.red_cards
    pts += s.own_goals * sc.own_goals
    pts += s.bonus
    dc = sc.defensive_contribution
    if dc is not None and position != "GKP" and s.defensive_contribution >= dc.threshold[position]:
        pts += dc.points[position]
    return pts
