# GOAT Catalog API

STAC API implementation for the GOAT data catalog.

## Overview

This service serves the harvested GOAT data catalog as a [STAC API](https://stacspec.org/) (v1.0.0: Core, Collections, OGC API - Features, Item Search; extensions: Filter/CQL2, Free-text, Sort, Collection Search, Aggregation), plus GOAT-specific helpers and an MCP server for LLM clients.

It is **database-less by design**: the whole catalog lives in `${DATA_DIR}/catalog/catalog.parquet` (plus `nuts.parquet` for the spatial-filter region search), loaded on startup into an in-memory DuckDB table with a full-text-search index. The files are maintained by the goatlib `sync_catalog` Windmill task (S3 → local, ETag-gated, atomic swap via a `VERSION` marker); the service reloads automatically when the marker changes, without interrupting in-flight requests.

Specs: `docs/goat-catalog-design.md` (architecture), `docs/goat-catalog-api.md` (endpoints, file contract, compliance audit), `docs/goat-catalog-contract.md` (harvester contract).

## Why a Separate Service?

Same rationale as the geoapi/processes split: catalog browse/search traffic and MCP sessions from LLM clients must never contend with the latency-critical tile path. Because the service needs no database and no object storage at request time, it scales by simply running more replicas against the same read-only files.

## Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /stac` | Landing page (Catalog + `conformsTo`) |
| `GET /stac/conformance` | Conformance classes |
| `GET /stac/queryables` · `GET /stac/collections/{id}/queryables` | CQL2 filterable properties |
| `GET /stac/collections` | Dataset collections (Collection Search params) |
| `GET /stac/collections/{id}` · `/items` · `/items/{itemId}` | Collection browse (OGC API - Features) |
| `GET`/`POST /stac/search` | Item Search (bbox, intersects, ids, datetime, CQL2 `filter`, free-text `q`, `sortby`, facet params) |
| `GET /stac/aggregations` · `GET /stac/aggregate` | Aggregation extension (facet counts) |
| `GET /stac/resolve/{id}` · `GET /stac/items/{id}` | GOAT extensions: id resolution / collection-agnostic item lookup |
| `GET /stac/nuts` · `GET /stac/nuts/{id}/geometry` | NUTS region typeahead + boundary (spatial-filter UI) |
| `GET`/`POST /mcp` | MCP server (Streamable HTTP) exposing catalog search tools |
| `GET /healthz` | Liveness + loaded catalog version/item count |
| `GET /api/docs` · `/api/redoc` · `/api/openapi.json` | Interactive API docs + OpenAPI schema (same layout as geoapi/processes) |

All `/stac` and `/mcp` routes honor the repo-wide `AUTH` switch (JWT via Keycloak when enabled).

## Running Locally

```bash
# Needs a catalog file. Generate a synthetic one for development:
cd apps/catalog
uv run python -c "
from pathlib import Path; import sys; sys.path.insert(0, 'tests')
from fixtures.gen_catalog import write_catalog, write_nuts
d = Path('/tmp/goat-catalog-dev/catalog'); d.mkdir(parents=True, exist_ok=True)
write_catalog(d, n=1000); write_nuts(d)"

DATA_DIR=/tmp/goat-catalog-dev AUTH=False uv run uvicorn catalog.main:app --reload --port 8400
curl localhost:8400/stac | jq .

# Tests
uv run pytest tests/
```

## Configuration

Env prefix `CATALOG_`; shared values (`AUTH`, `DATA_DIR`, `KEYCLOAK_SERVER_URL`, `REALM_NAME`, `CORS_ORIGINS`) are read from their repo-wide names with `CATALOG_`-prefixed overrides. Notable settings: `CATALOG_ENABLE_MCP` (default true), `CATALOG_MCP_ALLOWED_HOSTS` (default `["*"]`; set the real ingress hostname in production).
