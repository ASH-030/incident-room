# Google sign-in and reviewer administration

Create a Google Auth Platform Web application client. Allow the exact dashboard origins (scheme, hostname and port). Local defaults are `http://localhost:3000` and `http://127.0.0.1:3000`. For a hosted installation add its HTTPS hostname. The application uses Google Identity Services and verifies Google ID tokens on the backend. It needs the public Client ID; it does not use a client secret or request access to a reviewer's BigQuery project.

In Testing mode add the two reviewers as test users. Enter one email at a time and press Enter to make each a separate entry. Save the public ID locally:

```powershell
uv run python scripts/configure-google.py
uv run python -m incident_room.manage_users invite FINANCE_EMAIL finance
uv run python -m incident_room.manage_users invite ENGINEERING_EMAIL engineering
```

Restart the API and dashboard, then sign in with an invited Google account. Roles come from the operator's persistent membership table. A login cannot select its own role. Google `sub`, rather than display name, identifies the person for independent approval. Server sessions expire after eight hours. Membership changes and revocations end existing sessions. Browser writes require an allowed Origin and the session CSRF token.

After verifying a real Google login, set `ALLOW_REVIEWER_TOKENS=false` and restart to retire local operator tokens. Production always disables them, requires `GOOGLE_CLIENT_ID`, a persistent `DATABASE_URL`, and explicit HTTPS `APP_ORIGINS`.

## Link Switch participants

Use the complete opaque sender returned in the adapter's denial message. Never infer authority from a Switch display name. The corresponding invited Google account must sign in to the dashboard once before using Switch commands.

```powershell
uv run python -m incident_room.manage_users bind-switch OPAQUE_SENDER GOOGLE_EMAIL
uv run python -m incident_room.manage_users revoke GOOGLE_EMAIL
```

`SWITCH_ADAPTER_TOKEN` authenticates the adapter as a service. The API resolves its `X-Switch-Sender` header through the operator's binding table and the current membership. The adapter cannot supply a role or choose a Google subject. Keep its service key and `.env` private.
