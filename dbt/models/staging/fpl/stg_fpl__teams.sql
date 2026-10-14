select
    cast(t.value ->> 'id' as int) as team_id,
    cast(t.value ->> 'code' as int) as team_code,
    t.value ->> 'name' as team_name,
    t.value ->> 'short_name' as short_name,
    r.fetched_at as as_of,
    r.id as response_id
from {{ source('raw', 'fpl_api_responses') }} as r
cross join lateral jsonb_array_elements(r.payload -> 'teams') as t
where r.endpoint = 'bootstrap-static'
