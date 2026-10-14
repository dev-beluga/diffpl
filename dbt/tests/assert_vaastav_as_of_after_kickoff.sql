-- Leakage guard: a GW row must never be available before its match kicks off.
select *
from {{ ref('stg_vaastav__player_gameweeks') }}
where as_of <= kickoff_time
