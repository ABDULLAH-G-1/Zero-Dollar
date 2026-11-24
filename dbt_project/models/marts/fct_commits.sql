with commits as (
    select * from {{ ref('stg_github__commits') }}
)

select
    commit_sha,
    md5(repo_full_name) as repo_key,
    md5(author_login) as contributor_key,
    cast(committed_at_utc as date) as commit_date,
    committed_at_utc
from commits
