# Demo recording plan — under three minutes

Record a real interaction between finance, engineering and the custom Incident Room agent in the private Mattermost channel. The engineering reviewer must first complete their own Google sign-in. Keep passwords, keys and the private access file outside the recording. The dashboard is invite-only, so the video should show the complete workflow without requiring judge access.

Aim for 2:40–2:55. It is fine to cut waiting time or visibly speed it up; preserve the actual order and outcomes, and label edited waiting time. Do not substitute automated test identities for the two human reviewers.

| Time | Show | Explain |
| --- | --- | --- |
| 0:00–0:15 | Private Mattermost Incident Room channel with both people and the agent. | Finance and engineering need to explain a conflicting invoice metric together. The connected agent is a custom Python/OpenAI agent, using Switch. |
| 0:15–0:35 | Finance sends `@incident-room !open <report>` and `!definition <contract>`. | The presentation dataset deliberately omits cancellations from the daily transform. The source is real UCI retail data; this fault is disclosed and isolated. |
| 0:35–1:15 | Finance sends `@incident-room !evidence`; retrieve `!status`, then show the same incident's evidence in the dashboard. | Executed SQL and BigQuery job IDs support the cancellation discrepancy. The model is producing the result live; explain the difference using the actual returned evidence. |
| 1:15–1:45 | Proposed SQL diff and independent isolated checks. Engineering sends a review message in chat. | Explain the correction and the six passing checks if that is the actual result. If a check fails, show and address it before approval. |
| 1:45–2:15 | Finance and engineering each send `@incident-room !approve <full digest>` using their own chat accounts. Show both approval indicators. | Both people approve the same exact tested patch. The agent cannot approve itself. |
| 2:15–2:40 | Engineering sends `@incident-room !repair`; retrieve `!status` and show branch/commit in the dashboard. | The server revalidates and publishes the exact approved SQL as a Git branch. No automatic production-table overwrite or hosted GitHub PR is claimed. |
| 2:40–2:55 | Audit trail and project repository. | The result is shared evidence, two accountable approvals and a verified repair artifact. Switch connects the humans and agent through the real channel. |

Use the exact report and definition in [PRESENTATION.md](PRESENTATION.md). The source data has 541,909 invoice lines. The documented fault produces GBP 10,644,560.424 versus the raw signed total GBP 9,747,747.934. Let the investigation substantiate those figures with actual queries.

After recording, upload to YouTube or Loom as public or unlisted. Check the link in a signed-out browser, verify the duration is under three minutes and paste the actual link into the submission. A video has not yet been recorded or uploaded; this document is a plan, not evidence that the two-person flow has been completed.
