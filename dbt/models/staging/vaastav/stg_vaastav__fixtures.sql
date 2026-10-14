with src as (
    select season, data, source_commit
    from {{ ref('base_vaastav__rows') }}
    where file = 'fixtures.csv'
)

select
    season,
    {{ json_num('data', 'id', 'int') }} as fixture_id,
    {{ json_num('data', 'event', 'int') }} as gw,
    cast(nullif(data ->> 'kickoff_time', '') as timestamptz) as kickoff_time,
    {{ json_num('data', 'team_h', 'int') }} as home_team_id,
    {{ json_num('data', 'team_a', 'int') }} as away_team_id,
    {{ json_num('data', 'team_h_score', 'int') }} as home_score,
    {{ json_num('data', 'team_a_score', 'int') }} as away_score,
    {{ json_num('data', 'team_h_difficulty', 'int') }} as home_difficulty,
    {{ json_num('data', 'team_a_difficulty', 'int') }} as away_difficulty,
    {{ json_bool('data', 'finished') }} as finished,
    -- The schedule is public before the season; scores are not. Consumers must use
    -- result_as_of for scores and difficulty is an end-of-season value (see docs).
    cast(nullif(data ->> 'kickoff_time', '') as timestamptz)
        + interval '{{ var("match_settle_interval") }}' as result_as_of,
    source_commit
from src
