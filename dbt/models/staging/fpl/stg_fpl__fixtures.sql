-- One row per fixture per snapshot. Scores in a snapshot are known as of fetched_at.
select
    cast(f.value ->> 'id' as int) as fixture_id,
    cast(f.value ->> 'event' as int) as gw,
    cast(f.value ->> 'kickoff_time' as timestamptz) as kickoff_time,
    cast(f.value ->> 'team_h' as int) as home_team_id,
    cast(f.value ->> 'team_a' as int) as away_team_id,
    cast(f.value ->> 'team_h_score' as int) as home_score,
    cast(f.value ->> 'team_a_score' as int) as away_score,
    cast(f.value ->> 'team_h_difficulty' as int) as home_difficulty,
    cast(f.value ->> 'team_a_difficulty' as int) as away_difficulty,
    cast(f.value ->> 'finished' as boolean) as finished,
    r.fetched_at as as_of,
    r.id as response_id
from {{ source('raw', 'fpl_api_responses') }} as r
cross join lateral jsonb_array_elements(r.payload) as f
where r.endpoint = 'fixtures'
