# Snowflake Authentication Security Center

A focused Streamlit application for analyzing Snowflake authentication activity, with an emphasis on legacy service-account password usage, authentication-method adoption, human-user authentication posture, and application activity.

## What problem does this solve?

In a Snowflake environment, authentication data can answer important operational questions, but the raw account-usage views are not always easy to consume as a single security-focused workflow.

This application brings several related questions into one focused dashboard:

- Which legacy service accounts are still using password authentication?
- How much authentication has moved to non-password methods?
- Which authentication methods are being observed?
- Which human users have a password-enabled account without Duo enrollment?
- What password-authenticated query activity can be investigated for a selected service account?
- Which client applications are generating session activity?

## Application flow

The dashboard is organized into six tabs:

| Tab | Purpose |
| --- | --- |
| **Overview** | High-level service-account authentication and migration metrics |
| **Accounts Detail** | Account-level migration status and recent authentication activity |
| **Password Query Logs** | Investigate queries associated with password-authenticated sessions |
| **Authentication Methods** | Summarize observed first- and second-factor combinations |
| **Human Users** | Review human-user authentication posture and recent activity |
| **Application Analysis** | Review client applications and authentication-method combinations |

## Data sources

The application reads Snowflake account-usage data using the active Snowpark session:

- `SNOWFLAKE.ACCOUNT_USAGE.USERS`
- `SNOWFLAKE.ACCOUNT_USAGE.LOGIN_HISTORY`
- `SNOWFLAKE.ACCOUNT_USAGE.SESSIONS`
- `SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY`

The app is designed for Streamlit in Snowflake and uses `get_active_session()` rather than requiring a manually created connection.

## Key calculations

### Legacy service-account migration

Legacy service accounts are selected from `ACCOUNT_USAGE.USERS` where `TYPE = 'LEGACY_SERVICE'` and the account has not been deleted.

Authentication activity is read from `LOGIN_HISTORY` for the selected lookback period.

- `PASSWORD` first authentication factor = password authentication
- Any other first authentication factor = non-password authentication

Migration status is calculated from password-authentication share:

- **Critical**: 50% or more password authentication
- **Needs attention**: greater than 0% but less than 50% password authentication
- **On track**: 0% password authentication observed

### Human-user posture

Human users are selected from `ACCOUNT_USAGE.USERS` where the user is a person (or has a null type), is not deleted, and is not disabled.

The current implementation evaluates human-user policy using:

- `HAS_PASSWORD`
- `EXT_AUTHN_DUO`
- latest observed authentication factors from `LOGIN_HISTORY`

The dashboard labels a user as **Critical Risk** when `HAS_PASSWORD = TRUE` and `EXT_AUTHN_DUO = FALSE`; otherwise the current code labels the user **Compliant**.

> Note: this is intentionally documented according to the current code. `EXT_AUTHN_DUO` is a Duo-specific configuration field, so this logic should not be described as universal MFA enrollment unless the implementation is later changed to use a general MFA field.

### Password query investigation

For a selected service account, the app identifies sessions whose `AUTHENTICATION_METHOD` contains `PASSWORD`, then joins those sessions to `QUERY_HISTORY` using `SESSION_ID`.

The investigation view returns items such as:

- Query start time
- Query ID
- Session ID
- Username
- Query type
- Query tag
- Database and schema
- Warehouse
- Role
- Execution status
- Elapsed time
- Authentication method
- Client application
- Client environment
- Query text

Users can export the displayed results to Excel or CSV.

### Authentication-method analysis

`LOGIN_HISTORY` is grouped by:

- first authentication factor
- second authentication factor

The dashboard also shows login count, distinct user count, and most recent login.

### Application analysis

`ACCOUNT_USAGE.SESSIONS` is grouped by:

- `CLIENT_APPLICATION_ID`
- `AUTHENTICATION_METHOD`

This provides a high-level view of which client applications are generating session activity.

## Running in Streamlit in Snowflake

1. Create or open a Streamlit app in Snowflake.
2. Add the contents of `streamlit_app.py`.
3. Ensure the execution role can read the required `ACCOUNT_USAGE` views.
4. Run the app.
5. Use the sidebar to select the lookback window, successful-login filter, minimum service-account login threshold, and optional service-account filter.

## GitHub project structure

```text
snowflake-authentication-security-center/
├── Snowflake_authentication_security_streamlit_app
├── README.md
├── requirements.txt
├── screenshots/
    ├── 01-overview.png
    ├── 02-account-details.png
    ├── 03-password-query-logs.png
    ├── 04-authentication-methods.png
    ├── 05-human-users.png
    ├── 06-application-analysis.png
```

## Suggested repository description

> Focused Streamlit dashboard for Snowflake authentication posture, legacy service-account password adoption, authentication methods, human-user risk, query investigation, and application activity.

## Security / privacy note

Do not publish production account names, usernames, query text, exported audit data, screenshots containing sensitive identifiers, or credentials in the public repository.

This project is intended as an example analytics and security-monitoring workflow. Adapt permissions, data scope, classification logic, and retention practices to your organization's security requirements.
