select
    r.entry_id,
    c.value ->> 'name' as chip,
    cast(c.value ->> 'event' as int) as gw,
    r.as_of
from {{ ref('base_fpl__latest_responses') }} as r
cross join lateral jsonb_array_elements(r.payload -> 'chips') as c
where r.endpoint = 'entry-history'
