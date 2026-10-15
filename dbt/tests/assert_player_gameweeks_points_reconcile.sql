-- The mart must keep every point from staging: totals per season match exactly.
with stg as (
    select season, sum(total_points) as pts from {{ ref('stg_vaastav__player_gameweeks') }}
    group by season
),
mart as (
    select season, sum(total_points) as pts from {{ ref('fct_player_gameweeks') }}
    group by season
)
select coalesce(stg.season, mart.season) as season, stg.pts as stg_pts, mart.pts as mart_pts
from stg
full join mart on stg.season = mart.season
where stg.pts is distinct from mart.pts
