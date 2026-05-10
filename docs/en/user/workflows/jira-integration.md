# Jira integration

The `→ Jira` button on the ideas page creates a Jira Task in one click. To make it work, you need to configure credentials.

## Contents

- [What it is and why](#what-it-is-and-why)
- [Step 1. Get an API token](#step-1-get-an-api-token)
- [Step 2. Get accountId](#step-2-get-accountid)
- [Step 3. Configure DC](#step-3-configure-dc)
- [Step 4. Test](#step-4-test)
- [Best practice: env var](#best-practice-env-var)
- [Per-project override](#per-project-override)
- [Troubleshooting](#troubleshooting)

## What it is and why

If you have Jira (cloud version — atlassian.net) and you use it for tracking — DC can create Tasks from product ideas automatically.

Workflow:
1. The weekly product_ideas_scanner (or you yourself) drops an md file with an idea into `product_ideas_dir`.
2. On `/p/{slug}/ideas` you see the idea with an empty `jira` column.
3. You click `→ Jira`.
4. DC creates a Task in Jira with title and body from the md file, writes `jira_ticket: PROJ-1234` into the frontmatter, and the UI column shows the ticket id.

No manual copy-paste from markdown into the Jira form.

## Step 1. Get an API token

An API token is a long-lived credential Atlassian issues for programmatic access without a password.

1. Open https://id.atlassian.com/manage-profile/security/api-tokens
2. Sign in to your Atlassian account (the same one you use in Jira).
3. Click "Create API token".
4. Give it a label, e.g. `dc-dreaming-center`. Click Create.
5. Copy the token. **It is shown only once** — save it in a safe place (password manager).

The token looks roughly like `ATATT3xFfGF0...` — a long alphanumeric string.

## Step 2. Get accountId

So Jira knows whom to assign the created ticket to, you need your `accountId`.

Method 1 — via API:
1. Open in browser: `https://yourcompany.atlassian.net/rest/api/3/myself` (replace `yourcompany` with your sub-domain).
2. If not signed in — sign in.
3. You'll see JSON. Find the `accountId` field (e.g. `5b10ac8d82e05b22cc7d4ef5`).

Method 2 — via Jira UI:
1. Open your Jira profile (click on your avatar → Profile).
2. The URL contains accountId: `/people/<accountId>`.

## Step 3. Configure DC

Open `/settings` (for global config) or `/p/{slug}/settings` (for per-project).

The "Jira" group has the keys:
- `jira_base_url` — your Jira URL: `https://yourcompany.atlassian.net`. No trailing slash. **Required.**
- `jira_email` — your email in Atlassian. **Required.**
- `jira_api_token` — token from step 1. **Required.** Password input (stored hidden).
- `jira_user_account_id` — accountId from step 2. **Required.**
- `jira_project_key` — Jira project key (e.g. `PROJ`, `MYAPP`). **Required.**
- `jira_issuetype` — issue type. Default `Task`. Can be `Story`, `Bug` if needed.

Fill in all the required ones. Save.

## Step 4. Test

1. Create a test idea: drop an md file into `product_ideas_dir`:
   ```
   ---
   id: TEST-001
   title: "Test Jira integration"
   status: backlog
   priority: low
   module: test
   jira_ticket: ""
   ---

   # Test idea

   This is a test to verify DC → Jira integration.

   ## Acceptance criteria
   - Click → Jira button on ideas page.
   - Verify ticket created in Jira.
   - Verify md frontmatter updated with jira_ticket.
   ```

2. Open `/p/{slug}/ideas`. Find this entry.
3. In the `jira` column there's a `→ Jira` button. Click.
4. After 1–3 seconds the page reloads. The column now shows a ticket id, e.g. `PROJ-1234`.
5. Open Jira — there must be a ticket with your title and description.
6. Open the md file — frontmatter is updated: `jira_ticket: PROJ-1234`.

If all is well — integration works.

## Best practice: env var

Storing `jira_api_token` in `config.yaml` or `project_settings` in the DB is unsafe. If the repo/DB backup leaks — the token is in plaintext.

The better approach — env var. Pydantic-settings reads env vars with the `DC_` prefix:

```
$env:DC_JIRA_API_TOKEN = "ATATT3xFfGF0..."   # PowerShell session-level
```

Or in a systemd unit / Windows service config:
```
Environment="DC_JIRA_API_TOKEN=ATATT3xFfGF0..."
```

If the env var is set — it overrides the value in `config.yaml` (env > yaml priority in pydantic-settings).

In the UI the `jira_api_token` field will stay empty (because it's not in config.yaml), but DC will actually use the env value. To confirm — look at the logs or a dev shell:
```python
from dreaming.config import AppSettings
print(AppSettings.load().jira_api_token)
```

## Per-project override

If you have several Jira projects (each DC project → its own Jira project), use per-project override.

Globally set the shared creds (`jira_base_url`, `jira_email`, `jira_api_token`, `jira_user_account_id`).

Per-project on `/p/{slug}/settings` override only `jira_project_key`:
- Project A: `jira_project_key = APP1`.
- Project B: `jira_project_key = APP2`.

When you click `→ Jira` on the ideas of Project A — the ticket goes into `APP1`. On Project B — into `APP2`.

## Troubleshooting

**`401 Unauthorized` after clicking → Jira:**
- The token expired (Jira invalidates after inactivity).
- Email doesn't match the one the token was issued under.
- Get a new token, update.

**`403 Forbidden`:**
- `jira_user_account_id` lacks the permission to create issues in `jira_project_key`.
- Check in Jira: open the project → Settings → People → make sure you have a role with Create Issues.

**`404 Not Found`:**
- `jira_project_key` is wrong. Open Jira, check the project key (usually UPPERCASE abbreviation).

**`400 Bad Request`:**
- `jira_issuetype` does not exist in the project. Check in Jira: Settings → Issue types. Often `Story` or `Task` exists, but it can be customised.

**Ticket is created but the frontmatter is not updated:**
- File system permissions issue — DC can't write to the md file.
- Check permissions on `product_ideas_dir`.

**No ticket id appears in the UI after the click:**
- The POST returned an error — open Network tab in DevTools, look at the response.
- Or uvicorn logs — there will be a stack trace.

---

See also:
- [`../features/ideas.md`](../features/ideas.md) — ideas page.
- [`../features/settings.md`](../features/settings.md) — where the Jira keys live.
- Technical: [`../../services.md#jira`](../../services.md), [`../../api.md`](../../api.md).
