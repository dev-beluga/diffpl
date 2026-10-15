-- Staging drops duplicate player-match rows. That is only safe if they carry the same data.
select season, data ->> 'element' as element, data ->> 'fixture' as fixture
from {{ ref('base_vaastav__rows') }}
where file = 'gws/merged_gw.csv'
group by season, data ->> 'element', coalesce(data ->> 'fixture', data ->> 'kickoff_time'), data ->> 'fixture'
having count(distinct data) > 1
