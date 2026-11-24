with source as (
    select * from {{ source('github_raw', 'raw_repos') }}
),

renamed as (
    select
        cast(id as bigint) as repo_id,
        case
            when full_name = 'dbt-labs/dbt' then 'dbt-labs/dbt-core'
            else cast(full_name as varchar)
        end as repo_full_name,
        cast(stargazers_count as bigint) as stars_count,
        cast(forks_count as bigint) as forks_count,
        cast(open_issues_count as bigint) as open_issues_count,
        cast(default_branch as varchar) as default_branch,
        cast(ingested_at_utc as timestamp with time zone) as ingested_at_utc
    from source
)

select * from renamed
