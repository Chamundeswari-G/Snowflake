from io import BytesIO

import pandas as pd
import streamlit as st
from snowflake.snowpark.context import get_active_session

st.set_page_config(    page_title="Snowflake Authentication Security Center",
layout="wide")
st.title("Snowflake Authentication Security Center")

session = get_active_session()

st.markdown(
    """
    <style>
    [data-testid="stDataFrame"] thead th {
        font-weight: 700 !important;
    }
    [data-testid="stMetric"] * {
        font-weight: 600 !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

if "lookback_days" not in st.session_state:
    st.session_state.lookback_days = 30
if "only_successful" not in st.session_state:
    st.session_state.only_successful = True
if "min_logins" not in st.session_state:
    st.session_state.min_logins = 1
if "selected_service_account" not in st.session_state:
    st.session_state.selected_service_account = "All"


def classify_status(password_share_pct: float) -> str:
    if password_share_pct >= 50:
        return "Critical"
    if password_share_pct > 0 and password_share_pct < 50:
        return "Needs attention"
    return "On track"


def status_display(status: str) -> str:
    if status == "Critical":
        return "🔴 Critical"
    if status == "Needs attention":
        return "🟡 Needs attention"
    return "🟢 On track"


def human_policy_status(first_auth: str, second_auth: str, native_mfa_enrolled: str) -> str:
    first_auth = (first_auth or "UNKNOWN").upper()
    second_auth = (second_auth or "NONE").upper()
    native_mfa_enrolled = (native_mfa_enrolled or "FALSE").upper()

    if (
        first_auth == "PASSWORD"
        and second_auth == "NONE"
        and native_mfa_enrolled != "TRUE"
    ):
        return "Critical Risk"
    return "Compliant"


def human_policy_display(status: str) -> str:
    if status == "Critical Risk":
        return "🔴 Critical Risk"
    return "🟢 Compliant"


def fmt_count(value) -> str:
    try:
        return f"{int(round(float(value))):,}"
    except Exception:
        return ""


def fmt_pct(value) -> str:
    try:
        return f"{float(value):.2f}%"
    except Exception:
        return ""


def fmt_ts(value) -> str:
    if pd.isna(value):
        return ""
    try:
        return pd.to_datetime(value).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(value)


def escape_sql_literal(value: str) -> str:
    return value.replace("'", "''")


def build_excel_bytes(df: pd.DataFrame, sheet_name: str = "Sheet1") -> bytes | None:
    buffer = BytesIO()
    try:
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name=sheet_name)
        buffer.seek(0)
        return buffer.read()
    except Exception:
        return None


with st.sidebar.form("filters_form"):
    st.header("Filters")

    lookback_days_input = st.slider(
        "Lookback window (days)",
        min_value=1,
        max_value=90,
        value=st.session_state.lookback_days,
        step=1,
    )

    only_successful_input = st.checkbox(
        "Only successful logins",
        value=st.session_state.only_successful,
    )

    min_logins_input = st.number_input(
        "Minimum logins to show",
        min_value=1,
        value=st.session_state.min_logins,
        step=1,
    )

    submitted = st.form_submit_button("Apply filters")

if submitted:
    st.session_state.lookback_days = lookback_days_input
    st.session_state.only_successful = only_successful_input
    st.session_state.min_logins = min_logins_input

lookback_days = st.session_state.lookback_days
only_successful = st.session_state.only_successful
min_logins = st.session_state.min_logins

success_filter = "AND lh.IS_SUCCESS = 'YES'" if only_successful else ""

st.caption(
    f"Last {lookback_days} days of login activity for users with TYPE = LEGACY_SERVICE"
)

st.info(
    "Non-password logins means any login method other than password authentication. "
    "The detail table shows the exact methods observed."
)

summary_sql = f"""
WITH service_users AS (
    SELECT
        NAME,
        LOGIN_NAME
    FROM SNOWFLAKE.ACCOUNT_USAGE.USERS
    WHERE UPPER(TYPE) = 'LEGACY_SERVICE'
      AND DELETED_ON IS NULL
),
login_events AS (
    SELECT
        su.NAME AS service_user,
        COALESCE(UPPER(lh.FIRST_AUTHENTICATION_FACTOR), 'UNKNOWN') AS auth_method,
        lh.EVENT_TIMESTAMP AS event_ts
    FROM SNOWFLAKE.ACCOUNT_USAGE.LOGIN_HISTORY lh
    JOIN service_users su
      ON lh.USER_NAME = su.LOGIN_NAME
    WHERE lh.EVENT_TYPE = 'LOGIN'
      AND lh.EVENT_TIMESTAMP >= DATEADD(day, -{lookback_days}, CURRENT_TIMESTAMP())
      {success_filter}
)
SELECT
    service_user AS "Service Account",
    COUNT(*) AS "Total Logins",
    SUM(IFF(auth_method = 'PASSWORD', 1, 0)) AS "Password Logins",
    SUM(IFF(auth_method <> 'PASSWORD', 1, 0)) AS "Non-Password Logins",
    ROUND(100 * SUM(IFF(auth_method = 'PASSWORD', 1, 0)) / NULLIF(COUNT(*), 0), 2) AS "Password Auth (%)",
    ROUND(100 * SUM(IFF(auth_method <> 'PASSWORD', 1, 0)) / NULLIF(COUNT(*), 0), 2) AS "Non-Password Auth (%)",
    MAX(event_ts) AS "Last Login",
    MAX(IFF(auth_method <> 'PASSWORD', event_ts, NULL)) AS "Last Non-Password Login"
FROM login_events
GROUP BY service_user
HAVING COUNT(*) >= {min_logins}
ORDER BY "Non-Password Auth (%)" DESC, "Total Logins" DESC, "Service Account"
"""

summary_df = session.sql(summary_sql).to_pandas()

if summary_df.empty:
    st.warning("No legacy service login activity found for the selected window.")
    st.stop()

for col in [
    "Total Logins",
    "Password Logins",
    "Non-Password Logins",
    "Password Auth (%)",
    "Non-Password Auth (%)",
]:
    summary_df[col] = pd.to_numeric(summary_df[col], errors="coerce").fillna(0)

service_account_options = ["All"] + sorted(summary_df["Service Account"].dropna().unique().tolist())

st.sidebar.selectbox(
    "Service Account",
    service_account_options,
    index=service_account_options.index(st.session_state.selected_service_account)
    if st.session_state.selected_service_account in service_account_options
    else 0,
    key="selected_service_account",
)

filtered_summary_df = summary_df.copy()
if st.session_state.selected_service_account != "All":
    filtered_summary_df = filtered_summary_df[
        filtered_summary_df["Service Account"] == st.session_state.selected_service_account
    ].copy()

filtered_summary_df["Migration Status"] = filtered_summary_df["Password Auth (%)"].apply(classify_status)
filtered_summary_df["Migration Status Display"] = filtered_summary_df["Migration Status"].apply(status_display)

status_order = {"Critical": 0, "Needs attention": 1, "On track": 2}
filtered_summary_df["Status Sort"] = filtered_summary_df["Migration Status"].map(status_order)

filtered_summary_df = (
    filtered_summary_df.sort_values(
        by=["Status Sort", "Non-Password Auth (%)", "Total Logins", "Service Account"],
        ascending=[True, False, False, True],
    )
    .drop(columns=["Status Sort"])
    .reset_index(drop=True)
)

total_logins = float(filtered_summary_df["Total Logins"].sum())
password_logins = float(filtered_summary_df["Password Logins"].sum())
non_password_logins = float(filtered_summary_df["Non-Password Logins"].sum())
service_accounts = int(filtered_summary_df["Service Account"].nunique())

password_share = round((password_logins * 100 / total_logins), 2) if total_logins else 0.0
non_password_share = round((non_password_logins * 100 / total_logins), 2) if total_logins else 0.0

migrated_accounts = int((filtered_summary_df["Non-Password Logins"] > 0).sum())
migration_pct = round(migrated_accounts * 100 / service_accounts, 1) if service_accounts else 0.0

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Legacy service accounts", f"{service_accounts} Accounts")
c2.metric("Total logins", fmt_count(total_logins))
c3.metric("Password authentication", f"{password_share:.2f}%")
c4.metric("Non-password authentication", f"{non_password_share:.2f}%")
c5.metric("Accounts migrated", f"{migration_pct:.1f}%")

if len(filtered_summary_df) > 0:
    st.progress(int(round(non_password_share)))

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
    [
        "Overview",
        "Accounts Detail",
        "Password Query Logs",
        "Authentication Methods",
        "Human Users",
        "Application Analysis",
    ]
)

auth_methods_sql = f"""
WITH login_events AS (
    SELECT
        u.NAME AS USER_NAME,
        u.TYPE AS USER_TYPE,
        COALESCE(UPPER(lh.FIRST_AUTHENTICATION_FACTOR), 'UNKNOWN') AS FIRST_AUTH_FACTOR,
        COALESCE(UPPER(lh.SECOND_AUTHENTICATION_FACTOR), 'NONE') AS SECOND_AUTH_FACTOR,
        lh.EVENT_TIMESTAMP
    FROM SNOWFLAKE.ACCOUNT_USAGE.LOGIN_HISTORY lh
    JOIN SNOWFLAKE.ACCOUNT_USAGE.USERS u
        ON lh.USER_NAME = u.LOGIN_NAME
    WHERE lh.EVENT_TYPE = 'LOGIN'
      AND lh.EVENT_TIMESTAMP >= DATEADD(day, -{lookback_days}, CURRENT_TIMESTAMP())
      {success_filter}
)
SELECT
    FIRST_AUTH_FACTOR,
    SECOND_AUTH_FACTOR,
    COUNT(*) AS LOGIN_COUNT,
    COUNT(DISTINCT USER_NAME) AS USER_COUNT,
    MAX(EVENT_TIMESTAMP) AS LAST_LOGIN
FROM login_events
GROUP BY
    1, 2
ORDER BY
    LOGIN_COUNT DESC,
    FIRST_AUTH_FACTOR,
    SECOND_AUTH_FACTOR
"""

auth_methods_df = session.sql(auth_methods_sql).to_pandas()

human_users_sql = f"""
WITH human_users AS (
    SELECT
        NAME,
        LOGIN_NAME,
        -- Check actual account configuration capabilities
        HAS_PASSWORD,
        EXT_AUTHN_DUO
    FROM SNOWFLAKE.ACCOUNT_USAGE.USERS
    WHERE (TYPE = 'PERSON' OR TYPE IS NULL)
      AND DELETED_ON IS NULL
      AND DISABLED = FALSE
),
login_counts AS (
    SELECT
        USER_NAME,
        COUNT(*) AS LOGIN_COUNT
    FROM SNOWFLAKE.ACCOUNT_USAGE.LOGIN_HISTORY
    WHERE EVENT_TYPE = 'LOGIN'
      AND EVENT_TIMESTAMP >= DATEADD(day, -{lookback_days}, CURRENT_TIMESTAMP())
    GROUP BY USER_NAME
),
latest_login AS (
    SELECT
        USER_NAME,
        COALESCE(UPPER(FIRST_AUTHENTICATION_FACTOR), 'UNKNOWN') AS FIRST_AUTH_FACTOR,
        COALESCE(UPPER(SECOND_AUTHENTICATION_FACTOR), 'NONE') AS SECOND_AUTH_FACTOR,
        EVENT_TIMESTAMP AS LAST_LOGIN,
        ROW_NUMBER() OVER (
            PARTITION BY USER_NAME
            ORDER BY EVENT_TIMESTAMP DESC
        ) AS RN
    FROM SNOWFLAKE.ACCOUNT_USAGE.LOGIN_HISTORY
    WHERE EVENT_TYPE = 'LOGIN'
      AND EVENT_TIMESTAMP >= DATEADD(day, -{lookback_days}, CURRENT_TIMESTAMP())
)
SELECT
    hu.NAME,
    hu.LOGIN_NAME,
    COALESCE(ll.FIRST_AUTH_FACTOR, 'UNKNOWN') AS FIRST_AUTH_FACTOR,
    COALESCE(ll.SECOND_AUTH_FACTOR, 'NONE') AS SECOND_AUTH_FACTOR,
    ll.LAST_LOGIN,
    COALESCE(lc.LOGIN_COUNT, 0) AS LOGIN_COUNT,
    -- Determine risk based on account settings rather than session type
    CASE
        WHEN hu.HAS_PASSWORD = TRUE AND hu.EXT_AUTHN_DUO = FALSE
        THEN 'Critical Risk'
        ELSE 'Compliant'
    END AS POLICY_STATUS
FROM human_users hu
LEFT JOIN login_counts lc
    ON hu.LOGIN_NAME = lc.USER_NAME
LEFT JOIN latest_login ll
    ON hu.LOGIN_NAME = ll.USER_NAME
   AND ll.RN = 1
ORDER BY
    CASE
        WHEN hu.HAS_PASSWORD = TRUE AND hu.EXT_AUTHN_DUO = FALSE THEN 0
        ELSE 1
    END,
    LAST_LOGIN DESC NULLS LAST,
    hu.NAME
"""

human_users_df = session.sql(human_users_sql).to_pandas()

applications_sql = f"""
SELECT
    CLIENT_APPLICATION_ID,
    AUTHENTICATION_METHOD,
    COUNT(*) AS TOTAL_SESSIONS
FROM SNOWFLAKE.ACCOUNT_USAGE.SESSIONS
WHERE CREATED_ON >= DATEADD(day, -{lookback_days}, CURRENT_TIMESTAMP())
GROUP BY
    1, 2
ORDER BY
    TOTAL_SESSIONS DESC
"""

applications_df = session.sql(applications_sql).to_pandas()

with tab1:
    st.subheader("Usage overview")
    chart_df = filtered_summary_df.set_index("Service Account")[["Password Logins", "Non-Password Logins"]]
    st.bar_chart(chart_df)

    st.subheader("Migration status summary")
    status_counts = (
        filtered_summary_df["Migration Status"]
        .value_counts()
        .reindex(["Critical", "Needs attention", "On track"])
        .fillna(0)
    )

    total_status_accounts = int(status_counts.sum())

    status_summary_df = pd.DataFrame(
        {
            "Migration Status": ["🔴 Critical", "🟡 Needs attention", "🟢 On track"],
            "Accounts": [
                int(status_counts["Critical"]),
                int(status_counts["Needs attention"]),
                int(status_counts["On track"]),
            ],
        }
    )
    status_summary_df["Share (%)"] = status_summary_df["Accounts"].apply(
        lambda x: f"{(x * 100 / total_status_accounts):.2f}%" if total_status_accounts else "0.00%"
    )

    st.dataframe(
        status_summary_df.reset_index(drop=True),
        use_container_width=True,
        height=220,
    )

with tab2:
    st.subheader("Account-level details")

    status_filter = st.selectbox(
        "Filter by migration status",
        ["All", "Critical", "Needs attention", "On track"],
        index=0,
    )

    detail_df = filtered_summary_df.copy()
    if status_filter != "All":
        detail_df = detail_df[detail_df["Migration Status"] == status_filter].copy()

    if detail_df.empty:
        st.warning("No accounts match the selected status filter.")
    elif len(detail_df) == 1:
        row = detail_df.iloc[0]

        st.markdown("### Selected Service Account")
        c1, c2, c3 = st.columns(3)
        c1.metric("Service Account", row["Service Account"])
        c2.metric("Migration Status", row["Migration Status Display"])
        c3.metric("Password Auth (%)", f'{row["Password Auth (%)"]:.2f}%')

        c4, c5, c6 = st.columns(3)
        c4.metric("Total Logins", fmt_count(row["Total Logins"]))
        c5.metric("Password Logins", fmt_count(row["Password Logins"]))
        c6.metric("Non-Password Logins", fmt_count(row["Non-Password Logins"]))

        c7, c8 = st.columns(2)
        c7.metric("Non-Password Auth (%)", f'{row["Non-Password Auth (%)"]:.2f}%')
        c8.metric("Last Login", fmt_ts(row["Last Login"]))

        st.metric("Last Non-Password Login", fmt_ts(row["Last Non-Password Login"]))

        single_df = detail_df[
            [
                "Service Account",
                "Total Logins",
                "Password Logins",
                "Non-Password Logins",
                "Password Auth (%)",
                "Non-Password Auth (%)",
                "Migration Status Display",
                "Last Login",
                "Last Non-Password Login",
            ]
        ].rename(columns={"Migration Status Display": "Migration Status"}).copy()

        single_df["Total Logins"] = single_df["Total Logins"].apply(fmt_count)
        single_df["Password Logins"] = single_df["Password Logins"].apply(fmt_count)
        single_df["Non-Password Logins"] = single_df["Non-Password Logins"].apply(fmt_count)
        single_df["Password Auth (%)"] = single_df["Password Auth (%)"].apply(fmt_pct)
        single_df["Non-Password Auth (%)"] = single_df["Non-Password Auth (%)"].apply(fmt_pct)
        single_df["Last Login"] = single_df["Last Login"].apply(fmt_ts)
        single_df["Last Non-Password Login"] = single_df["Last Non-Password Login"].apply(fmt_ts)

        st.dataframe(
            single_df.reset_index(drop=True),
            use_container_width=True,
            height=180,
        )

    else:
        display_df = detail_df[
            [
                "Service Account",
                "Total Logins",
                "Password Logins",
                "Non-Password Logins",
                "Password Auth (%)",
                "Non-Password Auth (%)",
                "Migration Status Display",
                "Last Login",
                "Last Non-Password Login",
            ]
        ].rename(columns={"Migration Status Display": "Migration Status"}).copy()

        display_df["Total Logins"] = display_df["Total Logins"].apply(fmt_count)
        display_df["Password Logins"] = display_df["Password Logins"].apply(fmt_count)
        display_df["Non-Password Logins"] = display_df["Non-Password Logins"].apply(fmt_count)
        display_df["Password Auth (%)"] = display_df["Password Auth (%)"].apply(fmt_pct)
        display_df["Non-Password Auth (%)"] = display_df["Non-Password Auth (%)"].apply(fmt_pct)
        display_df["Last Login"] = display_df["Last Login"].apply(fmt_ts)
        display_df["Last Non-Password Login"] = display_df["Last Non-Password Login"].apply(fmt_ts)

        st.dataframe(
            display_df.reset_index(drop=True),
            use_container_width=True,
            height=420,
        )

with tab3:
    st.subheader("Password Query Logs")

    selected_username = st.text_input(
        "Username filter",
        value="" if st.session_state.selected_service_account == "All" else st.session_state.selected_service_account,
        help="Enter a service account name, or leave it blank to use the selected service account from the sidebar.",
    ).strip()

    effective_username = selected_username or (
        "" if st.session_state.selected_service_account == "All" else st.session_state.selected_service_account
    )

    if not effective_username:
        st.warning("Select a service account in the sidebar or type a username filter to view query logs.")
    else:
        safe_username = escape_sql_literal(effective_username)

        password_logs_sql = f"""
        WITH password_sessions AS (
            SELECT DISTINCT
                s.session_id,
                s.user_name,
                s.authentication_method,
                s.client_application_id,
                s.client_application_version,
                s.client_environment
            FROM SNOWFLAKE.ACCOUNT_USAGE.SESSIONS s
            WHERE s.created_on >= DATEADD(day, -{lookback_days}, CURRENT_TIMESTAMP())
              AND UPPER(s.user_name) = UPPER('{safe_username}')
              AND UPPER(COALESCE(s.authentication_method, '')) LIKE '%PASSWORD%'
        )
        SELECT
            q.start_time AS "Query Start Time",
            q.query_id AS "Query ID",
            q.session_id AS "Session ID",
            q.user_name AS "Username",
            q.query_type AS "Query Type",
            q.query_tag AS "Query Tag",
            q.database_name AS "Database Name",
            q.schema_name AS "Schema Name",
            q.warehouse_name AS "Warehouse Name",
            q.role_name AS "Role Name",
            q.execution_status AS "Execution Status",
            ROUND(q.total_elapsed_time / 1000, 2) AS "Total Elapsed Seconds",
            ps.authentication_method AS "Authentication Method",
            ps.client_application_id AS "Client Application",
            ps.client_application_version AS "Client App Version",
            ps.client_environment AS "Client Environment",
            q.query_text AS "Query Text"
        FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY q
        JOIN password_sessions ps
          ON q.session_id = ps.session_id
        WHERE q.start_time >= DATEADD(day, -{lookback_days}, CURRENT_TIMESTAMP())
          AND UPPER(q.user_name) = UPPER('{safe_username}')
          AND q.query_text IS NOT NULL
          AND q.query_type IN ('SELECT', 'INSERT', 'UPDATE', 'DELETE', 'MERGE', 'COPY')
          AND q.query_text NOT ILIKE '%SYSTEM$%'
          AND q.query_text NOT ILIKE 'ALTER SESSION%'
          AND q.query_text NOT ILIKE 'SET %'
          AND q.query_text NOT ILIKE 'UNSET %'
          AND q.query_text NOT ILIKE 'USE %'
          AND q.query_text NOT ILIKE 'SHOW %'
          AND q.query_text NOT ILIKE 'DESCRIBE %'
          AND q.query_text NOT ILIKE 'SELECT CURRENT_%'
          AND q.query_text NOT ILIKE 'SELECT LAST_QUERY_ID(%'
        ORDER BY q.start_time DESC, q.query_id DESC
        """

        pwd_logs_df = session.sql(password_logs_sql).to_pandas()

        if pwd_logs_df.empty:
            st.info("No password-based login events found for the selected username in the selected window.")
        else:
            st.dataframe(pwd_logs_df, use_container_width=True, height=420)

            excel_bytes = build_excel_bytes(pwd_logs_df, sheet_name="Password Login Events")
            if excel_bytes:
                st.download_button(
                    label="Download Excel",
                    data=excel_bytes,
                    file_name=f"password_login_events_{effective_username}_{lookback_days}d.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )
            else:
                csv_bytes = pwd_logs_df.to_csv(index=False).encode("utf-8")
                st.download_button(
                    label="Download CSV",
                    data=csv_bytes,
                    file_name=f"password_login_events_{effective_username}_{lookback_days}d.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

with tab4:
    st.subheader("Authentication Methods Summary")
    st.info("Shows authentication methods observed in LOGIN_HISTORY for the selected lookback window.")

    if auth_methods_df.empty:
        st.warning("No authentication methods found for the selected window.")
    else:
        auth_summary = (
            auth_methods_df.groupby("FIRST_AUTH_FACTOR", as_index=False)["LOGIN_COUNT"]
            .sum()
            .sort_values("LOGIN_COUNT", ascending=False)
        )

        st.bar_chart(auth_summary.set_index("FIRST_AUTH_FACTOR")[["LOGIN_COUNT"]])

        st.dataframe(
            auth_methods_df.reset_index(drop=True),
            use_container_width=True,
            height=500,
        )

        st.subheader("Method totals")
        st.dataframe(
            auth_summary.rename(columns={"FIRST_AUTH_FACTOR": "Authentication Method"}),
            use_container_width=True,
            height=220,
        )

with tab5:
    st.subheader("Human User Authentication Tracking")
    st.info(
        "Critical Risk means the human account has password authentication enabled but is not enrolled in MFA. Password-Only Logins separately show whether successful password-only authentication was actually observed during the selected window."
    )

    if human_users_df.empty:
        st.warning("No human users found for the selected window.")
    else:
        total_humans = len(human_users_df)
        critical_risk_users = len(human_users_df[human_users_df["POLICY_STATUS"] == "Critical Risk"])
        compliant_users = total_humans - critical_risk_users

        c1, c2, c3 = st.columns(3)
        c1.metric("Human Users", total_humans)
        c2.metric("Critical Risk", critical_risk_users)
        c3.metric("Compliant", compliant_users)

        compliance_pct = round((compliant_users * 100 / total_humans), 1) if total_humans else 0.0
        st.metric("Compliance %", f"{compliance_pct}%")
        st.progress(int(compliance_pct))

        human_display_df = human_users_df.copy()
        human_display_df["POLICY_STATUS"] = human_display_df["POLICY_STATUS"].apply(human_policy_display)
        human_display_df["LAST_LOGIN"] = human_display_df["LAST_LOGIN"].apply(fmt_ts)
        human_display_df["LOGIN_COUNT"] = human_display_df["LOGIN_COUNT"].apply(fmt_count)

        human_display_df = human_display_df.rename(
            columns={
                "NAME": "Name",
                "LOGIN_NAME": "Login Name",
                "FIRST_AUTH_FACTOR": "First Auth Factor",
                "SECOND_AUTH_FACTOR": "Second Auth Factor",
                "LAST_LOGIN": "Last Login",
                "LOGIN_COUNT": "Login Count",
                "POLICY_STATUS": "Policy Status",
            }
        )

        st.dataframe(
            human_display_df.reset_index(drop=True),
            use_container_width=True,
            height=500,
        )

with tab6:
    st.subheader("Application Analysis")
    st.info("Shows client application and authentication-method combinations observed in SNOWFLAKE.ACCOUNT_USAGE.SESSIONS.")

    if applications_df.empty:
        st.warning("No application session data found for the selected window.")
    else:
        st.bar_chart(
            applications_df.groupby("CLIENT_APPLICATION_ID", as_index=False)["TOTAL_SESSIONS"]
            .sum()
            .set_index("CLIENT_APPLICATION_ID")
        )
        st.dataframe(applications_df, use_container_width=True, height=500)

with st.expander("How this is calculated"):
    st.write(
        "This report counts login events in SNOWFLAKE.ACCOUNT_USAGE.LOGIN_HISTORY for users whose "
        "TYPE is LEGACY_SERVICE. Password logins are counted when FIRST_AUTHENTICATION_FACTOR = 'PASSWORD'. "
        "The password log tab now shows raw password login events from LOGIN_HISTORY with a 500-row cap. "
        "Human user policy status is Critical Risk only when the latest login is PASSWORD, SECOND_AUTH_FACTOR = 'NONE', "
    )
 