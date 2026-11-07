# Deploy the complete application

The container stack runs PostgreSQL, the FastAPI investigator, the Next.js dashboard and an optional Switch adapter. Source SQL and application state are mounted persistently. One API worker and one adapter are supported. The official Switch server is a separate version-pinned stack; its PostgreSQL, Mattermost and Gateway are independent from the application's database.

## Prepare

Complete the real project configuration and Google sign-in first. Run `uv run python scripts/prepare-containers.py`. It writes `config/project.container.json` with Linux repository paths and stores random database and adapter secrets in `.env`. Keep `.env`, runtime, the local project JSON, database transfers and ADC credentials out of source control and source archives.

The API runs as UID 10001. On Linux, give that UID write access to `runtime` and the SQL Git repository. Configure Git author identity in the mounted SQL repository. After copying a trusted repository from another machine, configure that exact repository as safe for the container user if Git reports different ownership; do not enable wildcard trust.

## Local Docker

Windows native launch remains available through `scripts/start-local.ps1`. Stop native services before using port 3000 from Docker. Set `GOOGLE_ADC_PATH` to your local Application Default Credentials JSON, then run:

```powershell
docker compose -f compose.yaml -f compose.credentials.yaml up -d --build
```

To test alongside the native dashboard, set `ROOM_WEB_PORT=3002`; Google sign-in on that port additionally needs the origin authorized in Google and `APP_ORIGINS`. The production frontend build proxies `/api` to the API container. Database and API ports stay inside the Compose network; the dashboard binds to loopback.

When the adapter is in Docker and Switch is on the host, its `SWITCH_BASE_URL` must use `http://host.docker.internal:8000`. Native Windows uses `http://127.0.0.1:8000`. Run `docker compose --profile switch up -d adapter` after binding the actual Switch senders. An uncertain event or history gap stops the adapter for reconciliation; it does not automatically replay approvals.

## Preserve incident history when changing databases

Stop the investigator and adapter during transfer. Export from the installation whose `DATABASE_URL` points to the source:

```powershell
uv run python -m incident_room.database_transfer export runtime/history-transfer.json
```

On the destination, set `DATABASE_URL` to the empty PostgreSQL database, then run the same command with `import`. The transfer preserves incident versions, evidence, immutable audit rows, memberships, Google identities, Switch bindings and delivery cursors. It refuses a nonempty target. It does not move browser sessions or sign-in challenges; users sign in again. Transfer files are private backups, not submission artifacts. Back up PostgreSQL and the SQL repository before upgrades.

## Shared HTTPS host

Use a Linux host with Docker Compose, persistent disk and a DNS hostname you control. Set `APP_DOMAIN`, authorize `https://YOUR_HOSTNAME` in the Google client, configure Google members, and use:

```sh
docker compose -f compose.yaml -f compose.https.yaml --profile switch up -d --build
```

Caddy terminates HTTPS on ports 80/443. The production API refuses local reviewer tokens and insecure origins. Open only 80/443 to users; keep databases, the API and Switch's administrative ports private. If sharing Switch itself, follow the official self-host guide to configure its own TLS, public address and sign-in. The localhost Switch stack is not publicly exposed by the application proxy.

## GCP deployment status

**Step 3 is deployed.** The shared app uses Cloud Run HTTPS addresses backed by the private VM; a custom domain is not required. See [HOSTED.md](HOSTED.md) for the current architecture, URLs, backup/recovery procedure and reviewer onboarding. The server-provisioning details below describe Step 2. Do not repeat baseline preparation scripts over an active presentation project; preserve the active project JSON and matching SQL Git repository together.

On November 7, 2026, project `incident-room-514005` was linked to an active billing account and its deployment APIs were enabled. Step 2 provisions `incident-room-server` in `us-central1-a`: an `e2-medium` with 4 GB RAM, Debian 12 and a 30 GB standard persistent boot disk. A reserved regional address keeps the future application endpoint stable.

The server uses its own `incident-room-runtime` service account and a custom network. SSH ingress is restricted to Google's IAP TCP range; the existing operator accesses it using OS Login. Application ingress is configured during HTTPS deployment. Deletion protection is enabled and the boot disk is retained if the VM is deleted. The runtime account receives application-specific permissions during application deployment.

`deploy/gcp/provision-server.ps1` records completed steps in the ignored `runtime/gcp-server.json`. Its startup script installs Docker Engine and Compose through Docker's signed Debian repository, prepares persistent directories, and records readiness under `/var/lib/incident-room`. Secrets are not included in VM startup metadata. Application installation, database transfer, HTTPS and hosted finance Google sign-in have since completed.
