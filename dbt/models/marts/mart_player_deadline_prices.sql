-- Price, ownership and transfer counts per player at each GW deadline.
-- vaastav stores these on the GW's match rows, whose as_of is after kickoff. FPL publishes
-- them at the deadline, so they get their own as_of just before it. A double GW has two
-- match rows with the same values; the first kickoff's row is kept.
with ranked as (
    select
        g.season,
        g.gw,
        g.element_id,
        g.price_tenths,
        g.selected_by,
        g.transfers_in,
        g.transfers_out,
        row_number() over (
            partition by g.season, g.gw, g.element_id order by g.kickoff_time, g.row_num
        ) as rn
    from {{ ref('stg_vaastav__player_gameweeks') }} as g
    where g.position <> 'AM'
)

select
    r.season,
    r.gw,
    r.element_id,
    r.price_tenths,
    r.selected_by,
    r.transfers_in,
    r.transfers_out,
    d.deadline_time - interval '1 minute' as as_of
from ranked as r
inner join {{ ref('mart_gameweek_deadlines') }} as d on r.season = d.season and r.gw = d.gw
where r.rn = 1
