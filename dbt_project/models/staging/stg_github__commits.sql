with source as (
    select * from {{ source('github_raw', 'raw_commits') }}
),

renamed as (
    select
        cast(sha as varchar) as commit_sha,
        cast(repo_full_name as varchar) as repo_full_name,
        coalesce(
            cast(author__login as varchar),
            cast(commit__author__name as varchar),
            'unknown'
        ) as author_login,
        cast(commit__message as varchar) as commit_message,
        cast(commit__committer__date as timestamp with time zone) as committed_at_utc
    from source
)

select * from renamed
