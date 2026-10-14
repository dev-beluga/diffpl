-- One row per player per fixture (double gameweeks give two rows per GW).
-- as_of: kickoff plus the settle interval. A row is never knowable before its match ends.
with src as (
    select season, row_num, data, source_commit
    from {{ ref('base_vaastav__rows') }}
    where file = 'gws/merged_gw.csv'
)

select
    season,
    row_num,
    {{ json_num('data', 'element', 'int') }} as element_id,
    data ->> 'name' as player_name,
    nullif(data ->> 'position', '') as position,
    nullif(data ->> 'team', '') as team_name,
    {{ json_num('data', 'fixture', 'int') }} as fixture_id,
    cast(coalesce(nullif(data ->> 'GW', ''), nullif(data ->> 'round', '')) as int) as gw,
    cast(nullif(data ->> 'kickoff_time', '') as timestamptz) as kickoff_time,
    {{ json_bool('data', 'was_home') }} as was_home,
    {{ json_num('data', 'opponent_team', 'int') }} as opponent_team_id,
    {{ json_num('data', 'minutes', 'int') }} as minutes,
    {{ json_num('data', 'total_points', 'int') }} as total_points,
    {{ json_num('data', 'goals_scored', 'int') }} as goals_scored,
    {{ json_num('data', 'assists', 'int') }} as assists,
    {{ json_num('data', 'clean_sheets', 'int') }} as clean_sheets,
    {{ json_num('data', 'goals_conceded', 'int') }} as goals_conceded,
    {{ json_num('data', 'saves', 'int') }} as saves,
    {{ json_num('data', 'yellow_cards', 'int') }} as yellow_cards,
    {{ json_num('data', 'red_cards', 'int') }} as red_cards,
    {{ json_num('data', 'own_goals', 'int') }} as own_goals,
    {{ json_num('data', 'penalties_missed', 'int') }} as penalties_missed,
    {{ json_num('data', 'penalties_saved', 'int') }} as penalties_saved,
    {{ json_num('data', 'bonus', 'int') }} as bonus,
    {{ json_num('data', 'bps', 'int') }} as bps,
    {{ json_num('data', 'influence') }} as influence,
    {{ json_num('data', 'creativity') }} as creativity,
    {{ json_num('data', 'threat') }} as threat,
    {{ json_num('data', 'ict_index') }} as ict_index,
    {{ json_num('data', 'expected_goals') }} as expected_goals,
    {{ json_num('data', 'expected_assists') }} as expected_assists,
    {{ json_num('data', 'expected_goal_involvements') }} as expected_goal_involvements,
    {{ json_num('data', 'expected_goals_conceded') }} as expected_goals_conceded,
    {{ json_num('data', 'starts', 'int') }} as starts,
    -- Price and ownership are recorded at the GW deadline, so they share the row's as_of.
    {{ json_num('data', 'value', 'int') }} as price_tenths,
    {{ json_num('data', 'selected', 'bigint') }} as selected_by,
    {{ json_num('data', 'transfers_in', 'int') }} as transfers_in,
    {{ json_num('data', 'transfers_out', 'int') }} as transfers_out,
    cast(nullif(data ->> 'kickoff_time', '') as timestamptz)
        + interval '{{ var("match_settle_interval") }}' as as_of,
    source_commit
from src
