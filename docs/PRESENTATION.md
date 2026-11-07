# Presenting the real repair workflow

Use the hosted dashboard and the private Incident Room channel in Mattermost or Switch Console. Google sign-in establishes finance and engineering authority; chat participant bindings connect room messages to those verified identities. The engineering reviewer must complete Google sign-in once before approving or publishing.

## The incident

The source is the real UCI Online Retail dataset: 541,909 invoice lines. A separate `incident_room_presentation` dataset contains cloned raw, line and daily assets. Its separate SQL repository deliberately contains `WHERE NOT is_cancellation` before the daily aggregation. That removes cancellation records from a metric whose contract requires every signed invoice line. This is a disclosed presentation fault, not a claim that an actual business experienced an outage.

The independent raw-based checks detect the omission. Five of six current contracts pass; the daily reconciliation contract fails. The correct signed total is GBP 9,747,747.934. Excluding cancellations yields GBP 10,644,560.424, an overstatement of GBP 896,812.490. The raw records and original `incident_data` warehouse remain unchanged. Setup separately tested the minimal correction in disposable clones and obtained six passing contracts; the presentation's faulty table and main SQL branch remain available for a live investigation.

## Run it

1. Finance signs in to the dashboard. Open a **new incident** with this report:

   > In the controlled presentation dataset, the daily signed invoice total is GBP 10,644,560.424, but the raw invoice lines sum to GBP 9,747,747.934. Investigate the daily transformation and explain the GBP 896,812.490 difference with query evidence. Preserve the source records.

2. Finance enters the metric definition and clicks **Confirm definition**:

   > Signed invoice value is the exact NUMERIC sum of original quantity times GBP unit price across all original records, including C-prefixed cancellations, negative and zero adjustments, and missing-customer rows. Daily grain is source invoice date and country across every original line. Daily totals and counts must reconcile directly to the raw inputs. Preserve the selected output columns and arithmetic; correct only the daily transformation when supported by evidence.

3. Click **Run investigator**. Show the executed SQL, returned evidence and BigQuery job IDs. The model may ask a specific clarification; answer it through **Team context**, then rerun. The output is generated live and need not use identical wording on every run.

4. Show the proposed SQL diff and verification results. A passing isolated rebuild makes a patch eligible for review. It does not change the presentation table or the original warehouse.

5. Finance reads the evidence and exact diff, then clicks **Approve as finance**. Engineering signs in separately, reviews the same proposal and clicks **Approve as engineering**. One Google identity cannot provide both required approvals. New context, changed source or a changed proposal invalidates earlier approval.

6. Engineering clicks **Publish verified branch**. The server repeats validation and commits exactly the approved SQL to `incident-room/<incident-id>`. Show the branch and commit in the verification panel. The main checkout stays unchanged. No GitHub PR is created until a real remote and credentials are connected.

7. State the outcome accurately: the team has an evidence-backed, independently reviewed and tested repair branch. Deployment and post-deployment checks are separate; the app has not silently overwritten warehouse tables.

## Show the Switch contribution

For a room-linked investigation, start it through the agent instead of the dashboard: mention **incident-room** and send `!open <report>`. Finance then sends `!definition <definition>`, followed by `!evidence`. Poll `!status` to retrieve asynchronous results. The dashboard and chat use the same incident and audit trail.

Reviewers can also send `!approve <full proposal digest>` and engineering can send `!repair`. These are explicit authenticated commands; ordinary chat does not count as approval. In Mattermost, prefix each command with `@incident-room`. Console users select/mention the Incident Room agent. An incident created only in the dashboard has no room association; start in chat if you want to show both surfaces sharing that case.

The useful contribution is the shared investigation and authority across people and an agent: finance supplies business meaning, the agent executes evidence-gathering tools, engineering inspects the code, both reviewers approve an exact tested artifact, and Switch carries that collaboration through a real room.

## Repeat or reset

The publication step preserves the faulty main branch and warehouse, so a new incident can investigate the same fault again. Each run makes new model calls and validation jobs. Do not reuse a proposal after its source/configuration changes. Do not reset persistent app history or alter the original warehouse merely to repeat a presentation.

The operator setup script `deploy/gcp/prepare-presentation.py` refuses an existing presentation record or nonempty repository. It is a one-time preparation tool, not an automatic reset. Preserve `/srv/incident-room/runtime/presentation-evidence.json`, the active project JSON and the SQL repository in backups.
