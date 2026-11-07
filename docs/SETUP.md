# Your setup steps

Project folder: `D:\SwitchHackathon\src\incident-room`.

The application implements BigQuery + OpenAI. You need a real warehouse dataset and its SQL repository; there is no generated demonstration data. Keep all keys on your computer. Do not paste them into chat.

## 1. Connect Google Cloud

1. Select or create your Google Cloud project, enable billing and the BigQuery API, and have actual source/output tables available.
2. Install the [Google Cloud CLI for Windows](https://docs.cloud.google.com/sdk/docs/install-sdk), then open a new PowerShell window.
3. Authenticate the Python client with Application Default Credentials:

```powershell
gcloud init
gcloud auth application-default login
gcloud auth application-default set-quota-project YOUR_VALIDATION_PROJECT_ID
```

The second command opens Google's browser login. A normal `gcloud auth login` alone does not configure the application's ADC. Alternatively, configure a workload/service-account credential using Google's supported ADC mechanism; do not copy its contents into the project.

Give the application's Google identity:

- BigQuery Data Viewer on the exact source/output tables or datasets it must investigate.
- BigQuery Job User on the project that runs and bills validation jobs.
- Permission to create datasets (`bigquery.datasets.create`) in the validation project, and to create/update/delete tables and delete the generated validation datasets. A dataset creator normally receives ownership of the new dataset. Ask your administrator to scope these permissions appropriately. Avoid granting this identity write access to source datasets.

Clones must use a compatible location and organization. All configured tables need to be materialized, cloneable TABLE assets. Materialize views and obtain stable snapshots for streaming inputs before using them here. Row/column policies and organization policies can impose additional access requirements; the live preflight will expose permission failures.

References: [ADC setup](https://docs.cloud.google.com/docs/authentication/set-up-adc-local-dev-environment), [creating datasets](https://docs.cloud.google.com/bigquery/docs/datasets), [clone requirements](https://docs.cloud.google.com/bigquery/docs/table-clones-create).

## 2. Describe your real SQL project

Your SQL needs to be in an existing, clean Git repository. Each configured transform is a standalone GoogleSQL SELECT with a known output table. It must run without dbt/Jinja rendering. Configure all inputs and intermediate/output tables used by the rebuild, ordered from upstream to downstream.

```powershell
cd D:\SwitchHackathon\src\incident-room
uv sync --frozen
Copy-Item config\bigquery.project.example.json config\project.local.json
notepad config\project.local.json
```

Replace every placeholder:

| Field | Your value |
| --- | --- |
| `billing_project` | Project that runs jobs and owns temporary validation datasets |
| `location` | Location shared by the configured tables, such as US or your actual region |
| `project_root` | Absolute path to the real SQL Git checkout; forward slashes work on Windows |
| `tables` | Explicit `project.dataset.table` allowlist, including outputs |
| `transforms` | SQL file paths relative to that checkout, in dependency order |
| `outputs` | Each transform file mapped to its actual output table |
| `assertions` | Named SELECT queries returning violating rows; **zero rows means pass** |
| `metrics` | Named SELECTs returning one numeric scalar; optional minimum/maximum bounds |
| `maximum_bytes_billed` | Your per-query ceiling; default is 1,000,000,000 bytes |
| `datahub_urns` | Optional authoritative DataHub dataset URNs; leave empty if unused |

An assertion should check an independently known business contract: uniqueness, reconciliation, completeness, or valid units. A query that always returns no rows provides no useful protection. The agent cannot redefine your assertions to make its own repair pass. Assertions and metric SQL use the original fully qualified names; the adapter redirects them to the generated scratch tables during verification.

Configure Git author identity in **the SQL repository**, if not already set:

```powershell
git -C D:/path/to/your-sql-repository config user.name "Your Name"
git -C D:/path/to/your-sql-repository config user.email "your-email@example.com"
```

For optional PR creation, set `publish_pr` to true, install/authenticate GitHub CLI, configure the repository's origin, and ensure you can push branches. Leave it false to create a local verified branch only. Deployment through your normal SQL pipeline follows PR review/merge.

## 3. Configure OpenAI and reviewers locally

```powershell
uv run python -m incident_room.configure
```

The helper asks for your OpenAI API key without echoing it, a model ID available to your OpenAI project that supports **Responses API function calling**, the absolute path to `config/project.local.json`, and two distinct reviewer names. It creates:

- `.env`: local OpenAI and application configuration, ignored by Git.
- `runtime/reviewer-credentials.json`: each reviewer's sign-in token, ignored by Git.

Those tokens are a local operator fallback. For normal reviewer sign-in, complete [Google sign-in and membership setup](GOOGLE-SIGN-IN.md), invite the two real accounts and retire the fallback after verifying login. There is no role-switching shortcut in the UI. Model keys stay on the server; allowed warehouse values used as evidence are sent to OpenAI. Review data authorization before allowing sensitive columns.

If using DataHub, set `DATAHUB_GMS_URL` and, when required, `DATAHUB_TOKEN` in `.env`, plus dataset URNs in the project JSON. Configured metadata failures stop the investigation instead of silently dropping its contracts.

## 4. Check and start the application

```powershell
uv run python -m incident_room.preflight
```

This checks reviewer configuration, real OpenAI model access, ADC, BigQuery schema/metrics, and Git identity. The optional command below also creates a temporary BigQuery dataset, rebuilds your current SQL, checks your contracts and cleans up. It runs billable warehouse jobs:

```powershell
uv run python -m incident_room.preflight --validate
```

Existing faulty SQL can fail the assertions; that is useful evidence rather than a reason to relax the contract. Resolve configuration/permission failures before opening an investigation.

Start the dashboard and API:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start-local.ps1
```

Open http://localhost:3000 and sign in with your invited Google account. Logs are in `runtime`. Keep a single API worker. The launch script starts the adapter automatically when its connection is configured. Stop the owned processes with:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\stop-local.ps1
```

The local state database is `runtime/room-live.db`. Back it up along with your configuration and repair branches. PostgreSQL and the complete API/web/adapter stack are supplied in `compose.yaml`; see [deployment and database transfer](DEPLOYMENT.md). Switch's server stack is separate.

## 5. Install and configure Switch

`docker version` must show a working Server as well as Client. On this workstation the missing WSL runtime was repaired and the official Switch 0.31.0 stack now runs from `D:\SwitchHackathon\deploy\switch`. Gateway is on port 3001 and messaging on 8065. Private operator credentials are in that stack's ignored `operator-credentials.json`.

1. Install [Switch Console for Windows](https://docs.switchagents.ai/switch-rooms/getting-started/install-switch-console).
2. Follow [Add a server](https://docs.switchagents.ai/switch-rooms/getting-started/add-a-server) to create a local full-stack server. Let Console choose the ports. Save the server address and sign-in details it provides.
3. Open the server's Gateway, create a room for the investigation, add the two reviewers, and copy the room ID.
4. On the Gateway API Keys page, create a key of type **registration**. This is used once; it is different from the agent key.
5. Run:

```powershell
uv run python -m incident_room.register_switch
```

Supply the Switch server/bridge base URL, a unique agent name, and the registration key. The helper registers our custom adapter and saves the returned agent identity locally. Do not register it again on every launch. A successful registration does not yet grant room membership or permission to answer both reviewers.

6. Invite this agent to the room. In its Switch settings, allow the intended reviewers to address it (new agents initially answer their owner). During identity binding you may permit room participants to address it; the app's own allowlist still rejects unassigned senders.
7. Set `SWITCH_ROOM_ID` in `.env`, then start the adapter:

```powershell
uv run python -m incident_room.switch_adapter
```

8. Each reviewer signs in with Google in the dashboard once, then mentions the agent with `!status` in the room. Until bound, it replies with the opaque Switch participant ID. Copy the **whole** ID, including the server suffix, and bind it to the invited Google account:

```powershell
uv run python -m incident_room.manage_users bind-switch "OPAQUE_FINANCE_PARTICIPANT_ID" FINANCE_GOOGLE_EMAIL
uv run python -m incident_room.manage_users bind-switch "OPAQUE_ENGINEERING_PARTICIPANT_ID" ENGINEERING_GOOGLE_EMAIL
```

Set a random private `SWITCH_ADAPTER_TOKEN` (generated by `scripts/prepare-containers.py`) for service authentication. Bindings are read from persistent membership by the API; they do not require per-reviewer tokens or adapter restarts. A sender cannot claim a role through their display name. Do not onboard this custom adapter as a Console-managed provider: it uses its own documented WebSocket connection. Your OpenAI key powers this application; Switch's built-in coding-agent provider configuration is separate.

Reference: [Switch custom agent protocol](https://docs.switchagents.ai/switch-rooms/internals/agent-protocol).

## 6. Run an actual investigation

Mention the agent when using room commands. The dashboard shows the same incidents:

| Command | Who / effect |
| --- | --- |
| `!open <concrete report>` | Either reviewer; open the incident in this room |
| `!definition <metric meaning, window and exclusions>` | Finance confirms the business contract |
| `!context <fact or answer>` | Either reviewer; invalidates earlier investigation/approvals |
| `!evidence` | Starts the OpenAI investigation and isolated patch testing |
| `!status` | Retrieves progress, questions, evidence-backed conclusion and full proposal digest |
| `!approve <full digest>` | Each reviewer approves the exact tested proposal independently |
| `!repair` | Engineering revalidates and creates the verified repair branch |

The agent may ask for clarification or conclude no repair is warranted. Failed validation produces no approvable patch. Inspect the proposal, SQL evidence and assertions before approving. The final artifact is a source-code branch/optional PR; deploy it through your normal warehouse pipeline and independently check production after deployment.

## Recovery

- After changing `.env`, restart API/adapter processes; tokens are not stored in browser local storage.
- On a source/context change, rerun investigation and obtain fresh approvals.
- On a process restart, inspect interrupted incidents before restarting a job. No uncertain mutation is replayed automatically.
- On a Switch gap/takeover/refusal, stop and inspect the server and audit history. The adapter persists cursor and event records in the state database. Do not delete them merely to force a replay. If a domain event is marked processing, determine whether its operation committed before reconciling that record.
- Validation datasets use the `incident_room_` prefix. Normally they are deleted; tables also have a one-hour expiration fallback. A cleanup/permission failure is surfaced as an error. An empty dataset can remain after a crash; inspect and remove the specific abandoned dataset in Google Cloud.
- If branch creation succeeded but a later step failed, inspect `incident-room/<incident-id>` and its commit before retrying. The application stops rather than overwriting an existing branch or claiming production was repaired.

The current installation has completed credentialed BigQuery, OpenAI and Switch checks. See [VALIDATION.md](VALIDATION.md) for the evidence and [HOSTED.md](HOSTED.md) for deployment access and remaining reviewer onboarding.
