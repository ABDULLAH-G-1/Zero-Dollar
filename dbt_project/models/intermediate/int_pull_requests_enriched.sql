with pull_requests as (
    select * from {{ ref('stg_github__pull_requests') }}
),

enriched as (
    select
        pr_id,
        pr_number,
        repo_full_name,
        author_login,
        pr_status,
        created_at_utc,
        updated_at_utc,
        merged_at_utc,
        closed_at_utc,
        cast(created_at_utc as date) as created_date,
        case
            when merged_at_utc is not null then true
            else false
        end as is_merged,
        case
            when merged_at_utc is not null then
                greatest(round(date_diff('second', created_at_utc, merged_at_utc) / 3600.0, 2), 0.0)
            else null
        end as hours_to_merge
    from pull_requests
)

select * from enriched
