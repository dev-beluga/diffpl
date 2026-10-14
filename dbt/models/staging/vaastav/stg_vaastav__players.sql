-- Identity columns only. players_raw.csv is an end-of-season snapshot; its prices, totals
-- and news leak future information and are deliberately not exposed.
select
    season,
    {{ json_num('data', 'id', 'int') }} as element_id,
    {{ json_num('data', 'code', 'int') }} as player_code,
    data ->> 'first_name' as first_name,
    data ->> 'second_name' as second_name,
    data ->> 'web_name' as web_name,
    {{ json_num('data', 'element_type', 'int') }} as element_type,
    -- End-of-season team: a mid-season transfer shows only the final club.
    {{ json_num('data', 'team', 'int') }} as team_id,
    source_commit
from {{ ref('base_vaastav__rows') }}
where file = 'players_raw.csv'
