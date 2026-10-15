-- Latest snapshot of each league-related URL. Older snapshots stay in raw.
select distinct on (url)
    id as response_id,
    endpoint,
    url,
    cast(substring(url from '/entry/([0-9]+)/') as int) as entry_id,
    cast(substring(url from '/event/([0-9]+)/') as int) as gw,
    cast(substring(url from '/leagues-classic/([0-9]+)/') as int) as league_id,
    payload,
    fetched_at as as_of
from {{ source('raw', 'fpl_api_responses') }}
where endpoint in ('leagues-classic-standings', 'entry-history', 'entry-picks')
order by url, fetched_at desc
