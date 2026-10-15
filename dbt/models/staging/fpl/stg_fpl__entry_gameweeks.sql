-- Official per-GW figures for each entry. `points` is before hits, `hit_cost` is the hit,
-- and `total_points` is the cumulative total after hits.
select
    r.entry_id,
    cast(h.value ->> 'event' as int) as gw,
    cast(h.value ->> 'points' as int) as points,
    cast(h.value ->> 'event_transfers_cost' as int) as hit_cost,
    cast(h.value ->> 'event_transfers' as int) as transfers,
    cast(h.value ->> 'total_points' as int) as total_points,
    cast(h.value ->> 'points_on_bench' as int) as points_on_bench,
    cast(h.value ->> 'bank' as int) as bank_tenths,
    cast(h.value ->> 'value' as int) as value_tenths,
    cast(h.value ->> 'overall_rank' as int) as overall_rank,
    r.as_of
from {{ ref('base_fpl__latest_responses') }} as r
cross join lateral jsonb_array_elements(r.payload -> 'current') as h
where r.endpoint = 'entry-history'
