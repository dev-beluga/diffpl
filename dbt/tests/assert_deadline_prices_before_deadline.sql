-- Leakage guard: deadline prices must be visible before the deadline and after the previous one.
select p.*
from {{ ref('mart_player_deadline_prices') }} as p
inner join {{ ref('mart_gameweek_deadlines') }} as d on p.season = d.season and p.gw = d.gw
left join {{ ref('mart_gameweek_deadlines') }} as prev
    on p.season = prev.season and prev.gw = p.gw - 1
where p.as_of >= d.deadline_time or p.as_of <= prev.deadline_time
