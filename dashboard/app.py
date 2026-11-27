"""OSS Engineering Health & Velocity Dashboard.

Streamlit BI application analyzing GitHub repositories using marts from DuckDB/MotherDuck.
"""

from datetime import datetime
import os
from pathlib import Path
import sys
from typing import Any

import duckdb
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# Ensure project root is available for imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# -----------------------------------------------------------------------------
# Streamlit Page Configuration & Styling
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="OSS Engineering Health & Velocity Dashboard",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
        .block-container {
            padding-top: 2rem;
            padding-bottom: 2rem;
            padding-left: 2rem;
            padding-right: 2rem;
        }
        .main-header {
            font-size: 2.1rem;
            font-weight: 700;
            letter-spacing: -0.5px;
            margin-bottom: 0.2rem;
        }
        .sub-header {
            font-size: 0.95rem;
            color: #64748b;
            margin-bottom: 1.5rem;
        }
        [data-testid="stMetricValue"] {
            font-size: 1.55rem;
            font-weight: 700;
        }
        [data-testid="stMetricLabel"] {
            font-size: 0.85rem;
            font-weight: 600;
            color: #64748b;
        }
        .footer-container {
            margin-top: 2.5rem;
            padding-top: 1.2rem;
            border-top: 1px solid rgba(226, 232, 240, 0.2);
            font-size: 0.85rem;
            color: #64748b;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .stack-badge {
            background: linear-gradient(90deg, #3b82f6 0%, #10b981 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-weight: 700;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


# -----------------------------------------------------------------------------
# Database Connection & Query Helpers
# -----------------------------------------------------------------------------
def get_target_env() -> tuple[str, str]:
    """Retrieve TARGET_ENV and MOTHERDUCK_TOKEN from st.secrets or .env."""
    target_env = "dev"
    motherduck_token = ""

    try:
        if "TARGET_ENV" in st.secrets:
            target_env = st.secrets["TARGET_ENV"]
            motherduck_token = st.secrets.get("MOTHERDUCK_TOKEN", "")
            return target_env, motherduck_token
    except Exception:
        pass

    from dotenv import load_dotenv

    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)
    target_env = os.getenv("TARGET_ENV", "dev")
    motherduck_token = os.getenv("MOTHERDUCK_TOKEN", "")

    return target_env, motherduck_token


def get_duckdb_connection():
    """Create a new DuckDB connection (read-only for local dev, or MotherDuck)."""
    target_env, motherduck_token = get_target_env()
    if target_env.lower() == "prod":
        return duckdb.connect(f"md:github_analytics?motherduck_token={motherduck_token}")
    db_path = str(PROJECT_ROOT / "data" / "github_warehouse.duckdb")
    return duckdb.connect(db_path, read_only=True)


@st.cache_data(ttl=300, show_spinner=False)
def run_query(query: str) -> pd.DataFrame:
    """Execute a read-only query against DuckDB and return a DataFrame, cleanly closing connection."""
    con = get_duckdb_connection()
    try:
        return con.execute(query).df()
    finally:
        con.close()


# -----------------------------------------------------------------------------
# Data Access Functions
# -----------------------------------------------------------------------------
@st.cache_data(ttl=300, show_spinner=False)
def get_available_repos() -> list[str]:
    """Fetch distinct repository names available in dim_repos."""
    df = run_query("select distinct repo_full_name from marts.dim_repos order by repo_full_name")
    return df["repo_full_name"].tolist()


@st.cache_data(ttl=300, show_spinner=False)
def get_kpis(selected_repos: tuple[str, ...], exclude_bots: bool) -> dict[str, Any]:
    """Calculate the 5 top-level KPI metrics across selected repositories."""
    repos_clause = ", ".join([f"'{r}'" for r in selected_repos])
    bot_filter = "and contrib.is_bot = false" if exclude_bots else ""

    q_commits = f"""
        select count(*) as total_commits
        from marts.fct_commits c
        join marts.dim_repos r on c.repo_key = r.repo_key
        left join marts.dim_contributors contrib on c.contributor_key = contrib.contributor_key
        where r.repo_full_name in ({repos_clause}) {bot_filter}
    """
    q_prs = f"""
        select 
            count(case when pr.is_merged then 1 end) as merged_prs,
            round(avg(pr.hours_to_merge), 1) as avg_merge_time_hrs
        from marts.fct_pull_requests pr
        join marts.dim_repos r on pr.repo_key = r.repo_key
        left join marts.dim_contributors contrib on pr.contributor_key = contrib.contributor_key
        where r.repo_full_name in ({repos_clause}) and pr.is_merged = true {bot_filter}
    """
    q_issues = f"""
        select 
            round(100.0 * count(case when i.issue_state = 'closed' then 1 end) / nullif(count(*), 0), 1) as closure_rate_pct
        from marts.fct_issues i
        join marts.dim_repos r on i.repo_key = r.repo_key
        left join marts.dim_contributors contrib on i.contributor_key = contrib.contributor_key
        where r.repo_full_name in ({repos_clause}) {bot_filter}
    """
    q_contributors = f"""
        with active as (
            select c.contributor_key, c.repo_key from marts.fct_commits c
            union
            select p.contributor_key, p.repo_key from marts.fct_pull_requests p
            union
            select i.contributor_key, i.repo_key from marts.fct_issues i
        )
        select count(distinct a.contributor_key) as active_contributors
        from active a
        join marts.dim_repos r on a.repo_key = r.repo_key
        left join marts.dim_contributors contrib on a.contributor_key = contrib.contributor_key
        where r.repo_full_name in ({repos_clause}) {bot_filter}
    """

    commits_df = run_query(q_commits)
    prs_df = run_query(q_prs)
    issues_df = run_query(q_issues)
    contributors_df = run_query(q_contributors)

    return {
        "total_commits": int(commits_df["total_commits"].iloc[0] or 0),
        "merged_prs": int(prs_df["merged_prs"].iloc[0] or 0),
        "avg_merge_time_hrs": float(prs_df["avg_merge_time_hrs"].iloc[0] or 0.0),
        "closure_rate_pct": float(issues_df["closure_rate_pct"].iloc[0] or 0.0),
        "active_contributors": int(contributors_df["active_contributors"].iloc[0] or 0),
    }


@st.cache_data(ttl=300, show_spinner=False)
def get_weekly_velocity(selected_repos: tuple[str, ...], exclude_bots: bool) -> pd.DataFrame:
    """Query commit count grouped by week and repository."""
    repos_clause = ", ".join([f"'{r}'" for r in selected_repos])
    bot_filter = "and contrib.is_bot = false" if exclude_bots else ""
    q = f"""
        select 
            r.repo_full_name as repository,
            date_trunc('week', c.commit_date) as week_start,
            count(*) as commits
        from marts.fct_commits c
        join marts.dim_repos r on c.repo_key = r.repo_key
        left join marts.dim_contributors contrib on c.contributor_key = contrib.contributor_key
        where r.repo_full_name in ({repos_clause}) {bot_filter}
        group by r.repo_full_name, date_trunc('week', c.commit_date)
        order by week_start asc, r.repo_full_name
    """
    return run_query(q)


@st.cache_data(ttl=300, show_spinner=False)
def get_pr_cycle_times(selected_repos: tuple[str, ...], exclude_bots: bool) -> pd.DataFrame:
    """Query average and median PR cycle times in hours per repository."""
    repos_clause = ", ".join([f"'{r}'" for r in selected_repos])
    bot_filter = "and contrib.is_bot = false" if exclude_bots else ""
    q = f"""
        select 
            r.repo_full_name as repository,
            round(avg(pr.hours_to_merge), 1) as avg_hours,
            round(median(pr.hours_to_merge), 1) as median_hours
        from marts.fct_pull_requests pr
        join marts.dim_repos r on pr.repo_key = r.repo_key
        left join marts.dim_contributors contrib on pr.contributor_key = contrib.contributor_key
        where r.repo_full_name in ({repos_clause}) and pr.is_merged = true {bot_filter}
        group by r.repo_full_name
        order by avg_hours desc
    """
    return run_query(q)


@st.cache_data(ttl=300, show_spinner=False)
def get_issue_backlog(selected_repos: tuple[str, ...], exclude_bots: bool) -> pd.DataFrame:
    """Query issue counts segmented by status (Closed, Open Active, Open Stale >30d)."""
    repos_clause = ", ".join([f"'{r}'" for r in selected_repos])
    bot_filter = "and contrib.is_bot = false" if exclude_bots else ""
    q = f"""
        select 
            r.repo_full_name as repository,
            case 
                when i.issue_state = 'closed' then 'Closed'
                when i.is_stale then 'Open (Stale >30d)'
                else 'Open (Active)'
            end as status,
            count(*) as count
        from marts.fct_issues i
        join marts.dim_repos r on i.repo_key = r.repo_key
        left join marts.dim_contributors contrib on i.contributor_key = contrib.contributor_key
        where r.repo_full_name in ({repos_clause}) {bot_filter}
        group by r.repo_full_name, status
        order by r.repo_full_name, status
    """
    return run_query(q)


@st.cache_data(ttl=300, show_spinner=False)
def get_top_contributors(selected_repos: tuple[str, ...], exclude_bots: bool) -> pd.DataFrame:
    """Fetch top 10 contributors by total contribution volume across selected repos."""
    repos_clause = ", ".join([f"'{r}'" for r in selected_repos])
    bot_filter = "where contrib.is_bot = false" if exclude_bots else ""
    q = f"""
        with repo_activity as (
            select c.contributor_key, 'commit' as act from marts.fct_commits c
            join marts.dim_repos r on c.repo_key = r.repo_key where r.repo_full_name in ({repos_clause})
            union all
            select p.contributor_key, 'pr' as act from marts.fct_pull_requests p
            join marts.dim_repos r on p.repo_key = r.repo_key where r.repo_full_name in ({repos_clause})
            union all
            select i.contributor_key, 'issue' as act from marts.fct_issues i
            join marts.dim_repos r on i.repo_key = r.repo_key where r.repo_full_name in ({repos_clause})
        ),
        contrib_stats as (
            select 
                contrib.author_login,
                contrib.is_bot,
                count(case when a.act = 'commit' then 1 end) as commits,
                count(case when a.act = 'pr' then 1 end) as pull_requests,
                count(case when a.act = 'issue' then 1 end) as issues,
                count(*) as total_contributions
            from repo_activity a
            join marts.dim_contributors contrib on a.contributor_key = contrib.contributor_key
            {bot_filter}
            group by contrib.author_login, contrib.is_bot
        )
        select 
            author_login as "Contributor",
            is_bot as "Bot",
            commits as "Commits",
            pull_requests as "Pull Requests",
            issues as "Issues",
            total_contributions as "Total Contributions"
        from contrib_stats
        order by total_contributions desc
        limit 10
    """
    return run_query(q)


@st.cache_data(ttl=300, show_spinner=False)
def get_repo_summary(selected_repos: tuple[str, ...]) -> pd.DataFrame:
    """Fetch repository health summary table joined with stars and forks."""
    repos_clause = ", ".join([f"'{r}'" for r in selected_repos])
    q = f"""
        select 
            m.repo_full_name as "Repository",
            r.stars_count as "Stars",
            r.forks_count as "Forks",
            m.total_commits as "Commits",
            m.total_prs as "Total PRs",
            m.merged_prs as "Merged PRs",
            m.avg_hours_to_merge as "Avg Merge (hrs)",
            m.median_hours_to_merge as "Median Merge (hrs)",
            m.total_issues as "Total Issues",
            m.issue_closure_rate_pct as "Closure Rate (%)",
            m.active_human_contributors as "Active Contributors",
            m.bot_commit_pct as "Bot Commit (%)"
        from marts.mart_repo_health_summary m
        join marts.dim_repos r on m.repo_key = r.repo_key
        where m.repo_full_name in ({repos_clause})
        order by m.total_commits desc
    """
    return run_query(q)


@st.cache_data(ttl=300, show_spinner=False)
def get_latest_ingested_at() -> str:
    """Fetch the latest pipeline ingestion timestamp from dim_repos."""
    q = "select max(ingested_at_utc) as latest_ingest from marts.dim_repos"
    val = run_query(q)["latest_ingest"].iloc[0]
    if pd.isna(val) or val is None:
        return "N/A"
    if hasattr(val, "strftime"):
        return val.strftime("%Y-%m-%d %H:%M:%S UTC")
    return str(val)


# -----------------------------------------------------------------------------
# Main Application Flow
# -----------------------------------------------------------------------------
def main():
    target_env, _ = get_target_env()

    # --- Sidebar Controls ---
    st.sidebar.title("🎛️ Analytics Controls")
    st.sidebar.markdown(
        f"**Environment:** `{target_env.upper()}` "
        + ("*(MotherDuck)*" if target_env.lower() == "prod" else "*(DuckDB Local)*")
    )

    available_repos = get_available_repos()
    selected_repos = st.sidebar.multiselect(
        "Select Repositories",
        options=available_repos,
        default=available_repos,
        help="Filter metrics and charts by repository",
    )

    exclude_bots = st.sidebar.toggle(
        "Exclude Bots",
        value=True,
        help="Filter out automated bot accounts from velocity, cycles, and leaderboard metrics",
    )

    warehouse_label = "MotherDuck (Cloud)" if target_env.lower() == "prod" else "DuckDB (Local)"
    st.sidebar.markdown("---")
    st.sidebar.info(
        "**Stack Architecture:**\n"
        "- Ingestion: `dlt` (GitHub REST v3)\n"
        f"- Warehouse: `{warehouse_label}`\n"
        "- Transformations: `dbt-duckdb`\n"
        "- BI Layer: `Streamlit` & `Plotly`"
    )

    if not selected_repos:
        st.warning("⚠️ Please select at least one repository in the sidebar.")
        st.stop()

    repos_tuple = tuple(selected_repos)

    # --- Header Section ---
    st.markdown('<div class="main-header">⚡ OSS Engineering Health & Velocity Dashboard</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sub-header">Multi-repository analytics across commit velocity, PR merge cycles, issue backlog, and contributor dynamics.</div>',
        unsafe_allow_html=True,
    )

    # --- 1. Top KPI Row (5 Metrics) ---
    kpis = get_kpis(repos_tuple, exclude_bots)
    c1, c2, c3, c4, c5 = st.columns(5)

    with c1:
        with st.container(border=True):
            st.metric(
                label="Total Commits",
                value=f"{kpis['total_commits']:,}",
                help="Total Git commits across selected repositories",
            )
    with c2:
        with st.container(border=True):
            st.metric(
                label="Merged PRs",
                value=f"{kpis['merged_prs']:,}",
                help="Count of pull requests successfully merged into default branch",
            )
    with c3:
        with st.container(border=True):
            st.metric(
                label="Avg PR Merge Time",
                value=f"{kpis['avg_merge_time_hrs']:.1f} hrs",
                help="Average duration in hours from PR creation to merge",
            )
    with c4:
        with st.container(border=True):
            st.metric(
                label="Issue Closure Rate",
                value=f"{kpis['closure_rate_pct']:.1f}%",
                help="Percentage of closed issues out of total issues tracked",
            )
    with c5:
        with st.container(border=True):
            st.metric(
                label="Active Contributors",
                value=f"{kpis['active_contributors']:,}",
                help="Distinct authors participating across commits, PRs, or issues",
            )

    st.markdown("---")

    # --- 2. Weekly Commit Velocity (Line Chart) ---
    st.subheader("📈 Weekly Commit Velocity")
    st.caption("Weekly commit volume comparison across selected repositories")
    velocity_df = get_weekly_velocity(repos_tuple, exclude_bots)

    if not velocity_df.empty:
        fig_velocity = px.line(
            velocity_df,
            x="week_start",
            y="commits",
            color="repository",
            markers=True,
            labels={"week_start": "Week Starting", "commits": "Commits", "repository": "Repository"},
            color_discrete_sequence=px.colors.qualitative.Prism,
        )
        fig_velocity.update_layout(
            height=380,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            hovermode="x unified",
            xaxis=dict(showgrid=True, gridcolor="rgba(128,128,128,0.2)"),
            yaxis=dict(showgrid=True, gridcolor="rgba(128,128,128,0.2)"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, title_text=""),
            margin=dict(t=45, b=40, l=20, r=20),
        )
        st.plotly_chart(fig_velocity, use_container_width=True, config={"displayModeBar": False})
    else:
        st.info("No commit history found for the selected repositories.")

    # --- 3. Two-Column Row: PR Cycle Time & Issue Backlog ---
    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("⏱️ PR Cycle Time Comparison")
        st.caption("Average vs median hours required to merge pull requests")
        cycle_df = get_pr_cycle_times(repos_tuple, exclude_bots)
        if not cycle_df.empty:
            fig_cycle = go.Figure()
            fig_cycle.add_trace(
                go.Bar(
                    x=cycle_df["repository"],
                    y=cycle_df["avg_hours"],
                    name="Avg Hours",
                    marker_color="#3b82f6",
                )
            )
            fig_cycle.add_trace(
                go.Bar(
                    x=cycle_df["repository"],
                    y=cycle_df["median_hours"],
                    name="Median Hours",
                    marker_color="#10b981",
                )
            )
            fig_cycle.update_layout(
                height=380,
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                barmode="group",
                xaxis=dict(title="Repository", showgrid=False),
                yaxis=dict(title="Hours to Merge", showgrid=True, gridcolor="rgba(128,128,128,0.2)"),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, title_text=""),
                margin=dict(t=45, b=40, l=20, r=20),
            )
            st.plotly_chart(fig_cycle, use_container_width=True, config={"displayModeBar": False})
        else:
            st.info("No merged pull requests available for cycle time analysis.")

    with col_right:
        st.subheader("📋 Issue Backlog Health")
        st.caption("Issue state distribution: Closed vs Active vs Stale (>30d)")
        backlog_df = get_issue_backlog(repos_tuple, exclude_bots)
        if not backlog_df.empty:
            color_map = {
                "Closed": "#10b981",
                "Open (Active)": "#3b82f6",
                "Open (Stale >30d)": "#ef4444",
            }
            fig_backlog = px.bar(
                backlog_df,
                x="repository",
                y="count",
                color="status",
                color_discrete_map=color_map,
                labels={"count": "Issue Count", "repository": "Repository", "status": "Status"},
            )
            fig_backlog.update_layout(
                height=380,
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                barmode="stack",
                xaxis=dict(title="Repository", showgrid=False),
                yaxis=dict(title="Issue Count", showgrid=True, gridcolor="rgba(128,128,128,0.2)"),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, title_text=""),
                margin=dict(t=45, b=40, l=20, r=20),
            )
            st.plotly_chart(fig_backlog, use_container_width=True, config={"displayModeBar": False})
        else:
            st.info("No issue backlog records found.")

    st.markdown("---")

    # --- 4. Top 10 Contributors Leaderboard ---
    st.subheader("🏆 Top 10 Contributors Leaderboard")
    top_contrib_df = get_top_contributors(repos_tuple, exclude_bots)

    if not top_contrib_df.empty:
        tab_chart, tab_table = st.tabs(["Leaderboard Chart", "Contributor Table"])

        with tab_chart:
            st.caption("Top 10 contributors by combined volume (commits, PRs, issues)")
            # Sort ascending for horizontal bar chart so highest is at top
            chart_df = top_contrib_df.sort_values(by="Total Contributions", ascending=True)
            max_val = float(chart_df["Total Contributions"].max()) if not chart_df.empty else 100.0

            fig_leaderboard = px.bar(
                chart_df,
                x="Total Contributions",
                y="Contributor",
                orientation="h",
                color="Total Contributions",
                color_continuous_scale="Viridis",
                text="Total Contributions",
            )
            fig_leaderboard.update_traces(
                textposition="outside",
                cliponaxis=False,
            )
            fig_leaderboard.update_layout(
                height=400,
                uniformtext_mode="hide",
                coloraxis_showscale=False,
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                margin=dict(t=45, b=40, l=20, r=20),
                xaxis=dict(
                    range=[0, max_val * 1.18],
                    showgrid=True,
                    gridcolor="rgba(128,128,128,0.2)",
                    title="Total Contributions",
                ),
                yaxis=dict(title="Contributor", showgrid=False),
            )
            st.plotly_chart(fig_leaderboard, use_container_width=True, config={"displayModeBar": False})

        with tab_table:
            table_df = top_contrib_df.copy()
            table_df["Type"] = table_df["Bot"].apply(lambda b: "Bot" if b else "Human")
            table_df = table_df[["Contributor", "Type", "Commits", "Pull Requests", "Issues", "Total Contributions"]]

            st.dataframe(
                table_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Contributor": st.column_config.TextColumn("Contributor"),
                    "Type": st.column_config.TextColumn("Type"),
                    "Commits": st.column_config.NumberColumn("Commits", format="%d"),
                    "Pull Requests": st.column_config.NumberColumn("Pull Requests", format="%d"),
                    "Issues": st.column_config.NumberColumn("Issues", format="%d"),
                    "Total Contributions": st.column_config.NumberColumn("Total Contributions", format="%d"),
                },
            )
    else:
        st.info("No contributor records found.")

    st.markdown("---")

    # --- 5. Repo Health Summary Table ---
    st.subheader("📊 Repository Health Summary Mart")
    summary_df = get_repo_summary(repos_tuple)

    if not summary_df.empty:
        rename_map = {
            "Repository": "Repository",
            "Stars": "Stars",
            "Forks": "Forks",
            "Commits": "Commits",
            "Total PRs": "PRs",
            "Merged PRs": "Merged",
            "Avg Merge (hrs)": "Avg Merge (h)",
            "Median Merge (hrs)": "Med Merge (h)",
            "Closure Rate (%)": "Closure %",
            "Active Contributors": "Human Devs",
            "Bot Commit (%)": "Bot %",
        }
        compact_cols = [
            "Repository",
            "Stars",
            "Forks",
            "Commits",
            "PRs",
            "Merged",
            "Avg Merge (h)",
            "Med Merge (h)",
            "Closure %",
            "Human Devs",
            "Bot %",
        ]
        display_summary = summary_df.rename(columns=rename_map)[compact_cols]

        st.dataframe(
            display_summary,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Repository": st.column_config.TextColumn("Repository"),
                "Stars": st.column_config.NumberColumn("Stars", format="%d"),
                "Forks": st.column_config.NumberColumn("Forks", format="%d"),
                "Commits": st.column_config.NumberColumn("Commits", format="%d"),
                "PRs": st.column_config.NumberColumn("PRs", format="%d"),
                "Merged": st.column_config.NumberColumn("Merged", format="%d"),
                "Avg Merge (h)": st.column_config.NumberColumn("Avg Merge (h)", format="%.1f"),
                "Med Merge (h)": st.column_config.NumberColumn("Med Merge (h)", format="%.1f"),
                "Closure %": st.column_config.NumberColumn("Closure %", format="%.1f%%"),
                "Human Devs": st.column_config.NumberColumn("Human Devs", format="%d"),
                "Bot %": st.column_config.NumberColumn("Bot %", format="%.1f%%"),
            },
        )
    else:
        st.info("No summary mart records found.")

    # --- 6. Footer ---
    latest_ingest = get_latest_ingested_at()
    st.markdown(
        f"""
        <div class="footer-container">
            <div>
                <strong>Pipeline Ingestion:</strong> Last sync <code>{latest_ingest}</code>
            </div>
            <div>
                Engineered with <span class="stack-badge">dlt → DuckDB → dbt → Streamlit</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
