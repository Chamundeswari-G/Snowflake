# Architecture

## High-level flow

```text
                         Snowflake ACCOUNT_USAGE
                                  |
        ----------------------------------------------------------
        |                         |               |               |
       USERS                 LOGIN_HISTORY      SESSIONS     QUERY_HISTORY
        |                         |               |               |
        |                         |               |               |
        +------------+------------+---------------+---------------+
                     |
                     v
              Streamlit / Snowpark
                     |
          +----------+----------+
          |                     |
          v                     v
 Service Account Analysis   Human User Analysis
          |                     |
          v                     v
 Migration / Adoption       Authentication Posture
          |                     |
          +----------+----------+
                     |
                     v
                Streamlit UI
```

## Query relationships

### Service-account analysis

`USERS` identifies legacy service accounts.

`LOGIN_HISTORY` supplies authentication events and factors.

The application calculates password versus non-password authentication share for each account.

### Authentication-method analysis

`LOGIN_HISTORY` is grouped by first and second authentication factor to show the authentication methods actually observed in the selected period.

### Human-user analysis

`USERS` provides human-user account configuration.

`LOGIN_HISTORY` supplies recent authentication activity, factors, and timestamps for the user-level view.

### Password-query investigation

`SESSIONS` identifies password-authenticated sessions for a selected username.

`QUERY_HISTORY` is joined through `SESSION_ID` to provide query-level investigation detail.

### Application analysis

`SESSIONS` provides client application and authentication-method combinations.

## Main Python components

- `get_active_session()` connects the Streamlit app to Snowflake.
- Formatting helpers standardize counts, percentages, and timestamps.
- SQL strings perform the account-usage analysis.
- Pandas converts Snowflake query results into Streamlit-ready tables.
- `st.tabs()` organizes the security workflow into focused investigation areas.
- `BytesIO` + `pandas.ExcelWriter` support Excel export from the password-query investigation tab.
