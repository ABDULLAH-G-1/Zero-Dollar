with source as (
    select * from {{ source('github_raw', 'raw_pull_requests') }}
),

renamed as (
    select
        cast(id as bigint) as pr_id,
        cast(number as bigint) as pr_number,
        cast(repo_full_name as varchar) as repo_full_name,
        coalesce(cast(user__login as varchar), 'unknown') as author_login,
        case
            when merged_at is not null then 'merged'
            else lower(cast(state as varchar))
        end as pr_status,
        cast(created_at as timestamp with time zone) as created_at_utc,
        cast(updated_at as timestamp with time zone) as updated_at_utc,
        cast(merged_at as timestamp with time zone) as merged_at_utc,
        cast(closed_at as timestamp with time zone) as closed_at_utc
    from source
)

select * from renamed
