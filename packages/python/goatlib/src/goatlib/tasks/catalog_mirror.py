"""Build the query-shaped catalog mirror from published stac-geoparquet.

The harvester publishes native stac-geoparquet at the bucket root --
``items.parquet`` (one row per STAC Item, ``properties.*`` promoted to
top-level columns, ``assets``/``links`` as real STRUCTs) and
``collections.parquet`` (one row per Collection). ``apps/catalog`` reads
``mirror_items.parquet`` + ``mirror_collections.parquet``: the same rows, every
published column passed through under its published name, plus the columns a
search needs and a published file cannot have -- collection fields
denormalised onto their items, a lowercased ``search_text``, envelope scalars,
and precomputed bundle membership.

This module is that build. It runs at sync time, not per request, so the
service reads local files and knows nothing about the published layout.

Two properties are deliberate:

**Everything is derived from the observed columns.** The published schema is
not ours to pin, and it has already changed twice in a day (``language``
appeared on items, ``license``/``providers``/``themes`` on collections, the
``type`` column went away). So the column list comes from ``DESCRIBE``: every
published column is passed through under its published name, a derived
expression over a column that is absent yields ``NULL`` rather than a SQL
error, and a *new* published column is served as a ``properties.*`` member --
and picked up by ``catalog.services.registry`` as a queryable -- with no code
change on either side.

**The join denormalises.** ``license`` and ``providers`` live on the
Collection, never on the Item, but the catalog page facets *datasets* by
licence and publisher. Doing that join here -- once per harvest -- is what
lets every request stay a single-relation scan.

Items and collections stay in **separate files**, as they are published and as
pgstac stores them: merged, every item query would carry a discriminator
predicate over rows it can never return, and the schema would be the union of
both. Measured over 1.77M rows, separate relations won on every query shape.

The remaining derived columns exist only to keep request-time work off the hot
path, measured at the 1M-item target:

- ``search_text`` is one lowercased column holding title, description,
  keywords and publisher. It is what free-text scans; it replaced a full-text
  index that cost 1.8 GB resident and a rebuild in every pod on every swap.
- ``goat:geographical_code`` and the other facet columns are real columns
  rather than paths into a JSON blob: filtering through a JSON path cost 1.4 s
  per query at 1M rows versus 2.6 ms as a column.
- ``member_count``, ``is_representative`` and ``group_geometry`` precompute
  bundle membership, which a per-request ``GROUP BY`` was recomputing over
  every item row (~1 GB of hash table) on data fixed between harvests.
- ``bbox_xmin``/``ymin``/``xmax``/``ymax`` (and the ``group_*`` pair) are the
  envelopes as plain doubles, which a spatial filter tests before it calls
  ``ST_Intersects``: measured at 1M rows, that took a bbox search from 89 ms to
  10 ms, and unlike a geometry column these give parquet row-group statistics
  to prune with.

What the mirror deliberately does **not** store is the rendered STAC document.
Caching it cost 69% of the file and 3.2 GB of the build's peak memory, to save
a transformation the service performs on every response anyway.
"""

from __future__ import annotations

import logging
from pathlib import Path

import duckdb

logger = logging.getLogger(__name__)

__all__ = [
    "COLLECTIONS_FILENAME",
    "GUARANTEED_COLLECTION_COLUMNS",
    "GUARANTEED_ITEM_COLUMNS",
    "ITEMS_FILENAME",
    "build_mirror",
]

ITEMS_FILENAME = "items.parquet"
COLLECTIONS_FILENAME = "collections.parquet"

#: Columns every mirror carries, whatever the published file contains.
#:
#: Passthrough alone is not enough: `apps/catalog` names these in its own SQL
#: (``ORDER BY updated``, ``datetime >= ?``, the facets), so a published file
#: that happens to omit one would produce a mirror the service cannot query.
#: They are emitted as typed NULLs instead, which keeps the schema stable and
#: turns "the harvester dropped a column" into empty results rather than a
#: binder error mid-request.
_GUARANTEED_SHARED: tuple[tuple[str, str], ...] = (
    ("title", "VARCHAR"),
    ("description", "VARCHAR"),
    ("license", "VARCHAR"),
    ("category", "VARCHAR"),
    ("language_code", "VARCHAR"),
    ("publisher", "VARCHAR"),
    ("search_text", "VARCHAR"),
    ("updated", "TIMESTAMPTZ"),
)
GUARANTEED_ITEM_COLUMNS: tuple[tuple[str, str], ...] = (
    *_GUARANTEED_SHARED,
    ("collection", "VARCHAR"),
    ("datetime", "TIMESTAMPTZ"),
    ("created", "TIMESTAMPTZ"),
    ("parquet_url", "VARCHAR"),
    ("goat:layerType", "VARCHAR"),
    ("goat:geometryType", "VARCHAR"),
    ("goat:geographical_code", "VARCHAR"),
)
GUARANTEED_COLLECTION_COLUMNS: tuple[tuple[str, str], ...] = (
    *_GUARANTEED_SHARED,
    ("datetime", "TIMESTAMPTZ"),
)

#: Physical row order of the written files -- what a reader's row-group
#: pruning has to work with, since the service queries the parquet through a
#: view rather than loading it into a table.
#:
#: `updated DESC` first because it is the default sort of every listing, so
#: the first page comes out of the first row group. `collection` second is
#: nearly free and buys per-collection pruning: in the real catalog a
#: collection's items all share one harvest timestamp (median 1 distinct
#: `updated` per collection), so a collection's rows stay contiguous inside a
#: timestamp run. Both columns are guaranteed, so this always binds.
#:
#: Honest scope: at today's 10.8k items each file is a *single* row group, so
#: this changes nothing yet -- it starts paying above DuckDB's 122,880-row
#: group size, on the way to the 500k-1M target. Measured gains at a synthetic
#: 1M rows are ~1.2-1.6x over unsorted across listing/bbox/free-text shapes.
_ITEM_CLUSTER_ORDER = "updated DESC NULLS LAST, collection NULLS LAST, id"
_COLLECTION_CLUSTER_ORDER = "updated DESC NULLS LAST, id"


def _columns(con: duckdb.DuckDBPyConnection, path: Path) -> dict[str, str]:
    rows = con.execute(
        "DESCRIBE SELECT * FROM read_parquet(?)", [path.as_posix()]
    ).fetchall()
    return {row[0]: row[1] for row in rows}


def _quoted(name: str) -> str:
    """Quote an identifier -- published names contain colons."""
    escaped = name.replace('"', '""')
    return f'"{escaped}"'


def _ref(name: str, alias: str = "") -> str:
    """A column reference, table-qualified when an alias is given.

    Qualification is required on the item side: the mirror joins items to
    collections and the two share column names (``id``, ``title``,
    ``stac_extensions``, ...), so a bare reference is ambiguous.
    """
    return f"{alias}.{_quoted(name)}" if alias else _quoted(name)


def _opt(
    columns: dict[str, str],
    name: str,
    expr: str | None = None,
    alias: str = "",
) -> str:
    """``expr`` when ``name`` is present in the file, else ``NULL``."""
    if name not in columns:
        return "NULL"
    return expr if expr is not None else _ref(name, alias)


def _text(expr: str) -> str:
    """Force a derived scalar to VARCHAR.

    A column the published file lacks degrades to a bare ``NULL``, which DuckDB
    types as INTEGER -- so the mirror would carry, say, an integer
    ``language_code``. The registry classifies by type, so that column silently
    stops being facetable, and a CQL2 filter on it compares against the wrong
    type. Casting keeps the schema stable whether or not the source has it.
    """
    return f"CAST({expr} AS VARCHAR)"


def _probe(con: duckdb.DuckDBPyConnection, path: Path, expr: str, alias: str) -> str:
    """``expr`` if it actually binds against this file, else ``NULL``.

    :func:`_opt` only checks that a *column* exists, which is not enough for the
    nested paths this converter reads (``assets.data.href``,
    ``summaries.updated.maximum``, ``providers[1].name``,
    ``themes[1].concepts[1].id``, ``extent.spatial.bbox[1][1]``). A published
    STRUCT whose member list differs is a **bind error that fails the whole
    build**, not a NULL -- and that is not hypothetical: the collections
    captured from the bucket in ``tests/fixtures/real`` carry a ``summaries``
    struct with no ``updated`` member, which took the mirror down entirely.

    Since the published schema is not ours to pin, the only reliable test is to
    ask DuckDB. This binds the expression against zero rows once per expression
    at build time -- no per-row cost, and it tolerates any shape change in the
    published structs, not just the ones we thought to anticipate.
    """
    try:
        con.execute(
            f"SELECT {expr} FROM read_parquet('{path.as_posix()}') {alias} LIMIT 0"
        )
    except duckdb.Error:
        logger.info("published schema lacks %s; emitting NULL", expr)
        return "NULL"
    return expr


def _geometry_expr(columns: dict[str, str], alias: str = "") -> str:
    """A geometry-typed expression for the geometry column, or ``NULL``.

    DuckDB only surfaces a parquet geometry column as ``GEOMETRY`` when the
    file carries GeoParquet ``geo`` metadata; without it the same bytes read
    back as ``BLOB`` (raw WKB) and every spatial function refuses them. The
    published ``items.parquet`` does carry that metadata -- but
    ``collections.parquet`` does not, so the two spellings already coexist
    upstream and a converter that assumed one of them would break on the
    other.
    """
    if "geometry" not in columns:
        return "NULL"
    ref = _ref("geometry", alias)
    if columns["geometry"].strip().upper().startswith("BLOB"):
        return f"ST_GeomFromWKB({ref})"
    return ref


def _keywords_text(columns: dict[str, str], alias: str = "") -> str:
    """``keywords`` as a plain string, whatever shape it is published in.

    STAC's ``keywords`` is an array of strings, but the flat mirror has also
    seen it published as a single string; both flatten to text here so
    :func:`_search_text_expr` does not have to care.
    """
    if "keywords" not in columns:
        return "NULL"
    ref = _ref("keywords", alias)
    declared = columns["keywords"].strip().upper()
    if declared.endswith("[]") or declared.startswith("LIST"):
        return f"array_to_string({ref}, ' ')"
    return f"{ref}::VARCHAR"


def _search_text_expr(columns: dict[str, str], alias: str = "") -> str:
    """One lowercase haystack per row, for the free-text (``q``) filter.

    Precomputed here rather than assembled per query for two reasons: the
    service scans this single column instead of three (a projection of ~80 MB
    at 1M items rather than the whole file), and the concatenation + case
    folding happen once per harvest instead of once per request.

    The fields are the ones the STAC free-text extension names -- title,
    description, keywords -- and nothing else. Widening it to publisher or
    category would make ``q`` quietly overlap the facet filters, so those stay
    separately filterable instead.

    ``concat_ws`` skips NULL arguments, so a row missing any of the three still
    produces a usable haystack rather than NULL.
    """
    parts = [
        _opt(columns, "title", alias=alias),
        _opt(columns, "description", alias=alias),
        _keywords_text(columns, alias),
    ]
    present = [p for p in parts if p != "NULL"]
    if not present:
        return "NULL"
    return f"lower(concat_ws(' ', {', '.join(present)}))"


def _envelope_columns(geom_expr: str, prefix: str = "bbox") -> str:
    """Four ``DOUBLE`` envelope columns for a geometry expression.

    Cheap numeric comparisons on these eliminate almost every row before the
    exact ``ST_Intersects`` runs, and -- being plain scalars -- they also land in
    the parquet's per-row-group min/max statistics, so whole row groups can be
    skipped without being read.
    """
    if geom_expr == "NULL":
        return ", ".join(
            f"NULL::DOUBLE AS {prefix}_{part}"
            for part in ("xmin", "ymin", "xmax", "ymax")
        )
    return ", ".join(
        f"ST_{fn}({geom_expr}) AS {prefix}_{part}"
        for fn, part in (
            ("XMin", "xmin"),
            ("YMin", "ymin"),
            ("XMax", "xmax"),
            ("YMax", "ymax"),
        )
    )


def _first_theme(columns: dict[str, str], alias: str = "") -> str:
    """The dataset's category: the first concept of the first theme block.

    Read from the item first and the collection second (see the item SELECT's
    ``COALESCE``). Category is a dataset-level attribute, like ``license`` and
    ``publisher`` which only exist on the collection, so the collection is the
    natural fallback -- and it keeps the facet working if item-level ``themes``
    ever disappears the way the item ``type`` column did.
    """
    return _opt(columns, "themes", f"{_ref('themes', alias)}[1].concepts[1].id")


def _fill_missing(
    produced: set[str], guaranteed: tuple[tuple[str, str], ...]
) -> list[str]:
    """Typed NULLs for guaranteed columns the source did not supply."""
    return [
        f"NULL::{sql_type} AS {_quoted(name)}"
        for name, sql_type in guaranteed
        if name not in produced
    ]


def _passthrough(columns: dict[str, str], alias: str, exclude: set[str]) -> list[str]:
    """Every published column, verbatim, minus the ones we replace.

    Passthrough rather than re-encoding is the whole point of dropping the
    ``document`` blob: the published file already types ``assets``/``links``/
    ``table:columns`` as real STRUCTs, and the service rebuilds the STAC JSON
    from them per response. A property the harvester adds tomorrow flows
    through here with no code change -- the same drift-tolerance the blob gave,
    without paying to render 1.3 GB of JSON at every harvest.
    """
    return [
        f"{_ref(name, alias)} AS {_quoted(name)}"
        for name in columns
        if name not in exclude
    ]


def build_mirror(
    items_path: Path,
    collections_path: Path,
    out_items: Path,
    out_collections: Path,
    con: duckdb.DuckDBPyConnection | None = None,
) -> tuple[int, int]:
    """Write the two mirror files; returns ``(item rows, collection rows)``.

    Items and collections stay in separate files, as they are published and as
    pgstac stores them. Merged into one table they would need a schema that is
    the union of both -- ``extent``/``providers``/``summaries`` null on every
    item row, ``assets``/``table:columns`` null on every collection row -- and
    every item query would carry a discriminator predicate over rows it can
    never return. Measured over 1.77M rows, separate relations were faster on
    every query shape (facet filters 0.37x, collection listing 0.38x).

    ``con`` is injectable so a caller that already has a DuckDB connection
    (with the spatial/json extensions loaded) can reuse it.
    """
    owns_connection = con is None
    if con is None:
        con = duckdb.connect()
        con.execute("INSTALL spatial; LOAD spatial;")
        con.execute("INSTALL json; LOAD json;")
    try:
        items = _columns(con, items_path)
        collections = _columns(con, collections_path)
        logger.info(
            "building mirror from %d item columns and %d collection columns",
            len(items),
            len(collections),
        )

        def item_expr(expr: str) -> str:
            return _probe(con, items_path, expr, "i")

        def coll_expr(expr: str) -> str:
            return _probe(con, collections_path, expr, "c")

        # Denormalised from the Collection onto every item row: the catalog page
        # facets *datasets* by licence and publisher, and neither exists on a
        # published item. Doing the join once per harvest is what keeps a
        # faceted search a single-relation scan.
        publisher = coll_expr(_opt(collections, "providers", "c.providers[1].name"))
        layer_type = "COALESCE({}, {}, 'feature')".format(
            item_expr(_opt(items, "goat:layerType", 'i."goat:layerType"')),
            coll_expr(_opt(collections, "goat:layerType", 'c."goat:layerType"')),
        )
        geographical_code = "COALESCE({}, {})".format(
            item_expr(
                _opt(items, "goat:geographical_code", 'i."goat:geographical_code"')
            ),
            coll_expr(
                _opt(
                    collections, "goat:geographical_code", 'c."goat:geographical_code"'
                )
            ),
        )

        # Names we compute ourselves and therefore must not also pass through.
        # Everything else keeps its published name, so `goat:geometryType` stays
        # `goat:geometryType` -- the column and the STAC property it becomes are
        # the same word, and the registry seeds already know it.
        item_derived = {
            "geometry",
            "goat:layerType",
            "goat:geographical_code",
            "license",
            "publisher",
            "category",
            "search_text",
            "parquet_url",
            "language_code",
        }
        item_select = f"""
            SELECT
                {", ".join(_passthrough(items, "i", item_derived))},
                {_geometry_expr(items, "i")}                  AS geometry,
                {_text(layer_type)}                           AS "goat:layerType",
                {_text(geographical_code)}                    AS "goat:geographical_code",
                {_text(f"COALESCE({item_expr(_opt(items, 'license', 'i.license'))}, "
                       f"{coll_expr(_opt(collections, 'license', 'c.license'))})")} AS license,
                {_text(publisher)}                             AS publisher,
                {_text(f"COALESCE({item_expr(_first_theme(items, 'i'))}, "
                       f"{coll_expr(_first_theme(collections, 'c'))})")} AS category,
                {_text(_search_text_expr(items, "i"))}         AS search_text,
                {_text(item_expr(_opt(items, "language", "i.language.code")))} AS language_code,
                {_text(item_expr(_opt(items, "assets", "i.assets.data.href")))} AS parquet_url
            FROM read_parquet('{items_path.as_posix()}') i
            LEFT JOIN read_parquet('{collections_path.as_posix()}') c
                ON c.id = i.collection
        """

        # A Collection's spatial extent is a bbox, not a geometry column, so the
        # mirror's geometry is that envelope. Collection-level spatial filtering
        # is therefore bbox-precise, which is all a STAC extent is.
        collection_geometry = _probe(
            con,
            collections_path,
            _opt(
                collections,
                "extent",
                "ST_MakeEnvelope(extent.spatial.bbox[1][1], extent.spatial.bbox[1][2],"
                " extent.spatial.bbox[1][3], extent.spatial.bbox[1][4])",
            ),
            "",
        )
        collection_derived = {
            "geometry",
            "datetime",
            "publisher",
            "category",
            "search_text",
            "updated",
            "language_code",
        }
        collection_select = f"""
            SELECT
                {", ".join(_passthrough(collections, "", collection_derived))},
                {collection_geometry}                          AS geometry,
                {_text(_probe(con, collections_path, _opt(collections, "providers", "providers[1].name"), ""))} AS publisher,
                {_text(_probe(con, collections_path, _first_theme(collections), ""))} AS category,
                {_text(_search_text_expr(collections))}        AS search_text,
                {_text(_probe(con, collections_path, _opt(collections, "language", "language.code"), ""))} AS language_code,
                {_probe(con, collections_path, _opt(collections, "summaries", "TRY_CAST(summaries.updated.maximum AS TIMESTAMPTZ)"), "")} AS updated,
                {_probe(con, collections_path, _opt(collections, "extent", "TRY_CAST(extent.temporal.interval[1][1] AS TIMESTAMPTZ)"), "")} AS datetime
            FROM read_parquet('{collections_path.as_posix()}')
        """

        # Bundle membership, precomputed. `grouped=True` search shows one card
        # per bundle (`coalesce(collection, id)`), which the service used to
        # answer with a GROUP BY over every item row -- ~1M groups and about a
        # gigabyte of hash table per request, on data that cannot change between
        # harvests. Computing it once here turns that request into a filter on
        # `is_representative` plus a column read of `member_count`.
        #
        # `group_geometry` is the union envelope of the bundle's members, so a
        # spatial filter in grouped mode still matches a bundle when *any*
        # member falls in the box (the previous GROUP BY semantics). An envelope
        # can over-include, never under-include -- the same precision a STAC
        # Collection extent gives.
        # "Most recently updated, ties broken by id". Safe to bind
        # unconditionally: `updated` is a guaranteed column, so it is a typed
        # NULL rather than a bind error when the published file omits it.
        representative_order = "updated DESC NULLS LAST, id"
        item_produced = (set(items) - item_derived) | item_derived
        collection_produced = (
            set(collections) - collection_derived
        ) | collection_derived
        item_fill = _fill_missing(item_produced, GUARANTEED_ITEM_COLUMNS)
        collection_fill = _fill_missing(
            collection_produced, GUARANTEED_COLLECTION_COLUMNS
        )
        if item_fill:
            item_select = f"SELECT *, {', '.join(item_fill)} FROM ({item_select})"
        if collection_fill:
            collection_select = (
                f"SELECT *, {', '.join(collection_fill)} FROM ({collection_select})"
            )

        grouped_items = f"""
            SELECT
                * EXCLUDE (group_key),
                {_envelope_columns("geometry")},
                {_envelope_columns("ST_Envelope_Agg(geometry) OVER w", "group_bbox")},
                count(*) OVER w                                AS member_count,
                row_number() OVER (
                    PARTITION BY group_key
                    ORDER BY {representative_order}
                ) = 1                                          AS is_representative,
                ST_Envelope_Agg(geometry) OVER w                AS group_geometry
            FROM (
                SELECT *, coalesce(collection, id) AS group_key
                FROM ({item_select})
            )
            WINDOW w AS (PARTITION BY group_key)
        """
        # A collection row is not a bundle member, so it carries the count of
        # its own items (what `/stac/resolve` used to run a second query for).
        grouped_collections = f"""
            SELECT
                c.*,
                {_envelope_columns("c.geometry")},
                coalesce(m.member_count, 0)                     AS member_count
            FROM ({collection_select}) c
            LEFT JOIN (
                SELECT collection, count(*) AS member_count
                FROM read_parquet('{items_path.as_posix()}')
                WHERE collection IS NOT NULL
                GROUP BY collection
            ) m ON m.collection = c.id
        """

        for out, query, order in (
            (out_items, grouped_items, _ITEM_CLUSTER_ORDER),
            (out_collections, grouped_collections, _COLLECTION_CLUSTER_ORDER),
        ):
            out.parent.mkdir(parents=True, exist_ok=True)
            con.execute(
                f"COPY (SELECT * FROM ({query}) ORDER BY {order}) "
                f"TO '{out.as_posix()}' (FORMAT PARQUET)"
            )

        def _count(path: Path) -> int:
            row = con.execute(
                "SELECT count(*) FROM read_parquet(?)", [path.as_posix()]
            ).fetchone()
            return int(row[0]) if row else 0

        return _count(out_items), _count(out_collections)
    finally:
        if owns_connection:
            con.close()
