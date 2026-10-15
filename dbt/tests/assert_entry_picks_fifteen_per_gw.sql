-- Every stored squad has 15 players in distinct slots and exactly one captain.
select entry_id, gw
from {{ ref('stg_fpl__entry_picks') }}
group by entry_id, gw
having count(*) <> 15 or count(distinct slot) <> 15 or sum(is_captain::int) <> 1
