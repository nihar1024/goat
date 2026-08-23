# Open items: flat layer storage, tests, CI

Follow-ups from the flat-layer-storage work (2026-08-16 rehearsal, 2026-08-22
tests/CI pass). The migration runbook is `flat-layer-storage-migration.md`.

## Blocking the catalog backend

- [ ] **Decide A or B for catalog layer data.** A = materialize into DuckLake
      (reuses `_ingest_to_ducklake`, all ~57 `rowid` sites keep working, PMTiles
      free). B = plain parquet read via a view that names `file_row_number` as
      `rowid` (verified working on DuckDB 1.5.4). The flat layout removed B's
      "no fake-user directory" argument, so A now costs less for the same
      result. Everything else in the catalog backend is independent of this —
      only the materialize job's target differs. Keep core ignorant of where
      data lives so the choice stays cheap.
- [ ] Core: migration for `catalog_external_uid` / `catalog_version` + the
      partial unique index that makes promote idempotent.
- [ ] Core: seeded `CATALOG_USER_ID` / `_ORG_ID` / `_FOLDER_ID` following the
      `DEFAULT_USER_ID` precedent, **plus** a quota exemption for that org
      (quota is per-org and shared catalog data would otherwise bill to it) and
      a guard on `layer.user_id`'s `ondelete=CASCADE` — deleting that user
      would cascade-delete every promoted layer.
- [ ] goatlib `catalog_promote`, reading the item from the mirror.
- [ ] The materialize job (the only piece A vs B changes).
- [ ] Authz branch for promoted layers (`catalog_external_uid IS NOT NULL` ⇒
      readable by any authenticated layer-viewer).
- [ ] Frontend pending state, reusing the existing job/toast machinery.
- [ ] `LayerSource` value object in geoapi — only needed if B, or when a second
      source kind arrives.

## Rollout

- [ ] Dev, then prod, per the runbook. The rule that cost a day locally: the
      goatlib rollout and the data migration must land in the same window, or
      workers compute `lake.user_<uid>.t_<layer>` for tables that have moved
      and every tool run fails.
- [ ] Repoint `/home/p4b/goat/compose.override.yaml` when leaving the `catalog`
      branch — it currently mounts goatlib from the `goat-catalog` worktree, so
      switching branches silently runs stale code in the workers. Backup at
      `compose.override.yaml.bak-preflatten`.

## CI

- [ ] **Decide whether goatlib's integration tests get a CI home.** 18 files,
      currently run nowhere. They are the *only* coverage the analytics tool
      runners have (buffer, join, clip, dissolve, union, centroid,
      intersection, difference, aggregate, layer import/export/delete, project
      export/import). Needs a Postgres service and a DuckLake fixture.
- [ ] **Decide whether the Playwright e2e suite runs in CI.** 7 files, never
      executed. Needs a service stack. The unused Chromium install was removed
      from the web job, so adding e2e means adding it back deliberately.
- [ ] `.github/workflows/` is **not tracked by git in the goat-catalog
      worktree** — confirm where these workflows are versioned before relying
      on the `goatobs` job and the goatlib `unit+utils+io` change.

## Test-suite hygiene

- [ ] Three heatmap tests fail on stale local fixture data:
      `data/traveltime_matrices/walking` has `orig_id, dest_id, cost, h3_3`
      while the code reads `traveltime`. They `assert path.exists()` with no
      skip guard. Regenerate the matrices, or add a skip when the schema does
      not match.
- [ ] `apps/geoapi` and `apps/processes` suites fail when a shared `.env` is
      sourced (3 and 2 tests). `apps/catalog` got an autouse fixture that
      clears the env vars its settings read by alias; the same treatment would
      make a root-level run green with `.env` loaded. CI is unaffected — it
      sets only the env each job needs.
- [ ] Cross-app pollution in a single-session run: `apps/core/tests/api/*`
      passes 167/167 alone and fails ~31 when collected with other apps. CI
      never does this (one job per app), so it is a local-workflow issue only.

## Deferred, lower priority

- [ ] `ducklake_compact` SIGSEGV on prod — still unresolved, compact left off.
- [ ] The DuckLake `ATTACH` mkdir race seen once during concurrent thumbnail
      rendering (`[Errno 17] File exists: '/app/data/ducklake'`). A read-only
      manager no longer creates the directory, which may or may not have been
      the cause. If it recurs, capture the **full traceback** — the message
      alone does not name the call site.
- [ ] Lake leftovers: 5 `user_*` directories (238 subdirs, no catalog rows) and
      the `churn_test` / `rowid_test` / `upgrade_test` / `import_probe`
      schemas. Inert; delete when convenient.
