-- One row per league member with season-to-date figures from the latest snapshot.
with members as (
    select distinct on (league_id, entry_id)
        league_id, entry_id, entry_name, player_name, rank, total_points
    from {{ ref('stg_fpl__league_standings') }}
    -- only members whose history was imported (an import can cap members)
    where entry_id in (select entry_id from {{ ref('stg_fpl__entry_gameweeks') }})
    order by league_id, entry_id, as_of desc
),

gws as (
    select
        entry_id,
        sum(hit_cost) as hit_cost,
        sum(transfers) as transfers,
        sum(points_on_bench) as bench_points,
        max(gw) as last_gw
    from {{ ref('stg_fpl__entry_gameweeks') }}
    group by entry_id
),

latest as (
    select distinct on (entry_id) entry_id, value_tenths, bank_tenths
    from {{ ref('stg_fpl__entry_gameweeks') }}
    order by entry_id, gw desc
),

chips as (
    select entry_id, string_agg(chip || ' GW' || gw, ', ' order by gw) as chips_used,
           count(*) as chips_count
    from {{ ref('stg_fpl__entry_chips') }}
    group by entry_id
)

select
    m.league_id,
    m.entry_id,
    m.entry_name,
    m.player_name,
    m.rank,
    m.total_points,
    l.value_tenths,
    l.bank_tenths,
    g.hit_cost,
    g.transfers,
    g.bench_points,
    g.last_gw,
    coalesce(c.chips_used, '') as chips_used,
    coalesce(c.chips_count, 0) as chips_count
from members as m
left join gws as g on m.entry_id = g.entry_id
left join latest as l on m.entry_id = l.entry_id
left join chips as c on m.entry_id = c.entry_id
