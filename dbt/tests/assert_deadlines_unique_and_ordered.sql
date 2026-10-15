-- One deadline per season and GW, and deadlines increase with GW.
with d as (
    select
        season,
        gw,
        deadline_time,
        count(*) over (partition by season, gw) as n,
        lag(deadline_time) over (partition by season order by gw) as prev_deadline
    from {{ ref('mart_gameweek_deadlines') }}
)

select * from d where n > 1 or deadline_time <= prev_deadline
