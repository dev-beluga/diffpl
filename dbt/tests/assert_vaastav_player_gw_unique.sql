-- A player plays a fixture once. Rows with no fixture id (oldest seasons) key on kickoff.
select season, element_id, coalesce(fixture_id::text, kickoff_time::text) as match_key, count(*)
from {{ ref('stg_vaastav__player_gameweeks') }}
group by 1, 2, 3
having count(*) > 1
