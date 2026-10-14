-- One commit per season: the most recently ingested one. Older commits stay in raw.
with ranked as (
    select
        season,
        source_commit,
        rank() over (partition by season order by max(ingested_at) desc, source_commit) as rnk
    from {{ source('raw', 'vaastav_rows') }}
    group by season, source_commit
)

select r.season, r.file, r.row_num, r.data, r.source_commit, r.fetched_at
from {{ source('raw', 'vaastav_rows') }} as r
inner join ranked as k
    on r.season = k.season and r.source_commit = k.source_commit and k.rnk = 1
