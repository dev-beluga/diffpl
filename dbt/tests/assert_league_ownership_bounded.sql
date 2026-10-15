-- Ownership is a share of members; effective ownership is at most 3 (triple captain).
select * from {{ ref('mart_league_ownership') }}
where ownership <= 0 or ownership > 1 or effective_ownership < 0 or effective_ownership > 3
