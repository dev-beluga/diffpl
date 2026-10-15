-- One row per season and GW with the deadline replay uses.
-- Live season: the deadline from the latest bootstrap snapshot.
-- Past seasons: vaastav has no deadlines, so estimate them as first kickoff minus 90 minutes,
-- the FPL convention since 2019-20. Flagged with is_estimated.
with past as (
    select
        season,
        gw,
        min(kickoff_time) - interval '90 minutes' as deadline_time,
        true as is_estimated
    from {{ ref('stg_vaastav__player_gameweeks') }}
    where gw is not null and kickoff_time is not null
    group by season, gw
),

latest_snapshot as (
    select max(as_of) as as_of from {{ ref('stg_fpl__events') }}
),

live as (
    select
        '{{ var("live_season") }}' as season,
        e.gw,
        e.deadline_time,
        false as is_estimated
    from {{ ref('stg_fpl__events') }} as e
    inner join latest_snapshot as l on e.as_of = l.as_of
)

select * from live
union all
select * from past
where season <> '{{ var("live_season") }}'
