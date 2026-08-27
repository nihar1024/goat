# Open items: flat layer storage, tests, CI

Follow-ups from the flat-layer-storage work (2026-08-16 rehearsal, 2026-08-22
tests/CI pass). The migration runbook is `flat-layer-storage-migration.md`.

## Blocking the catalog backend

All shipped 2026-08-23/24 (option B: plain GeoParquet + `rowid` view; commits
`b669fb1ed..e8dc2919e` on `catalog`, plan doc P1–P4). Nihar's bundles PR #3774
merged on top (`b07cb6fa6` + six fix commits). Remaining catalog work is P5
(locked bundles) and the sections below.

## Manual testing (browser click-throughs) — DONE 2026-08-24

Both flows verified in a real browser session against the local stack. The
catalog flow surfaced and fixed three real bugs (selection double-expansion
404, legend caption clobbering the pending caption, link-frozen
other_properties never clearing pending); the bundle flow surfaced the
missing `GOAT_GEOAPI_HOST` wiring. Verified along the way: pending caption
appears and clears via the 4s poll, ready-before-tiles serves dynamic MVT
(287MB NRW flood layer usable while tippecanoe ran), bundle upload detects
GTFS, imports 7 member layers, and renders the locked drag-disabled group.
Not covered: actual map rendering (headless browser has no WebGL) — worth one
human glance at the map canvas.

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
- [ ] Verify `GOAT_GEOAPI_HOST` is set on core in the charts (it predates this
      branch — folder-delete layer cleanup posts through it — but was missing
      from compose/.env.example until now; unset, bundle imports 503 and
      cleanup is silently skipped).
- [ ] Worker image: the routing extension must be rebuilt WITH the
      `build_timetable` binding or every GTFS bundle imports without its
      timetable artifact (graceful skip, logged as a warning — layers still
      ingest, but PT analysis on the bundle stays unavailable).
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
- [x] DECIDED 2026-08-24: `enGB` stays — European users expect day-first
      dates even in the English UI.
- [x] DECIDED 2026-08-24: "Datenpaket" is THE German term — all DE strings
      swept (was a three-way split with "Bundle" and "Paket").
- [x] DECIDED 2026-08-24: artifacts stay on the shared data volume
      (`BUNDLES_DATA_DIR`) per the matrices/gtfs mirror precedent — the
      routing engine opens them as local files. The direct-S3 migration must
      absorb them (add to that plan when it starts).

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

- [x] **Drop the old catalog's metadata columns from `customer.layer`.**
      DONE 2026-08-27. Thirteen columns removed (migration
      `c3e7a91b4d10`, which also carries the drops below) with
      **nothing replacing them** — the earlier plan to collapse them into a
      JSONB `dataset_metadata` was dropped once it was clear a layer has no
      metadata of its own to hold:

      * a user's uploaded dataset is its name, description and tags; publishing
        one to the catalog will be its own job, not a set of columns;
      * a promoted catalog layer already carries the catalog's record verbatim
        in `other_properties.catalog_item`, and `DatasetSummary` now reads it
        from there, in the catalog's own vocabulary.

      Translating that vocabulary into ours was considered and rejected:
      `DDN2` is an enum invented for the old catalog's filter dropdown, so
      mapping `DL-DE-BY-2.0` onto it replaces a real versioned licence
      identifier with an internal code, loses the `2.0`, and needs a lookup
      maintained forever — for a shape the catalog may change anyway.

      `customer.bundle` keeps its `dataset_metadata` document, because there an
      importer genuinely fills it (`feed_publisher_name` out of a GTFS feed).

      Measured before dropping: 109 of 12,281 layers carried any of the
      thirteen, 66 of them the old `in_catalog` rows.

- [x] **Remove the old catalog.** Endpoints `POST /layer/catalog` and
      `POST /layer/metadata/aggregate`, their schemas (`ICatalogLayerGet`,
      `IMetadataAggregate`, `IMetadataAggregateRead`, `MetadataGroupAttributes`),
      `crud_layer.metadata_aggregate`, the five filter params on
      `LayerGetBase`, and on the web the `CatalogExplorer` modal, its two
      workflow-panel entry points, `useCatalogLayers`, `useMetadataAggregated`
      and `datasetMetadataAggregated`. `METADATA_HEADER_ICONS` moved out of the
      deleted `CatalogDatasetCard` to `lib/constants/metadataIcons.ts`.

- [ ] **Workflow nodes lost their catalog source with the old explorer.**
      `DatasetNodeSettings` and `SqlToolSettings` offered "Catalog Explorer" as a
      data source and nothing replaced it. The new picker (`CatalogBody` +
      `useCatalogFlow`) can serve it, but a workflow node wants a bare
      `customer.layer` id and no project link, so it needs: a promote-only
      endpoint (`promote()` already takes no project — the link is added
      afterwards in `project_layer.py`), a single-select mode in the picker, and
      a decision about materialize — a freshly promoted layer is `pending` until
      the job finishes, and a workflow run against it would find no data.

- [x] **Remove scenarios.** No code referenced them any more: `apps/core` had no
      model, CRUD or endpoint, `apps/web` had nothing at all, and the last live
      reader (`get_scenario_features`) was broken — it treated
      `attribute_mapping` as `{real: generic}` while every stored row is
      `{generic: real}`, so it emitted `sf."category" AS "text_attr1"` against a
      table with no such column. Gone from goatlib: `scenario_id` on
      `ToolInputBase`, `ScenarioSelectorMixin`, `scenario_selector_field`, the
      `SECTION_SCENARIO` UI sections in 22 tools and both catchment-area
      runners, the merge path (`base._merge_scenario_features`,
      `db.get_scenario_features`), the routing payload branch (dead — it tested
      `hasattr(params, "street_network")`, an attribute no params class has),
      and the `scenario` / `scenario_id` i18n keys. The tables go too — see
      below.

      **Rollout step:** re-run `sync_windmill` per environment. Every published
      tool script carried a `scenario_id` argument in its generated `main()`
      signature, because the field lived on `ToolInputBase`. Local Windmill was
      re-synced 2026-08-27 (44 tools + 9 tasks; all 42 registered tools verified
      clean afterwards). Four unregistered leftovers still mention it —
      `catchment_area` and `heatmap_{gravity,connectivity,closest_average}_v2`,
      superseded by renamed tools and never deleted by the syncer — harmless,
      nothing dispatches them, delete when convenient.

- [x] **Scenario tables dropped.** DECIDED 2026-08-27 by the user, knowing there
      are rows in production: *"even if there is scenario data in prod we don't
      need it anymore"*. `customer.scenario` (214 rows, 118 distinct owners),
      `customer.scenario_feature` (246), `customer.scenario_scenario_feature`
      (245) and `customer.project.active_scenario_id` (160 non-null) all go in
      migration `c3e7a91b4d10`, after the column drops so the FKs unwind
      cleanly. The downgrade recreates all three in shape, regenerating
      `scenario_feature`'s 109 generic attribute columns from a family table
      rather than spelling them out; verified by running upgrade **and**
      downgrade inside one rolled-back transaction against the real database
      (layer 41 -> 24 -> 41 columns, table set identical, `scenario_feature`
      back at exactly 121 columns).

      Worth knowing if this is ever second-guessed: the payload would have
      become unreadable anyway. `scenario_feature` kept attributes in generic
      slots (`text_attr1`, `jsonb_attr1`, …) and the only thing that said what
      they meant was `layer.attribute_mapping`, which the same migration drops.
      Keeping the tables would have preserved bytes, not information. A
      `pg_dump` of the three tables before running this is the only way back.

- [x] **Drop `attribute_mapping` and the vestigial upload/data-store columns**
      (same migration, `c3e7a91b4d10`). `attribute_mapping` mapped generic physical
      column names back to real ones from the shared-wide-table era; the DuckLake
      migration already applied it (a layer mapping `{"text_attr1": "category"}`
      has a `category` column) and the field list now comes from the table schema
      plus `field_config`. Also dropped: `upload_reference_system` (0 rows) and
      `upload_file_type` (30) — no writer, no read schema — and `data_store_id`
      plus the whole `customer.data_store` table (5 rows, no CRUD, no endpoint,
      no router). Five dead helpers went with it from `core/utils/__init__.py`
      (`get_layer_columns`, `search_value`, `next_column_name`,
      `get_result_column`, `build_insert_query`).

      **Kept deliberately:** `tool_type` (9,828 rows) and `job_id` (11,451).
      Nothing reads either, but they record which tool and which Windmill job
      produced a layer, across most of the table — provenance, not cruft.

- [x] **The layer Metadata modal edits name and description only.** It was still
      posting `dataset_metadata` for layers after the columns went, which would
      have silently dropped every field. The provenance inputs (lineage,
      distribution, licence, attribution, reference year, geographical code) now
      render for **bundles** only, packed with `BUNDLE_METADATA_KEYS`; the form
      is typed on `BundleMetadata`, the widest of the three content kinds it
      serves. `layerMetadataSchema` is now just `contentMetadataSchema`.

- [x] **Second sweep (2026-08-27), after the first pass left residue.** Three
      read-only agents swept core, goatlib and web. What was genuinely caused by
      the removals and is now fixed:

      * `DataLicense` and `validate_geographical_code` still lived in
        `db/models/layer.py` — only bundle provenance uses them, so they moved to
        `schemas/metadata.py` and `pycountry` left the layer model.
      * `seed_roles` still granted `layer/catalog` and `layer/metadata/aggregate`.
      * `CRUDLayer.get_base_filter` kept an `attributes_to_exclude` parameter
        (only `metadata_aggregate` ever passed it) and an `isinstance(params,
        ILayerGet)` guard whose `else` branch existed for the deleted catalog
        schemas — always true now, so both went.
      * `"Create scenarios"` in the three gettext catalogs (`.mo` recompiled).
      * `request_examples` advertised a `get` key, an `export` key for an
        endpoint core does not have, and feature/table create bodies that only
        the raster endpoint would ever see.
      * `export_layer_to_parquet` kept a `project_id` parameter after the
        scenario merge went — **42 call sites across 26 tool files** were still
        passing it, plus the chain through both catchment-area coordinate
        helpers. `db.get_layer_project_id` was orphaned the same way.
      * `analysis/schemas/__init__.py` listed `"vector"` in `__all__` with no
        such symbol, so `import *` raised `AttributeError`.
      * Web: `getDatasetSchema` still declared the five removed filter params,
        `datasetMetadataValue` was the deleted aggregate endpoint's response
        shape, `useLayers` was unsubscribed (leaving three `mutate()` calls in
        rename/delete/share doing nothing — rewired to `matchesContentListKey`),
        `ICON_NAME.SCENARIO`, four dead `AddLayerSourceType` members, eight
        orphaned i18n keys, and stale catalog-explorer comments.
      * **`DatasetSummary` was showing eleven rows that could never resolve** —
        it reads the catalog record but still listed the old layer-metadata
        field names. Rewritten against the snapshot's actual keys
        (`processing:lineage`, `publisher`, `category`), with an explicit
        `i18nKey` per row because the vocabularies differ, and three missing
        `no_metadata_available` strings added in EN and DE.

      Checked and deliberately **not** treated as fallout: the `ARG002` unused
      arguments in `base.py`, `layer_replace.py`, `project_export.py` and
      `project_import.py` are identical to `origin/catalog` — they belong to the
      flat-layer-storage work, not to this removal.

- [x] **Catalog layers have no owner.** DECIDED 2026-08-27: the synthetic
      `catalog@goat.local` user existed only because `layer.user_id` was
      `NOT NULL`, and it dragged a fabricated organization with it (invented
      phone number, industry `other`, region `EU`, 2^31 quotas) plus an
      owner-role link and a folder. `user_id` and `folder_id` are now nullable
      and NULL for every promoted catalog layer, and that whole identity is
      deleted — `CATALOG_USER_ID` / `CATALOG_USER_EMAIL` /
      `CATALOG_ORGANIZATION_NAME` / `CATALOG_FOLDER_ID` and
      `seed_catalog_identity` with it.

      NULL is the truth (a catalog dataset belongs to the provider that
      published it) and every consumer already behaved correctly for it: the
      storage trigger finds no organization and bills nobody, "My Content"
      filters on `user_id = you` and never lists them, `check_layer` grants read
      through `catalog_external_uid IS NOT NULL`, and `canEditLayerFeatures`
      already returns false on a falsy owner.

      The ordering trap, since it would have destroyed data: `layer.folder_id`
      is `ON DELETE CASCADE`, so the rows are detached **before** the folder and
      user are deleted. Dropping the folder first takes the 17 layers with it,
      and all 17 are live in users' projects. (The DB has no FK on
      `layer.user_id` even though the model declares one — pre-existing drift.)
      Verified up **and** down in one rolled-back transaction: 17 layers keep
      their project links, the user and org disappear, no other layer is
      touched, and the legacy `catalog@plan4better.de` account keeps its 66
      `in_catalog` layers.

- [ ] **`in_catalog` is now doing two jobs and should be resolved.** The column
      is the old catalog's flag (66 rows), but the *field name* has been reused
      in the map UI as the read-only marker for catalog layers of either
      generation — `ProjectLayerTree` sets
      `in_catalog: layer.in_catalog || isCatalogLayer(layer)`, and rename,
      delete, the edit table and the layer menu all gate on it.

      Now that catalog layers are unowned, the honest replacement is "I don't
      own this dataset", which `canEditLayerFeatures` already computes. The
      blocker is the 66 legacy rows: they are owned by the real
      `catalog@plan4better.de` login, so ownership alone would make them
      editable, and `check_layer` still grants read through the flag. Options,
      in order of preference: set those 66 to NULL owner too (one UPDATE, then
      `check_layer` keys on `user_id IS NULL OR catalog_external_uid IS NOT
      NULL` and the flag drops), or leave the column as a pure legacy marker.
      Do **not** fabricate `catalog_external_uid` values for them — it is the
      STAC item id and carries promote's idempotency contract.

- [ ] **Decide what identifies a catalog-sourced bundle**, when P5 locked
      bundles land. Today no catalog dataset creates a `customer.bundle` row at
      all: a multi-layer dataset promotes to N layers plus a locked
      `layer_project_group` whose `bundle_id` stays NULL. If catalog bundles
      ever do get a row, they want `catalog_external_uid` + `catalog_version`
      under a partial unique index (the identity contract that gives promote
      its idempotency), plus the STAC snapshot — not the flat provenance
      vocabulary, which no catalog path can fill. Deliberately NOT pre-added:
      "the same bundle at the same version" is undefined while members promote
      as separate layers, and the harvester still publishes no
      `goat:bundleType` and no locked marker (verified against the 2026-08-27
      mirror), so the constraint would be designed blind.

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
