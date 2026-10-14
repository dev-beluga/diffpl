-- Leakage guard: end-of-season stats from players_raw.csv must stay out of staging.
select column_name
from information_schema.columns
where table_schema = 'staging'
  and table_name = 'stg_vaastav__players'
  and column_name in ('now_cost', 'total_points', 'news', 'selected_by_percent', 'form')
