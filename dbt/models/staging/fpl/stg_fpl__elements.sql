-- One row per player per bootstrap snapshot. as_of is when the snapshot was fetched.
select
    cast(p.value ->> 'id' as int) as element_id,
    cast(p.value ->> 'code' as int) as player_code,
    p.value ->> 'web_name' as web_name,
    cast(p.value ->> 'team' as int) as team_id,
    cast(p.value ->> 'element_type' as int) as element_type,
    cast(p.value ->> 'now_cost' as int) as price_tenths,
    p.value ->> 'status' as status,
    cast(p.value ->> 'chance_of_playing_next_round' as int) as chance_next_round,
    nullif(p.value ->> 'news', '') as news,
    cast(p.value ->> 'selected_by_percent' as numeric) as selected_by_percent,
    -- Owner count, the unit vaastav and element-summary history use.
    round(
        cast(p.value ->> 'selected_by_percent' as numeric)
        * cast(r.payload ->> 'total_players' as numeric) / 100
    )::bigint as selected_by,
    cast(p.value ->> 'transfers_in_event' as int) as transfers_in_event,
    cast(p.value ->> 'transfers_out_event' as int) as transfers_out_event,
    r.fetched_at as as_of,
    r.id as response_id
from {{ source('raw', 'fpl_api_responses') }} as r
cross join lateral jsonb_array_elements(r.payload -> 'elements') as p
where r.endpoint = 'bootstrap-static'
