select
    season,
    {{ json_num('data', 'id', 'int') }} as team_id,
    {{ json_num('data', 'code', 'int') }} as team_code,
    data ->> 'name' as team_name,
    data ->> 'short_name' as short_name,
    source_commit
from {{ ref('base_vaastav__rows') }}
where file = 'teams.csv'
