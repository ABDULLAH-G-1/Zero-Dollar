with contributors as (
    select * from {{ ref('int_contributor_activity') }}
)

select
    md5(author_login) as contributor_key,
    author_login,
    is_bot,
    first_seen_at_utc,
    total_commits,
    total_pull_requests,
    total_issues
from contributors
