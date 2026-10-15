-- League ownership per GW. ownership: share of members who own the player.
-- effective_ownership: summed multipliers / members (a captain counts 2, triple captain 3,
-- bench 0), which is what a manager's rank moves against when the player scores.
-- Members are standings entries whose history was imported (an import can cap members).
with members as (
    select distinct s.league_id, s.entry_id
    from {{ ref('stg_fpl__league_standings') }} as s
    where s.entry_id in (select entry_id from {{ ref('stg_fpl__entry_gameweeks') }})
),

sizes as (
    select league_id, count(*) as n_members from members group by league_id
)

select
    m.league_id,
    p.gw,
    p.element_id,
    count(*) as owners,
    sum(case when p.is_captain then 1 else 0 end) as captains,
    round(count(*)::numeric / s.n_members, 4) as ownership,
    round(sum(p.multiplier)::numeric / s.n_members, 4) as effective_ownership,
    s.n_members
from members as m
inner join {{ ref('stg_fpl__entry_picks') }} as p on m.entry_id = p.entry_id
inner join sizes as s on m.league_id = s.league_id
group by m.league_id, p.gw, p.element_id, s.n_members
