# Implementation verification

Checked on November 7, 2026, on Windows with Python 3.12.12 and Node 24.15.0.

- Backend: **55 tests passed** together. One dependency deprecation warning from Starlette's httpx TestClient adapter; no failed application tests. A sandbox-only rerun could not create its temporary directory; the same checks passed outside that restricted directory.
- Frontend: **Next.js production build and TypeScript checks passed** (Next 16.4.5).
- Frontend dependency audit after dependency cleanup: **0 reported vulnerabilities**.
- PowerShell launch/stop scripts: parsed successfully with PowerShell's language parser.
- Python modules: compilation check passed.
- Browser: authenticated entry page rendered correctly; missing model and warehouse configuration appeared as explicit blockers.
- Git integration test created a real temporary commit containing the exact proposed SQL and confirmed the original checkout stayed unchanged.
- Switch transport test used the documented event envelope, checked pongs while command work was blocked, and confirmed duplicate delivery did not repeat a domain command.

Provider test doubles are confined to automated tests. Subsequent credentialed checks below exercised the real model, warehouse and Switch server. A live GitHub pull request was not created; local verified-branch publication is exercised end to end.

The implementation delivers a verified repair branch and optional pull request. Production SQL deployment and subsequent production verification remain part of the user's existing warehouse deployment process.


## Live onboarding verification

Subsequent live checks on November 7, 2026 verified Google ADC, the OpenAI model identity, the real UCI transaction upload (541,909 records), both derived warehouse tables and all six reconciliation assertions. Seven additional reconciliation boundary cases passed on BigQuery. A real OpenAI investigation then executed SQL, read both transform files and submitted an evidence-backed no-repair conclusion for the cancellation reconciliation. The workflow now requires function calls on every model turn and rejects incomplete tool output; it does not accept free-form text as a verified conclusion.

The original failed investigation was retained under runtime/incident-reruns before retrying. The completed live case reconciles GBP 10,644,560.424 of non-cancellation invoice value plus GBP -896,812.49 of cancellations to GBP 9,747,747.934 of signed invoice value.

## Real repair path

Acceptance run `31df00cf57ef` created isolated BigQuery clones and a separate SQL repository, introduced a documented cancellation-filter fault there, and confirmed that independent daily reconciliation failed. The real OpenAI investigator proposed a correction to `models/retail_daily.sql`; the normal server verified the exact patch in BigQuery. Publication was rejected without both role approvals. Two explicitly automated acceptance identities then exercised the approval gates; they did not impersonate either human reviewer.

The normal publisher repeated verification and created a Git branch whose SQL blob matched the approved bytes exactly. The acceptance harness applied that branch only to its isolated daily table and all six contracts passed with the original totals restored. The main acceptance checkout remained unchanged. Baseline warehouse table versions stayed unchanged and acceptance datasets were cleaned. Full private evidence is in `runtime/acceptance/31df00cf57ef/result.json`.

Current contract checks run before each model investigation. A failed contract cannot be closed through `no_repair`; the agent must propose a justified fix or ask a concrete unresolved question. Evidence records retain executed SQL and BigQuery job IDs. Stable Google subjects, rather than display names, enforce independent approval.

## Real Switch transport

Repaired the missing Microsoft WSL runtime with a signed official installer; WSL 3.0.3 and Docker Engine 29.8.0 then started successfully. Started the official Switch **0.31.0** stack, registered the real project agent, created a private room and revoked its one-time registration key. The adapter connected to the real WebSocket service.

A human-origin status command traversed Switch, the adapter and the API. The API denied the unbound sender and the adapter delivered that denial back to the room. After a real Google login, the actual agent-protocol sender was bound to the verified finance membership and another real status command succeeded. The service identity resolved to the stable Google subject. Chat's internal UUID and the protocol sender are different identifiers; binding uses the complete sender reported by the adapter. No incident or approval was created by either transport test. Evidence is in `runtime/switch-connection-validation.json` and `runtime/switch-authenticated-validation.json`.

## Sign-in and hosting status

Google Web application client and both test-user entries were created in project `incident-room-514005`. The client ID is configured locally. The finance reviewer completed a real Google sign-in in Chrome; the backend persisted the verified Google identity and session. Old local reviewer token sign-in was then disabled. The session survives the app restart. Automated tests cover nonce replay, verification failure, uninvited users, revocation, CSRF, viewer restrictions, logout, Switch binding, and production refusal of local bearer tokens. Engineering is invited; that person signs in using their own Google account and binds their own Switch participant during onboarding.

Both versioned deployment images built successfully. A separate owned Docker project verified the dashboard-to-API proxy, unauthenticated rejection, six real BigQuery metric queries using mounted ADC, unprivileged API execution (UID 10001), and absence of an `.env` file in the image. An incident and its audit response survived an API container restart backed by PostgreSQL. The disposable test containers and volumes were removed afterward. Evidence is in `runtime/container-validation.json` (run `c3d2f22d074f`). Native workstation services and the real Switch stack remain running.

GCP billing was subsequently linked and deployment APIs enabled. Step 2 created `incident-room-server` in `us-central1-a` (e2-medium, Debian 12, 4 GB RAM, 30 GB persistent disk). A real IAP/OS Login SSH session verified bootstrap status `ready`, Docker Engine 29.9.3, Compose 5.7.0 and an active Docker daemon. The server has deletion protection, Shielded VM protections and a dedicated service account. Step 2 ended with only IAP SSH ingress; the subsequent public deployment is described below. The private deployment record is `runtime/gcp-server.json`.

## Hosted deployment and presentation project

Step 3 deployed the dashboard, Switch endpoint, Switch Console and Mattermost through four Cloud Run HTTPS services with private VPC access to the VM. The original incident, all 18 audit entries, memberships and verified Google identity migrated to PostgreSQL; browser sessions were excluded from transfer. The user then completed a fresh real Google sign-in at the hosted dashboard. An API restart preserved the incident, audit and new hosted session. Unauthenticated incident requests returned 401, while the production auth configuration disabled legacy bearer-token login.

The deployed VM identity passed actual OpenAI model access, BigQuery metadata/metric reads, Git identity and isolated rebuild checks against the baseline (six of six contracts). The original dataset grants read access only to this runtime identity. A real Console status command and a real Mattermost mention each traversed Switch, the deployed WebSocket adapter, verified Google membership and the API, then returned the expected room reply. These checks created no incident or approval. Evidence: `runtime/cloud-preflight.log` and `runtime/cloud-live-validation.json`.

The completed upstream setup seeder was excluded from ongoing startup because it attempted public account creation after public signup was disabled. The API, adapter, databases, Switch, Console and chat were healthy after correction. Systemd starts the persistent stack on boot.

Daily backups include both database dumps, the active SQL Git bundle and its project JSON. Uploads to a private Cloud Storage bucket passed size and checksum verification. An actual application backup was restored into a disposable database; incident and audit contents matched exactly and the temporary database was removed. The production database was not changed. Evidence: `runtime/cloud-backup-validation.json`. Full Switch restore has not been tested.

An isolated persistent presentation dataset, `incident-room-514005.incident_room_presentation`, was cloned from the real baseline. A separate SQL repository deliberately excludes cancellations in the daily transformation. This produces GBP 10,644,560.424 instead of the raw signed total GBP 9,747,747.934. The independent reconciliation contract fails; the other five contracts pass. The minimal correction was independently verified in disposable clones and all six contracts passed. The original tables' metadata etags remained unchanged. No human approvals or repair branch were fabricated. The presentation main branch and table retain the fault for a real investigation.

The running API was then switched to that presentation configuration and repository. Actual reads through the active API container confirmed the expected failing contract and incorrect daily total. Evidence: `runtime/presentation-evidence.json` and `runtime/presentation-active-validation.json`. The earlier no-repair incident remains historical evidence from the clean original project. Finance should open a new incident for the presentation project. Engineering Google sign-in and a real two-person approval/publication exercise remain pending; the user chose to arrange engineering onboarding later. See [PRESENTATION.md](PRESENTATION.md).
