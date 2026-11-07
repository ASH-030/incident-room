# Hosted Incident Room

Deployment checked November 7, 2026, in Google Cloud project `incident-room-514005`.

## Open the application

- Dashboard: https://incident-room-281482385461.us-central1.run.app
- Switch Console: https://incident-switch-admin-281482385461.us-central1.run.app
- Team chat: https://incident-chat-281482385461.us-central1.run.app
- Switch API: https://incident-switch-281482385461.us-central1.run.app

The dashboard uses Google sign-in. Finance is `finance@example.com`; engineering is `engineering@example.com`. Each person must sign in with their own account. Finance has completed hosted sign-in. Engineering onboarding is pending. Both Google accounts are invited and both Console and Mattermost participants are bound to those memberships; a binding grants no access until the corresponding Google identity is verified.

Switch Console and Mattermost use their own account passwords. The operator's private handover is `D:\SwitchHackathon\private\gcp\reviewer-access.json`. Do not include that file, `.env` files, database backups, private runtime evidence, or SSH keys in a submission or public repository. The app's Google sign-in does not require pasting a token.

## What the deployment runs

Four Cloud Run services provide Google-managed HTTPS addresses. The dashboard proxies its API calls over a dedicated private VPC subnet to a single Linux VM. Three Nginx edge services proxy Switch, its Console and Mattermost. WebSockets are supported by the proxies. The VM runs the application API, one Switch adapter, PostgreSQL and the pinned official Switch 0.31.0 stack. Cloud Run scale-to-zero can cause a cold start; durable state and agent connections stay on the VM.

The VM has no public application or database ingress. Its backend firewall accepts only the Cloud Run subnet. Operator SSH uses IAP and OS Login. The runtime service account reads the original `incident_data` dataset, runs query jobs and creates isolated validation datasets. API/tool policy further restricts queries to the active project allowlist. The Cloud Run identities have no BigQuery or secret permissions.

OpenAI and Switch credentials live in Secret Manager; the VM retrieves them with its own short-lived identity. No workstation ADC file is copied to the server. Production sessions are Secure and HttpOnly; CSRF/origin checks protect mutations, and local reviewer bearer tokens are disabled. The public URLs expose sign-in pages; unauthenticated incident requests return 401.

`incident-room.service` starts persistent services on boot. The completed Switch setup seeder is excluded from routine startup: the upstream 0.31.0 seeder retries user creation and fails after public signup is correctly disabled. The API restarts automatically. The adapter deliberately stops on uncertain delivery/history gaps; inspect its state instead of blindly replaying commands.

## Presentation workflow

See [PRESENTATION.md](PRESENTATION.md). The presentation uses real retail records in a separate, explicitly labelled BigQuery dataset and a separate SQL Git repository. The initial daily transform contains one documented cancellation-filter error. Diagnoses and proposed patches are generated from actual queries by OpenAI; reviewers and approvals are real people. The original warehouse remains unchanged.

The previous evidence-backed no-repair incident remains in history. It investigated the original clean warehouse before the presentation project was selected. Open a new incident for the controlled fault; do not reuse or alter that earlier evidence.

## Backups and recovery

The daily systemd backup timer runs around 03:00 UTC. It produces an application PostgreSQL custom-format dump, a Switch/Mattermost cluster SQL dump, a Git bundle for the active SQL repository and the matching project JSON under `/srv/incident-room/backups`, readable only by root. Copies are uploaded to private bucket `gs://incident-room-514005-private-backups` with server-verified MD5 and size checks. Public access prevention and uniform bucket access are enabled. The VM can create objects in this bucket but cannot read, overwrite or delete them. Bucket lifecycle removes objects after 14 days, subject to the bucket's soft-delete policy. Local backups are retained; monitor disk space and manage their retention as part of operation.

The application dump is restore-tested against a disposable database and incident/audit contents are compared. Switch backups are checked for archive integrity; full Switch disaster recovery has not been exercised. A single VM is still a single availability point; this is not a multi-region service.

To recover, stop API/adapter activity, retrieve a chosen backup using an authorized operator account, restore PostgreSQL with the matching major versions (application 17, Switch 16), restore the SQL Git bundle, restore the active project configuration and fetch secrets using the VM identity. Start the stack and inspect interrupted incidents and Switch cursors before resuming work. Do not replay approvals or change cursor records without determining which operations committed.

## Validation and limits

Hosted finance login, anonymous incident denial, service health, real OpenAI access, BigQuery metadata and metric queries, baseline isolated rebuild (six contracts), Console and Mattermost status round trips, and incident/audit/session persistence across an API restart were checked. Detailed evidence is in the private application `runtime` directory and [VALIDATION.md](VALIDATION.md).

Two actual human approvals and engineering branch publication remain a reviewer exercise. Automated acceptance previously tested the full gate and exact-branch behavior in an isolated environment; those identities did not impersonate the human reviewers. GitHub is not connected, so publication creates a verified Git branch on the server, not a GitHub PR. The app does not deploy SQL to the original warehouse. A verified branch is the handoff to a normal warehouse deployment process.

For upload implementation details, see Google's [resumable upload documentation](https://docs.cloud.google.com/storage/docs/performing-resumable-uploads).
