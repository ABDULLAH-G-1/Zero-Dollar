with repos as (
    select
        repo_key,
        repo_full_name
    from {{ ref('dim_repos') }}
),

commits as (
    select
        c.repo_key,
        c.commit_sha,
        c.contributor_key,
        contrib.is_bot
    from {{ ref('fct_commits') }} c
    inner join {{ ref('dim_contributors') }} contrib
        on c.contributor_key = contrib.contributor_key
),

commit_agg as (
    select
        repo_key,
        count(*) as total_commits,
        round(100.0 * count(case when is_bot then 1 end) / nullif(count(*), 0), 2) as bot_commit_pct
    from commits
    group by repo_key
),

prs as (
    select
        repo_key,
        pr_id,
        contributor_key,
        is_merged,
        hours_to_merge
    from {{ ref('fct_pull_requests') }}
),

pr_agg as (
    select
        repo_key,
        count(*) as total_prs,
        count(case when is_merged then 1 end) as merged_prs,
        round(avg(hours_to_merge), 2) as avg_hours_to_merge,
        round(median(hours_to_merge), 2) as median_hours_to_merge
    from prs
    group by repo_key
),

issues as (
    select
        repo_key,
        issue_id,
        contributor_key,
        issue_state
    from {{ ref('fct_issues') }}
),

issue_agg as (
    select
        repo_key,
        count(*) as total_issues,
        round(100.0 * count(case when issue_state = 'closed' then 1 end) / nullif(count(*), 0), 2) as issue_closure_rate_pct
    from issues
    group by repo_key
),

human_contributors as (
    select
        activity.repo_key,
        activity.contributor_key
    from (
        select repo_key, contributor_key from {{ ref('fct_commits') }}
        union
        select repo_key, contributor_key from {{ ref('fct_pull_requests') }}
        union
        select repo_key, contributor_key from {{ ref('fct_issues') }}
    ) activity
    inner join {{ ref('dim_contributors') }} contrib
        on activity.contributor_key = contrib.contributor_key
    where not contrib.is_bot
),

human_contributor_agg as (
    select
        repo_key,
        count(distinct contributor_key) as active_human_contributors
    from human_contributors
    group by repo_key
)

select
    r.repo_key,
    r.repo_full_name,
    coalesce(c.total_commits, 0) as total_commits,
    coalesce(p.total_prs, 0) as total_prs,
    coalesce(p.merged_prs, 0) as merged_prs,
    coalesce(p.avg_hours_to_merge, 0.0) as avg_hours_to_merge,
    coalesce(p.median_hours_to_merge, 0.0) as median_hours_to_merge,
    coalesce(i.total_issues, 0) as total_issues,
    coalesce(i.issue_closure_rate_pct, 0.0) as issue_closure_rate_pct,
    coalesce(h.active_human_contributors, 0) as active_human_contributors,
    coalesce(c.bot_commit_pct, 0.0) as bot_commit_pct
from repos r
left join commit_agg c on r.repo_key = c.repo_key
left join pr_agg p on r.repo_key = p.repo_key
left join issue_agg i on r.repo_key = i.repo_key
left join human_contributor_agg h on r.repo_key = h.repo_key
