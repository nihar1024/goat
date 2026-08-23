# Catalog backend — implementation plan

Status: draft v1 (2026-08-22). Companion to `goat-catalog-design.md` (which it
amends in §7/§8) and `goat-catalog-contract.md`. Plan 1 (the `apps/catalog`
STAC service) is live; this is Plan 2 (core/goatlib/geoapi) + Plan 3 (frontend),
plus the format architecture that keeps future formats from being a rework.

## 1. The two axes: source × format

Every dataset in GOAT has a **source** and a **format**, and those two decide
everything else — where bytes live, how they are served, whether they can be
edited, how analytics reads them.

|                        | source = user upload            | source = catalog (promote-on-use)      |
|------------------------|---------------------------------|-----------------------------------------|
| vector / table         | DuckLake table — **editable**   | GeoParquet file — read-only              |
| raster (COG) *(later)* | COG in object storage — RO      | COG in object storage — RO               |
| point cloud *(later)*  | COPC/LAZ in storage — RO        | COPC/LAZ in storage — RO                 |
| locked bundle (GTFS)   | `import_bundle` (Nihar) — RO members | Bundle + member layers — RO         |
| open bundle            | n/a                             | pure STAC grouping, members promote individually |

Two rules fall out, and they are the whole design:

1. **Editable = (source == user) AND format supports editing.** Today only
   vector/table supports editing, and only DuckLake provides it. Everything
   else — every catalog dataset, every future COG/point cloud — is files +
   Postgres metadata, read-only. "Edit a catalog layer" later = copy-on-write
   import into the user's own DuckLake, which is the existing import path.
2. **Vector is the ONLY format with two storage backends.** Every other format
   is identical for both sources. So the format seam is not speculative
   generality — it is the shape the data already has.

Reference point: GeoLibre (opengeos) supports GeoParquet, FlatGeobuf, COG,
Zarr, PMTiles, 3D Tiles, COPC — all cloud-native files streamed by range
requests with no server conversion. Storing catalog artifacts as exactly such
files (clean GeoParquet, later COG) keeps direct streaming open as a serving
option with no storage change.

## 2. The format seam (goatlib)

One registry, used by BOTH producers (upload and promote):

```python
class FormatProfile:
    key: str                      # "vector", "raster_cog", "pointcloud", "bundle_gtfs"
    editable: bool                # only vector, and only for user source
    materialize: MaterializeHandler   # catalog item -> local artifact(s)
    # upload-side ingestion handler added when user uploads of the format land

HANDLERS = {"vector": VectorHandler()}          # iteration 1 ships this one
```

Format detection from STAC: `goat:layerType` (feature/table/raster) + the data
asset's media type; locked bundles need `goat:bundleType` from the harvester
(new contract item, extends C4b). Unknown format ⇒ promote refuses with a
clear error — never a half-materialized layer.

`VectorHandler.run(layer_id, item)`:
```
COPY (SELECT * FROM read_parquet(<item.parquet_url>) ORDER BY ST_Hilbert(geometry))
  TO '{DATA_DIR}/catalog/layers/t_<layer_id>.parquet' (FORMAT PARQUET, COMPRESSION ZSTD)
→ generate PMTiles (existing machinery, flat output)
→ update layer row: extent, fields, size; status pending → ready
```
The artifact is written streaming-ready at zero extra cost: GeoParquet
metadata on the geometry column, default row groups (with per-group stats),
Hilbert order so spatial queries prune to few row groups, and — worth adding —
the GeoParquet 1.1 bbox covering column, so range-reading clients can skip row
groups without a spatial index. The file holds pure harmonized data; GOAT's
`rowid` exists only in the read-time view, never in the file.

Core never sees a path; it fires "materialize layer X" and reads the status.

## 3. Storage layout

```
DATA_DIR/
├── ducklake/t_<id>/…              user vector data (DuckLake, editable)
├── catalog/
│   ├── mirror_*.parquet, nuts.parquet    (exists today)
│   ├── layers/t_<layer_id>.parquet       vector handler output; 1 file, never rewritten
│   ├── rasters/…                          (later) COGs
│   └── bundles/…                          (later) bundle payloads if any beyond member layers
└── tiles/t_<id>.pmtiles           shared, flat (exists today)
```

Keyed by GOAT layer id, not catalog uid: a new upstream version is a new
layer, new file, no collision. GC = `rm` + delete row; no snapshots.

## 4. Phases

### P1 — core: schema, identity, promote (3–4 d)
- Migration: `layer.catalog_external_uid text NULL`, `layer.catalog_version
  text NULL`, partial UNIQUE index on the pair (promote idempotency/races).
  Hand-written, `down_revision=init` (dev-DB drift rule).
- Seeded `CATALOG_USER_ID` / `CATALOG_ORG_ID` / `CATALOG_FOLDER_ID` following
  the `DEFAULT_USER_ID` precedent; quota exemption for that org; guard against
  deleting the catalog user (its `ondelete=CASCADE` would take every promoted
  layer with it).
- `goatlib catalog_promote`: read item row from `mirror_items.parquet`,
  STAC → layer field mapping (SPDX→DataLicense, themes→category, style from
  the style asset), INSERT with `status=pending` in `other_properties`
  (JSONB — no extra DDL), unique-index race handling (loser selects winner),
  insert `layer_project` link, enqueue materialize.
- Authz: `check_layer.sql` branch — `catalog_external_uid IS NOT NULL` ⇒
  readable by any authenticated layer-viewer; write routes refuse.
- Core endpoint: add-catalog-item-to-project (hit → instant link; miss →
  promote). Old `/layer/catalog` endpoints untouched until migration.

### P2 — materialize seam + vector handler (2–3 d)
- Dispatch skeleton + `VectorHandler` as above, as a Windmill job
  (processes precedent, fire-and-forget, idempotent — re-run overwrites via
  temp+rename).
- Failure path: status `failed` + error on the layer row; retry = re-enqueue.
- GC job: promoted layers with zero `layer_project` links → rm parquet +
  pmtiles + row (and the catalog org's storage accounting stays exempt).

### P3 — geoapi read path (2–3 d)
- `LayerInfo` → the value object: `kind` (`lake` | `catalog`), `relation`,
  `writable`. Resolver order: DuckLake catalog hit → `lake.…`; else
  `catalog/layers/t_<id>.parquet` exists → ensure view, return `catalog.t_<id>`.
- The view (verified on DuckDB 1.5.4):
  `CREATE VIEW … AS SELECT file_row_number AS rowid, * EXCLUDE (file_row_number)
   FROM read_parquet('…', file_row_number=true)` — every existing `rowid` site
  works unchanged because all SQL interpolates `{relation}`.
- Lifecycle: `CREATE SCHEMA/VIEW IF NOT EXISTS` on first resolve per
  connection — geoapi's shared base connection AND each worker's own. This is
  the riskiest line item; verify against the pinned cursor pool first.
- Two `EXCLUDE` additions so the view's real `rowid` column leaks into neither
  GeoJSON properties nor the field list; `writable=False` ⇒ 403 on write routes.
- `export_layer_to_parquet`: catalog layer ⇒ return the file path (or one
  filtered COPY when a CQL filter is set) — analytics gets faster, not slower.

### P4 — frontend (2–3 d)
- Wire CatalogBody's add-to-project to the new endpoint.
- Pending state: layer row in the tree, not drawn, driven by the existing
  job/toast machinery; status read from the layer row so it survives reload.
- Read-only affordances key off `catalog_external_uid` on the project-layer
  schema (no style-less editing traps).
- Favourites (`customer.favorite`, generic) + "update available" badge can
  trail in a follow-up; promote resolves idempotently server-side without them.

### P5 — locked bundles (3–5 d, gated on Nihar's branch merging)
- Adopt `feat/dataset-groups`' model wholesale: `bundle`, `bundle_type`
  (spec registry in goatlib), `bundle_layer` roles, `bundle_artifact`.
  It replaces design §8's `layer_bundle` placeholder.
- Promote of a `goat:bundle=locked` item = `BundleGtfsHandler`: create
  Bundle(type from `goat:bundleType`) owned by the catalog user, member layers
  by role through the SAME vector handler, artifacts built by his existing
  builders (PT graph → catchment analysis works on catalog GTFS).
- Deltas to agree with Nihar BEFORE merge: (a) locked-only — open bundles stay
  pure STAC, no Bundle row; (b) shared promoted bundles GC by refcount, not
  cascade-on-delete; (c) catalog system user owns promoted bundles.
- Open bundles: nothing to build — collection membership comes from the mirror.

### Later (designed-for, not built)
- User uploads of non-convertible formats (COG first): same `FormatProfile`
  gains an upload handler; stored under user storage, read-only, served by
  range reads. No schema change needed — `layer.type=raster` + internal URL.
- Direct parquet/COG streaming to clients: an authenticated `Range` endpoint
  (or presigned URLs, once storage is direct-S3) over the SAME files. Storage
  is already right — one immutable file per layer version at a stable URL, so
  `ETag`/`Cache-Control: immutable` are free and invalidation is a non-issue
  (a new version is a new URL). Serving + auth work only (S14: stays
  non-public). User-EDITABLE layers are the one thing that cannot stream
  directly (DuckLake internals are mutable/opaque); if wanted, that is a
  derived snapshot artifact regenerated on edit — the existing PMTiles
  pattern.
- Point clouds / 3D tiles: new profiles, same pattern.

## 5. Contract items to raise with the harvester team
- `goat:bundle = open | locked` on collections/items (C4b, already drafted).
- **NEW: `goat:bundleType`** (e.g. `pt_network_gtfs`) on locked items, matching
  goatlib's `BundleTypeName` vocabulary.
- **NEW: data-asset media type must be authoritative** for format dispatch
  (today everything is GeoParquet; the day a COG appears, the media type is
  what routes it).

## 6. Risks / open questions
1. View lifecycle across geoapi's pinned pool + worker connections (P3) —
   verify first, it decides nothing but costs the most if wrong.
2. Nihar-branch timing: P5 depends on it; P1–P4 do not.
3. Update/upgrade UX ("newer version exists" → promote new + repoint link) is
   deliberately out of iteration 1; snapshot semantics make waiting safe.
4. Editing catalog data = copy-on-write import (future); confirm nobody
   expects in-place editing.

## 7. Sizing

P1 3–4 d · P2 2–3 d · P3 2–3 d · P4 2–3 d ⇒ **iteration 1 ≈ 9–13 days**;
P5 adds 3–5 d once Nihar's branch lands. Verification gates: after P3, the
full manual pass (tiles, features, tool run, delete) against a promoted layer;
after P2, promote+materialize round-trip on the real mirror.
