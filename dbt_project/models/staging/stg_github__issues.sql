with source as (
    select * from {{ source('github_raw', 'raw_issues') }}
),

renamed as (
    select
        cast(id as bigint) as issue_id,
        cast(number as bigint) as issue_number,
        cast(repo_full_name as varchar) as repo_full_name,
        coalesce(cast(user__login as varchar), 'unknown') as author_login,
        lower(cast(state as varchar)) as issue_state,
        cast(created_at as timestamp with time zone) as created_at_utc,
        cast(updated_at as timestamp with time zone) as updated_at_utc,
        cast(closed_at as timestamp with time zone) as closed_at_utc
    from source
)

select * from renamed
