# Open items: flat layer storage, tests, CI

Follow-ups from the flat-layer-storage work (2026-08-16 rehearsal, 2026-08-22
tests/CI pass). The migration runbook is `flat-layer-storage-migration.md`.

## Blocking the catalog backend

All shipped 2026-08-23/24 (option B: plain GeoParquet + `rowid` view; commits
`b669fb1ed..e8dc2919e` on `catalog`, plan doc P1–P4). Nihar's bundles PR #3774
merged on top (`b07cb6fa6` + six fix commits). Remaining catalog work is P5
(locked bundles) and the sections below.

## Manual testing owed (before dev rollout)

- [ ] Browser click-through, catalog: project → Add layer → Catalog tab →
      select datasets → Add → pending caption clears → layer draws. Everything
      below the UI is verified; the UI itself has only compile+tests.
- [ ] Browser click-through, bundles: Add layer → Upload tab → `*gtfs*.zip` →
      "detected" note → upload → job tray → bundle on /datasets → locked group
      in the project. Local env is fully wired for both (DB migrated+seeded,
      Windmill scripts synced, `BUNDLES_DATA_DIR` on workers + `.env`).

## Rollout

- [ ] Dev, then prod, per the runbook. The rule that cost a day locally: the
      goatlib rollout and the data migration must land in the same window, or
      workers compute `lake.user_<uid>.t_<layer>` for tables that have moved
      and every tool run fails.
- [ ] **Chart updates (infra repo, helm values) — new env this branch needs:**
  - tools worker: the five `CATALOG_S3_*` vars (bucket, endpoint, key, secret,
    region — secret via a Secret, not values) and `BUNDLES_DATA_DIR`
    (default `/app/data/bundles` is right when the data volume mounts at
    `/app/data`); append **both** to `WHITELIST_ENVS` or jobs never see them.
  - core: `WINDMILL_URL` / `WINDMILL_TOKEN` / `WINDMILL_WORKSPACE` (enqueues
    materialize directly), plus a **read-only mount of only the catalog
    subtree**: `subPath: catalog`, `readOnly: true`, mounted at
    `/app/data/catalog` (compose equivalent already on the branch;
    `CATALOG_DATA_DIR` then needs no explicit value).
  - geoapi: nothing new if `DATA_DIR` is right (`CATALOG_LAYERS_DIR` derives);
    set explicitly only if the volume layout differs.
  - processes: `BUNDLES_DATA_DIR` consistent with the workers (it resolves
    bundle artifacts for tool runs).
- [ ] Per-env DB steps, in order: `alembic upgrade head` (bundle tables +
      catalog backrefs + merge revision `7732fb7ef953`) → `initial_data.py`
      (re-installs `check_layer` with the catalog + bundle branches, seeds the
      `datasets` authz resource row, bundle types, catalog identity).
- [ ] Windmill sync per env: `catalog_materialize`, `bundle_import`,
      `bundle_artifact_delete`, and the `catalog_gc` scheduled task.
- [ ] Catalog service prerequisite: `$DATA_DIR/catalog` mirror files
      (`catalog.parquet` / `mirror_items.parquet` + `nuts.parquet`) must exist
      on the env — the promote endpoint 503s without them (harvester/sync task
      owns producing these).
- [ ] Repoint `/home/p4b/goat/compose.override.yaml` when leaving the `catalog`
      branch — it currently mounts goatlib from the `goat-catalog` worktree, so
      switching branches silently runs stale code in the workers. Backup at
      `compose.override.yaml.bak-preflatten`.

## Bundle follow-ups (from the PR #3774 review; owner: Nihar unless noted)

Fixed at merge time: `POST /datasets` authz seed row, s3_key restricted to the
caller's upload prefix + validation off the event loop, `bundle_id` read-only
on group create, UUID guard before artifact `rmtree`, retryable failed imports
(cleanup + artifact upsert), datasets-grid revalidation after bundle/layer
mutations. Still open:

- [x] ~~`edge_path` / `node_path` in the huff-model job payload~~ — verified
      not exploitable: the runner excludes both fields when building the
      analysis params, so payload values are dropped; only the
      bundle-resolved paths are ever set.
- [ ] No ownership check when a tool run resolves a `bundle_id` artifact —
      but this is PARITY: tool runs don't authorize their input *layer* ids
      either (goatlib logs non-owner access and proceeds). The real fix is
      upstream — authorize resource ids in tool params at job submission
      (processes/core) — one design item covering layers and bundles alike.
- [x] Layer-delete tool now refuses bundle member layers (delete the bundle
      instead); bundle deletion unaffected — it removes the link rows first.
- [x] Bundle folder-moves now require a folder of the *bundle owner*, so a
      shared editor can no longer strand (or cascade-delete) the owner's
      bundle via their own folders.
- [ ] GTFS importer materializes whole files in memory (`shapes.txt` is
      GB-scale in national feeds) → worker OOM; stream via DuckDB instead.
- [ ] Any `.zip` named `*gtfs*`/`*overture*` is forced into the bundle path
      with no way to import as a plain layer — needs an override affordance.
- [ ] `list_bundles` is unpaginated.
- [ ] Decision (user): the `enUS`→`enGB` date-locale change rode along
      app-wide — keep or revert.
- [ ] Decision (user): DE locale uses both "Datenpaket" and "Bundle" — pick
      one term.
- [ ] Decision: bundle artifacts live on the shared RWX data volume
      (`BUNDLES_DATA_DIR`) — defensible per the matrices/gtfs mirror
      precedent, but the direct-S3 end-state has to absorb it.

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

## With the legacy-catalog retirement (design §11.4)

- [ ] **Collapse the flat metadata columns on `customer.layer` into JSONB.**
      Measured on the dev copy (12,257 layers): outside the 66 old
      `in_catalog` rows, license is set on 25, category on 37,
      positional_accuracy on 1 — these columns were only ever the old
      catalog's schema, hardcoded onto every row. Keep `name`,
      `description` (15% use) and probably `tags`; the rest move to a
      JSONB `metadata` column. Do it TOGETHER with removing the old catalog
      UI/endpoints, because those are the main consumers and the sweep
      (Metadata modal, DatasetSummary, core schemas, project export/import)
      is the same. The new catalog needs no typed columns in PG — faceting
      happens in the STAC service — and promoted layers already carry the
      full item snapshot in `other_properties.catalog_item`, stored at
      promote time because the mirror is rebuilt wholesale and an old
      version's metadata exists nowhere else afterwards.

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
