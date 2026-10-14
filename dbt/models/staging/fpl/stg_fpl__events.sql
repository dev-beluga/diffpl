-- One row per GW per bootstrap snapshot. as_of is when the snapshot was fetched.
select
    cast(e.value ->> 'id' as int) as gw,
    cast(e.value ->> 'deadline_time' as timestamptz) as deadline_time,
    cast(e.value ->> 'finished' as boolean) as finished,
    r.fetched_at as as_of,
    r.id as response_id
from {{ source('raw', 'fpl_api_responses') }} as r
cross join lateral jsonb_array_elements(r.payload -> 'events') as e
where r.endpoint = 'bootstrap-static'
