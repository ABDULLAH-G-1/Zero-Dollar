-- Fails if any merged pull request has merged_at_utc < created_at_utc
select
    pr_id,
    created_at_utc,
    merged_at_utc
from {{ ref('fct_pull_requests') }}
where merged_at_utc is not null
  and merged_at_utc < created_at_utc
