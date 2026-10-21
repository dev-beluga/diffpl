-- One row per player per played fixture of the live season, from the latest element-summary
-- snapshot of each player. Columns follow stg_vaastav__player_gameweeks.
-- as_of: kickoff plus the settle interval, as for vaastav. Price and ownership are those at
-- the GW deadline (FPL's history rows record them there).
with latest as (
    select distinct on (url) payload
    from {{ source('raw', 'fpl_api_responses') }}
    where endpoint = 'element-summary'
    order by url, fetched_at desc
)

select
    cast(h.value ->> 'element' as int) as element_id,
    cast(h.value ->> 'fixture' as int) as fixture_id,
    cast(h.value ->> 'round' as int) as gw,
    cast(h.value ->> 'kickoff_time' as timestamptz) as kickoff_time,
    cast(h.value ->> 'was_home' as boolean) as was_home,
    cast(h.value ->> 'opponent_team' as int) as opponent_team_id,
    cast(h.value ->> 'minutes' as int) as minutes,
    cast(h.value ->> 'total_points' as int) as total_points,
    cast(h.value ->> 'goals_scored' as int) as goals_scored,
    cast(h.value ->> 'assists' as int) as assists,
    cast(h.value ->> 'clean_sheets' as int) as clean_sheets,
    cast(h.value ->> 'goals_conceded' as int) as goals_conceded,
    cast(h.value ->> 'saves' as int) as saves,
    cast(h.value ->> 'yellow_cards' as int) as yellow_cards,
    cast(h.value ->> 'red_cards' as int) as red_cards,
    cast(h.value ->> 'own_goals' as int) as own_goals,
    cast(h.value ->> 'penalties_missed' as int) as penalties_missed,
    cast(h.value ->> 'penalties_saved' as int) as penalties_saved,
    cast(h.value ->> 'bonus' as int) as bonus,
    cast(h.value ->> 'bps' as int) as bps,
    cast(h.value ->> 'influence' as numeric) as influence,
    cast(h.value ->> 'creativity' as numeric) as creativity,
    cast(h.value ->> 'threat' as numeric) as threat,
    cast(h.value ->> 'ict_index' as numeric) as ict_index,
    cast(h.value ->> 'expected_goals' as numeric) as expected_goals,
    cast(h.value ->> 'expected_assists' as numeric) as expected_assists,
    cast(h.value ->> 'starts' as int) as starts,
    cast(h.value ->> 'value' as int) as price_tenths,
    cast(h.value ->> 'selected' as bigint) as selected_by,
    cast(h.value ->> 'transfers_in' as int) as transfers_in,
    cast(h.value ->> 'transfers_out' as int) as transfers_out,
    cast(h.value ->> 'kickoff_time' as timestamptz)
        + interval '{{ var("match_settle_interval") }}' as as_of
from latest
cross join lateral jsonb_array_elements(latest.payload -> 'history') as h
