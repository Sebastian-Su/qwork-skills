# WorkBuddy storage requirements

`~/.workbuddy/` is the stable WorkBuddy product-state root. The private snapshot is metadata/hash/schema only; it never copies credentials or user content.

## Stable domains

- Product packages: `plugins/`, `skills/`, `connectors/`, `connectors-marketplace/`, `plugin-marketplace-state-new/`, `binaries/`.
- Durable user/product state: `workbuddy.db`, `sessions/`, `projects/`, `tasks/`, `teams/`, `workspace/`, `project-resources/`, `artifact-index/`.
- Runtime and diagnostics: `app/`, `logs/`, `traces/`, `audit-log/`, `shell-snapshots/`.
- Configuration and identity: `settings.json`, `.mcp.json`, `mcp-approvals.json`, `models.json`, `user-state.json`, `workspace-state.json`, `device-id`.
- Long-term agent context: `BOOTSTRAP.md`, `SOUL.md`, `IDENTITY.md`, `USER.md`, `memory/`, `plans/`.

## Invariants

1. A stable identity must resolve to one canonical path. Version folders or marketplace aliases cannot change the logical expert/package path after sessions reference it.
2. Package content is immutable after activation. Usage, selection, sorting and session state live outside the package tree.
3. No path may escape `~/.workbuddy/`; symlinks are not followed during inventory or migration.
4. Secrets, cookies and credential material are never copied into Dataset evidence. SQLite is opened `mode=ro&immutable=1` and only schema is retained.
5. User-generated path segments are pseudonymized in the Dataset; source files remain in place.
6. QWork parity tests map WorkBuddy domains into `~/.qwork/` deliberately; no compatibility alias such as `workbuddy-local` becomes a persistent identity.
7. Restart, migration and rollback Cases verify both UI recovery and the durable file/database outcome.

## Executable disposition gate

`data/datasets/workbuddy-storage-dispositions.json` is a closed-world, one-record-per-source-atom decision ledger. It binds the frozen inventory hash and separates `decision_status` from `implementation_status`:

- `resolved + verified`: the QWork target and current implementation evidence are both bound;
- `resolved + not-required`: runtime/cache material is intentionally regenerated or excluded;
- any `pending`: the corresponding Case must fail and return its exact next action.

`scripts/validate_workbuddy_storage_case.py` is a non-UI integration replay over immutable Dataset assets. It never opens live `~/.workbuddy` or `~/.qwork`. Its PASS proves only that the bound atoms have complete decisions and evidence; UI recovery, actual migration, restart and rollback remain separate Electron/persistence Cases and cannot be inferred from this verifier.
