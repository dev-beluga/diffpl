-- One row per entry, GW and squad slot. Slots 1-11 start; 12-15 are the bench in order.
select
    r.entry_id,
    r.gw,
    cast(p.value ->> 'element' as int) as element_id,
    cast(p.value ->> 'position' as int) as slot,
    cast(p.value ->> 'multiplier' as int) as multiplier,
    cast(p.value ->> 'is_captain' as boolean) as is_captain,
    cast(p.value ->> 'is_vice_captain' as boolean) as is_vice_captain,
    r.payload ->> 'active_chip' as active_chip,
    r.as_of
from {{ ref('base_fpl__latest_responses') }} as r
cross join lateral jsonb_array_elements(r.payload -> 'picks') as p
where r.endpoint = 'entry-picks'
