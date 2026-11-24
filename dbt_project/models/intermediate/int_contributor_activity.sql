with commits as (
    select
        author_login,
        'commit' as activity_type,
        committed_at_utc as activity_at_utc
    from {{ ref('stg_github__commits') }}
),

pull_requests as (
    select
        author_login,
        'pull_request' as activity_type,
        created_at_utc as activity_at_utc
    from {{ ref('stg_github__pull_requests') }}
),

issues as (
    select
        author_login,
        'issue' as activity_type,
        created_at_utc as activity_at_utc
    from {{ ref('stg_github__issues') }}
),

unioned_activity as (
    select * from commits
    union all
    select * from pull_requests
    union all
    select * from issues
),

aggregated as (
    select
        author_login,
        min(activity_at_utc) as first_seen_at_utc,
        count(case when activity_type = 'commit' then 1 end) as total_commits,
        count(case when activity_type = 'pull_request' then 1 end) as total_pull_requests,
        count(case when activity_type = 'issue' then 1 end) as total_issues,
        case
            when author_login ilike '%[bot]%' or author_login ilike '%bot%' then true
            else false
        end as is_bot
    from unioned_activity
    group by author_login
)

select * from aggregated
