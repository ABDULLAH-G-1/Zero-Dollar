-- Fails if any cycle time (hours_to_merge or hours_to_close) is negative
with pr_failures as (
    select
        pr_id as entity_id,
        'pull_request' as entity_type,
        hours_to_merge as cycle_time_hours
    from {{ ref('fct_pull_requests') }}
    where hours_to_merge < 0
),

issue_failures as (
    select
        issue_id as entity_id,
        'issue' as entity_type,
        hours_to_close as cycle_time_hours
    from {{ ref('fct_issues') }}
    where hours_to_close < 0
)

select * from pr_failures
union all
select * from issue_failures
