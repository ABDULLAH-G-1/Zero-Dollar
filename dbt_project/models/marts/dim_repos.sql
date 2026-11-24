with repos as (
    select * from {{ ref('stg_github__repos') }}
)

select
    md5(repo_full_name) as repo_key,
    repo_id,
    repo_full_name,
    stars_count,
    forks_count,
    open_issues_count,
    default_branch,
    ingested_at_utc
from repos
