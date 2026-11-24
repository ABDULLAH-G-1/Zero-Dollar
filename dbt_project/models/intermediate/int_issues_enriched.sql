with issues as (
    select * from {{ ref('stg_github__issues') }}
),

enriched as (
    select
        issue_id,
        issue_number,
        repo_full_name,
        author_login,
        issue_state,
        created_at_utc,
        updated_at_utc,
        closed_at_utc,
        cast(created_at_utc as date) as created_date,
        case
            when closed_at_utc is not null or issue_state = 'closed' then true
            else false
        end as is_closed,
        case
            when closed_at_utc is not null then
                greatest(round(date_diff('second', created_at_utc, closed_at_utc) / 3600.0, 2), 0.0)
            else null
        end as hours_to_close,
        case
            when issue_state = 'open' and created_at_utc < (current_timestamp - interval 30 day) then true
            else false
        end as is_stale
    from issues
)

select * from enriched
