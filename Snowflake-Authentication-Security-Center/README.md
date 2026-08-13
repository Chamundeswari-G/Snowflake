# ❄️ Snowflake Authentication Security Center

A focused **Streamlit in Snowflake** application for analyzing Snowflake authentication activity, with an emphasis on legacy service-account password usage, strong-authentication adoption, human-user authentication posture, password-session investigation, and application activity.

> **Development environment:** This project was built and tested in a personal Snowflake environment using personally configured integrations and service accounts. No employer or production company data is included.

---

## Why this project matters

Snowflake is rolling out stronger authentication requirements for both **human users** and **non-human service users**.

Snowflake's Phase 3 enforcement is being rolled out account-by-account from **August through October 2026**.
<img width="887" height="217" alt="image" src="https://github.com/user-attachments/assets/18416fae-a5c3-470c-9980-9129674472a4" />


The change affects the two identity types differently:

| Identity | Phase 3 requirement |
| --- | --- |
| 👤 **Human users** | New and existing human users authenticating with a password must use a second authentication factor. |
| ⚙️ **Service users** | Non-human users are blocked from password authentication. Existing `LEGACY_SERVICE` users are migrated to `SERVICE`. |

This creates an important operational challenge:

> **How do we know which legacy service accounts are still using passwords, which integrations are already using stronger authentication, and where migration work should be prioritized?**

That is the primary problem this project explores.

---

## Snowflake strong-authentication transition

### 👤 Human users — MFA with password authentication

When Phase 3 is enforced for an account, all new and existing human users authenticating with a password must use a **second authentication factor**, with no exceptions.

Conceptually:

```text
Human User
     │
     ├── Strong / federated authentication
     │
     └── Password authentication
                  │
                  ▼
          Second factor required
                  │
                  ▼
          Strong Authentication
```

The application includes a **Human Users** view to provide additional visibility into human-user authentication posture.

> **Implementation note:** The current application uses `HAS_PASSWORD` and `EXT_AUTHN_DUO` for its human-user policy classification. Because `EXT_AUTHN_DUO` is Duo-specific, the application's Human Users view should be treated as an authentication-posture indicator rather than a universal Snowflake MFA-compliance assessment.

---

### ⚙️ Service users — password authentication is going away

Phase 3 also removes password authentication for non-human users.

When enforcement reaches an account:

- Non-human users are blocked from password authentication.
- `LEGACY_SERVICE` is fully deprecated.
- Existing `TYPE = 'LEGACY_SERVICE'` users are migrated to `TYPE = 'SERVICE'`.
- `SERVICE` users cannot authenticate with passwords.

This creates the migration path:

```text
LEGACY_SERVICE
      │
      │
      ▼
Observe authentication activity
      │
      ├── Password authentication
      │          │
      │          ▼
      │    Migration required
      │
      └── Non-password authentication
                 │
                 ▼
         Migration progressing
                 │
                 ▼
              SERVICE
                 │
                 ▼
       Password authentication
           not supported
```

---

## What can service users use instead?

Moving away from passwords does **not** mean applications lose programmatic access to Snowflake.

Depending on the workload and integration, strong programmatic authentication options include:

| Authentication method | Typical use |
| --- | --- |
| 🔑 **Key-pair authentication** | Scripts, applications, connectors, ETL/ELT tools, and automated workloads |
| 🔐 **OAuth** | Token-based application authentication and supported integrations |
| ☁️ **Workload Identity Federation (WIF)** | Cloud workloads using AWS, Azure, GCP, Kubernetes/OIDC, or other supported workload identities |
| 🎟️ **Programmatic Access Tokens (PATs)** | Token-based programmatic authentication |

Snowflake authentication policies recognize `KEYPAIR`, `OAUTH`, `PROGRAMMATIC_ACCESS_TOKEN`, and `WORKLOAD_IDENTITY` as authentication methods.

Workload Identity Federation is particularly interesting for cloud workloads because it allows applications and services to authenticate using their native workload identity rather than maintaining long-lived Snowflake credentials.

---

# What problem does this application solve?

Snowflake provides rich authentication, user, session, and query metadata through `ACCOUNT_USAGE`.

However, answering authentication-migration questions often requires analyzing several views together.

This application brings those questions into one focused workflow:

- Which legacy service accounts are still using password authentication?
- How much observed authentication has moved to non-password methods?
- Which service accounts should be prioritized for migration?
- When was non-password authentication last observed?
- Which authentication methods are actually being observed?
- Which human users have password-enabled accounts without Duo enrollment?
- What password-authenticated query activity can be investigated for a selected service account?
- Which client applications are generating session activity?

The goal is to turn strong-authentication migration from a configuration exercise into an **observable authentication-adoption process**.

---

# Dashboard Preview

<img width="1850" height="922" alt="image" src="https://github.com/user-attachments/assets/d2004215-f7dc-4936-8265-90aedffcbe88" />


The overview provides an immediate view of:

- Legacy service-account count
- Total authentication activity
- Password authentication %
- Non-password authentication %
- Accounts showing non-password adoption
- Authentication activity by account
- Migration-risk distribution

> Screenshots shown in this repository come from a personal development environment and contain no employer or production company data.

---

# Application Flow

The dashboard is organized into six tabs:

| Tab | Purpose |
| --- | --- |
| **Overview** | High-level service-account authentication and migration metrics |
| **Accounts Detail** | Account-level migration status and recent authentication activity |
| **Password Query Logs** | Investigate queries associated with password-authenticated sessions |
| **Authentication Methods** | Summarize observed first- and second-factor combinations |
| **Human Users** | Review human-user authentication posture and recent activity |
| **Application Analysis** | Review client applications and authentication-method combinations |

---

# Architecture

The application reads Snowflake metadata using the active Snowpark session.

```text
                SNOWFLAKE.ACCOUNT_USAGE
                          │
        ┌─────────────────┼─────────────────┐
        │                 │                 │
      USERS         LOGIN_HISTORY        SESSIONS
        │                 │                 │
        │                 │                 │
        │          Authentication           │
        │             activity              │
        │                 │                 ▼
        │                 │           QUERY_HISTORY
        │                 │                 │
        └─────────────────┼─────────────────┘
                          │
                          ▼
                   Snowpark Session
                          │
                          ▼
                Streamlit in Snowflake
                          │
                          ▼
           Authentication Security Center
```

---

# Data Sources

The application uses:

- `SNOWFLAKE.ACCOUNT_USAGE.USERS`
- `SNOWFLAKE.ACCOUNT_USAGE.LOGIN_HISTORY`
- `SNOWFLAKE.ACCOUNT_USAGE.SESSIONS`
- `SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY`

The app is designed for **Streamlit in Snowflake** and uses:

```python
from snowflake.snowpark.context import get_active_session
```

rather than requiring a manually configured Snowflake connection.

---

# Key Calculations

## Legacy service-account migration

Legacy service accounts are selected from:

```text
SNOWFLAKE.ACCOUNT_USAGE.USERS
```

where:

```sql
TYPE = 'LEGACY_SERVICE'
```

and the account has not been deleted.

Authentication activity is then read from `LOGIN_HISTORY` for the selected lookback period.

The application classifies:

```text
FIRST_AUTHENTICATION_FACTOR = PASSWORD
```

as password authentication.

Any other observed first authentication factor is categorized as non-password authentication.

For each legacy service account, the application calculates:

- Total logins
- Password logins
- Non-password logins
- Password authentication %
- Non-password authentication %
- Last login
- Last non-password login
- Migration status

---

## Migration Status

The dashboard uses project-defined thresholds to make migration activity easier to prioritize:

| Status | Definition |
| --- | --- |
| 🔴 **Critical** | 50% or more observed authentication is password-based |
| 🟡 **Needs attention** | More than 0% but less than 50% is password-based |
| 🟢 **On track** | 0% password authentication observed |

> These classifications are defined by this project for prioritization. They are **not official Snowflake security classifications**.

---

# Human-user posture

Human users are selected from `ACCOUNT_USAGE.USERS` where the user:

- is a person or has a null type,
- has not been deleted,
- and is not disabled.

The current implementation evaluates human-user policy using:

- `HAS_PASSWORD`
- `EXT_AUTHN_DUO`
- latest observed authentication factors from `LOGIN_HISTORY`

The dashboard currently labels a user as **Critical Risk** when:

```text
HAS_PASSWORD = TRUE
AND
EXT_AUTHN_DUO = FALSE
```

Otherwise, the current implementation labels the account **Compliant**.

### Important distinction

Snowflake's Phase 3 requirement is broader than this project's current human-user policy check.

Snowflake requires human users who authenticate using passwords to use a second authentication factor.

The current dashboard specifically examines Duo configuration through `EXT_AUTHN_DUO`.

Therefore:

> **The Human Users tab represents an authentication-posture indicator and should not be interpreted as a complete MFA-compliance engine.**

---

# Password Query Investigation

Authentication statistics tell us **that** a password-authenticated session occurred.

Sometimes the next question is:

> **What activity occurred through that session?**

For a selected service account, the application identifies sessions whose:

```text
AUTHENTICATION_METHOD
```

contains:

```text
PASSWORD
```

and correlates those sessions with:

```text
SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
```

using:

```text
SESSION_ID
```

Conceptually:

```text
Password-authenticated session
              │
              ▼
          SESSION_ID
              │
              ▼
        QUERY_HISTORY
              │
              ▼
      Activity investigation
```

The investigation view can return:

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

Results can be exported to **Excel or CSV**.

> Query-log screenshots are intentionally excluded from the public repository.

---

# Authentication-method analysis

`LOGIN_HISTORY` is grouped by:

- First authentication factor
- Second authentication factor

The dashboard also displays:

- Login count
- Distinct user count
- Most recent login

This provides visibility into the actual authentication-factor combinations observed during the selected period.

---

# Application Analysis

`ACCOUNT_USAGE.SESSIONS` is grouped by:

- `CLIENT_APPLICATION_ID`
- `AUTHENTICATION_METHOD`

This provides a high-level view of which client applications are generating Snowflake sessions and the authentication methods associated with them.

---

# Filters

The sidebar allows the analysis to be adjusted using:

- **Lookback window:** 1–90 days
- **Successful logins only**
- **Minimum service-account login threshold**
- **Service account**

This allows users to move between an environment-level view and focused account investigation.

---

# Running in Streamlit in Snowflake

## 1. Create a Streamlit application

Create or open a Streamlit application in Snowflake.

## 2. Add the application code

Add the contents of:

```text
Snowflake_authentication_security_streamlit_app
```

to the application.

## 3. Verify permissions

Ensure the Streamlit execution role can access the required `SNOWFLAKE.ACCOUNT_USAGE` views.

## 4. Run the application

Launch the application.

## 5. Configure the analysis

Use the sidebar to select:

- Lookback period
- Successful-login filtering
- Minimum service-account login threshold
- Optional service-account filter

Because the application uses `get_active_session()`, no separate Snowflake connection configuration is required when running in Streamlit in Snowflake.

---

# Repository Structure

```text
snowflake-authentication-security-center/
│
├── Snowflake_authentication_security_streamlit_app
├── README.md
├── requirements.txt
│
└── screenshots/
    ├── 01-overview.png
    ├── 02-account-details.png
    ├── 03-authentication-methods.png
    ├── 04-human-users.png
    └── 05-application-analysis.png
```

Password-query-log screenshots are intentionally excluded.

---

# Security and Data Privacy

This repository contains application code, documentation, and selected demonstration screenshots.

The project was developed in a **personal Snowflake environment** using personally configured integrations and service accounts.

The repository does not contain:

- Employer data
- Production company data
- Passwords
- OAuth tokens
- Private keys
- Snowflake credentials
- Connection strings
- Production query logs

Users adopting this project should review their organization's security and data-governance requirements before exposing authentication or query-history information outside Snowflake.

---

# Project Scope

This project is intended as an **authentication observability and migration-readiness tool**.

It does not attempt to replace:

- Snowflake authentication policies
- Snowflake's Strong Authentication Hub
- Identity-provider controls
- SIEM/security-monitoring platforms
- Formal security compliance tooling

Instead, it provides a focused analytical view of **observed authentication behavior** and service-account migration progress.

---

# Built With

- ❄️ Snowflake
- 🐍 Snowpark Python
- 📊 Streamlit in Snowflake
- 🐼 pandas
- 🔐 Snowflake `ACCOUNT_USAGE`

---

# References

- [Snowflake — Planning for the deprecation of single-factor password sign-ins](https://docs.snowflake.com/en/user-guide/security-mfa-rollout)
- [Snowflake — User management and user types](https://docs.snowflake.com/en/user-guide/admin-user-management)
- [Snowflake — Workload Identity Federation](https://docs.snowflake.com/en/user-guide/workload-identity-federation)
- [Snowflake — Authentication policies](https://docs.snowflake.com/en/sql-reference/sql/create-authentication-policy)
- Snowflake `ACCOUNT_USAGE.LOGIN_HISTORY`
- Snowflake `ACCOUNT_USAGE.USERS`
- Snowflake `ACCOUNT_USAGE.SESSIONS`
- Snowflake `ACCOUNT_USAGE.QUERY_HISTORY`

---

# Repository Description

> Streamlit in Snowflake dashboard for monitoring legacy service-account password usage, strong-authentication migration readiness, authentication methods, human-user posture, and application activity.
