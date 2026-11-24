with pull_requests as (
    select * from {{ ref('int_pull_requests_enriched') }}
)

select
    pr_id,
    md5(repo_full_name) as repo_key,
    md5(author_login) as contributor_key,
    pr_status,
    is_merged,
    hours_to_merge,
    created_at_utc,
    merged_at_utc
from pull_requests
