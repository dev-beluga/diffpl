select season, gw, element_id, count(*)
from {{ ref('fct_player_gameweeks') }}
group by 1, 2, 3
having count(*) > 1
