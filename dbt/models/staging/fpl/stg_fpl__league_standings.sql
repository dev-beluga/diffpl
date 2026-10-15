select
    r.league_id,
    r.payload -> 'league' ->> 'name' as league_name,
    cast(s.value ->> 'entry' as int) as entry_id,
    s.value ->> 'entry_name' as entry_name,
    s.value ->> 'player_name' as player_name,
    cast(s.value ->> 'rank' as int) as rank,
    cast(s.value ->> 'total' as int) as total_points,
    cast(s.value ->> 'event_total' as int) as event_points,
    r.as_of
from {{ ref('base_fpl__latest_responses') }} as r
cross join lateral jsonb_array_elements(r.payload -> 'standings' -> 'results') as s
where r.endpoint = 'leagues-classic-standings'
