-- One row per player per gameweek, historical seasons. Double gameweeks are summed; blank
-- gameweeks have no row. as_of is the latest fixture's as_of, so a row is known only once
-- every match in that gameweek has settled.
with pg as (
    select * from {{ ref('stg_vaastav__player_gameweeks') }}
),

-- Older seasons (2016-17 and 2018-19 at least) have no position column in merged_gw.csv. players_raw.csv gives
-- element_type, an identity field (not one of its leaky end-of-season columns).
player_types as (
    select
        season,
        element_id,
        case element_type
            when 1 then 'GKP' when 2 then 'DEF' when 3 then 'MID' when 4 then 'FWD' when 5 then 'AM'
        end as position
    from {{ ref('stg_vaastav__players') }}
)

select
    season,
    gw,
    element_id,
    max(player_name) as player_name,
    -- vaastav writes GK; the rules config and the FPL API use GKP.
    coalesce(
        max(case when pg.position = 'GK' then 'GKP' else pg.position end), max(pt.position)
    ) as position,
    max(pg.team_name) as team_name,
    count(*) as fixtures,
    sum(minutes) as minutes,
    sum(total_points) as total_points,
    sum(goals_scored) as goals_scored,
    sum(assists) as assists,
    sum(clean_sheets) as clean_sheets,
    sum(goals_conceded) as goals_conceded,
    sum(saves) as saves,
    sum(bonus) as bonus,
    sum(bps) as bps,
    sum(expected_goals) as expected_goals,
    sum(expected_assists) as expected_assists,
    -- Price is set before the deadline and is the same for every fixture in the gameweek.
    max(price_tenths) as price_tenths,
    max(selected_by) as selected_by,
    min(kickoff_time) as first_kickoff,
    max(as_of) as as_of
from pg
left join player_types as pt using (season, element_id)
group by season, gw, element_id
