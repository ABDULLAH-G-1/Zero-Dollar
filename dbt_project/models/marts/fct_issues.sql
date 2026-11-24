with issues as (
    select * from {{ ref('int_issues_enriched') }}
)

select
    issue_id,
    md5(repo_full_name) as repo_key,
    md5(author_login) as contributor_key,
    issue_state,
    is_stale,
    hours_to_close,
    created_at_utc,
    closed_at_utc
from issues
