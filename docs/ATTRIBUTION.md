# Prior work and scope

Blackbox by Alex Velazquez / the BlackBox contributors: https://github.com/alejandro-publius/blackbox-datahub

Source repository license: Apache-2.0. Original commit reviewed is recorded in `UPSTREAM_REVISION.txt` when packaging. No upstream executable source or branding is incorporated into this app. The upstream source is retained separately for reference with its own license and notices.

Original architectural inspiration: machine-produced evidence, gated repairs, verified execution and verification.

This implementation's focus: finance-owned metric definitions, team context revisions, proposal-bound dual-role approval, stale-evidence rejection and room-based collaboration.

Switch protocol references checked November 7, 2026:
- https://docs.switchagents.ai/switch-rooms/internals/agent-protocol
- https://docs.switchagents.ai/switch-rooms/internals/agent-connection
- https://docs.switchagents.ai/switch-rooms/internals/agent-events

No claim of exclusive technical novelty is made.

The external local Switch server uses the official 0.31.0 images and version-pinned standalone Compose artifact. Switch is licensed under Apache-2.0 with the Commons Clause; its license is retained beside that stack as `SWITCH-LICENSE`. No Switch executable source is copied into Incident Room. See the official [self-host documentation](https://docs.switchagents.ai/switch-rooms/deploy/self-host) for the server's deployment and licensing boundaries.
