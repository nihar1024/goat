"""GTFS importer: a gtfs.zip → member layers for a ``pt_network_gtfs`` package.

Role → file and per-role column requirements are GTFS-specific and live here;
which roles are *required* comes from the spec. Geometry roles (stops, shapes)
are emitted as GeoJSON so the runner's IOConverter builds proper geometry;
attribute roles are passed through as CSV.
"""

import csv
import io
import json
import os
import shutil
import zipfile
from typing import Dict, List, Optional, Set

import duckdb

from goatlib.dataset_packages.importers.base import (
    DatasetPackageImporter,
    ExtractedLayer,
    ValidationResult,
    register_importer,
)
from goatlib.models.dataset_package import DatasetPackageTypeName

# role -> GTFS file
_GTFS_FILE: Dict[str, str] = {
    "agency": "agency.txt",
    "stops": "stops.txt",
    "routes": "routes.txt",
    "trips": "trips.txt",
    "stop_times": "stop_times.txt",
    "calendar": "calendar.txt",
    "shapes": "shapes.txt",
}

# columns each role's file must expose (GTFS spec essentials)
_REQUIRED_COLUMNS: Dict[str, Set[str]] = {
    "agency": {"agency_name"},
    "stops": {"stop_id", "stop_lat", "stop_lon"},
    "routes": {"route_id"},
    "trips": {"route_id", "trip_id"},
    "stop_times": {"trip_id", "stop_id", "stop_sequence"},
    "calendar": {"service_id"},
    "shapes": {"shape_id", "shape_pt_lat", "shape_pt_lon", "shape_pt_sequence"},
}


class GtfsImporter(DatasetPackageImporter):
    package_type = DatasetPackageTypeName.pt_network_gtfs

    # -- validation --------------------------------------------------------

    def validate(self, source_path: str) -> ValidationResult:
        errors: List[str] = []
        if not zipfile.is_zipfile(source_path):
            return ValidationResult(
                valid=False, errors=["File is not a valid .zip archive"]
            )

        with zipfile.ZipFile(source_path) as zf:
            names = {os.path.basename(n) for n in zf.namelist()}
            detected = [r for r, f in _GTFS_FILE.items() if f in names]

            required = set(self.spec.required_role_keys())
            missing = sorted(r for r in required if _GTFS_FILE[r] not in names)

            # Column checks for every present file (required or optional).
            for role in detected:
                header = self._read_header(zf, _GTFS_FILE[role])
                needed = _REQUIRED_COLUMNS.get(role, set())
                absent = needed - set(header)
                if absent:
                    errors.append(
                        f"{_GTFS_FILE[role]} is missing column(s): "
                        f"{', '.join(sorted(absent))}"
                    )

        for role in missing:
            errors.append(f"Required GTFS file '{_GTFS_FILE[role]}' is missing")

        return ValidationResult(
            valid=not missing and not errors,
            detected_roles=detected,
            missing_required_roles=missing,
            errors=errors,
        )

    # -- extraction --------------------------------------------------------

    def extract_layers(self, source_path: str, workdir: str) -> List[ExtractedLayer]:
        layers: List[ExtractedLayer] = []
        with zipfile.ZipFile(source_path) as zf:
            names = {os.path.basename(n) for n in zf.namelist()}
            for role in self.spec.role_keys():
                fname = _GTFS_FILE[role]
                if fname not in names:
                    continue
                role_spec = self.spec.role(role)
                label = role_spec.label if role_spec else role

                if role == "stops":
                    path = self._write_points_geojson(
                        self._read_rows(zf, fname),
                        "stop_lon",
                        "stop_lat",
                        os.path.join(workdir, "stops.geojson"),
                    )
                    layers.append(
                        ExtractedLayer(
                            role=role,
                            name=label,
                            layer_type="feature",
                            geometry_type="point",
                            file_path=path,
                        )
                    )
                elif role == "shapes":
                    path = self._write_shapes_geojson(
                        self._read_rows(zf, fname),
                        os.path.join(workdir, "shapes.geojson"),
                    )
                    layers.append(
                        ExtractedLayer(
                            role=role,
                            name=label,
                            layer_type="feature",
                            geometry_type="line",
                            file_path=path,
                        )
                    )
                else:
                    # Attribute table → parquet with EVERY column as text: GTFS
                    # ids/codes are strings (e.g. "FLUO 11", zero-padded ids), so
                    # type auto-detection is wrong. DuckDB streams the file, so
                    # large tables (stop_times can be 100s of MB) stay off-heap.
                    txt_path = self._extract_member(zf, fname, workdir)
                    path = self._txt_to_parquet(
                        txt_path, os.path.join(workdir, f"{role}.parquet")
                    )
                    layers.append(
                        ExtractedLayer(
                            role=role,
                            name=label,
                            layer_type="table",
                            geometry_type=None,
                            file_path=path,
                        )
                    )
        return layers

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _resolve(zf: zipfile.ZipFile, basename: str) -> Optional[str]:
        for n in zf.namelist():
            if os.path.basename(n) == basename:
                return n
        return None

    def _read_header(self, zf: zipfile.ZipFile, basename: str) -> List[str]:
        name = self._resolve(zf, basename)
        if name is None:
            return []
        with zf.open(name) as fh:
            reader = csv.reader(io.TextIOWrapper(fh, encoding="utf-8-sig"))
            return next(reader, [])

    def _read_rows(self, zf: zipfile.ZipFile, basename: str) -> List[Dict[str, str]]:
        name = self._resolve(zf, basename)
        if name is None:
            return []
        with zf.open(name) as fh:
            reader = csv.DictReader(io.TextIOWrapper(fh, encoding="utf-8-sig"))
            return [row for row in reader]

    def _extract_member(
        self, zf: zipfile.ZipFile, basename: str, workdir: str
    ) -> str:
        """Extract a member file to workdir and return its path."""
        name = self._resolve(zf, basename)
        if name is None:
            raise ValueError(f"{basename} not found in archive")
        dest = os.path.join(workdir, basename)
        with zf.open(name) as src, open(dest, "wb") as out:
            shutil.copyfileobj(src, out)
        return dest

    @staticmethod
    def _txt_to_parquet(txt_path: str, out_path: str) -> str:
        """Convert a GTFS text file to parquet with all columns as VARCHAR.

        ``all_varchar`` disables type auto-detection — GTFS ids/codes/names are
        strings and must not be coerced to numbers. DuckDB streams the file, so
        this is memory-safe for large tables (e.g. stop_times).
        """
        src = txt_path.replace("'", "''")
        dst = out_path.replace("'", "''")
        con = duckdb.connect()
        try:
            con.execute(
                f"COPY (SELECT * FROM read_csv_auto('{src}', all_varchar=true, "
                f"header=true)) TO '{dst}' (FORMAT parquet)"
            )
        finally:
            con.close()
        return out_path

    @staticmethod
    def _write_points_geojson(
        rows: List[Dict[str, str]], lon_col: str, lat_col: str, out_path: str
    ) -> str:
        features = []
        for row in rows:
            try:
                lon = float(row[lon_col])
                lat = float(row[lat_col])
            except (KeyError, TypeError, ValueError):
                continue
            features.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [lon, lat]},
                    "properties": row,
                }
            )
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump({"type": "FeatureCollection", "features": features}, fh)
        return out_path

    @staticmethod
    def _write_shapes_geojson(rows: List[Dict[str, str]], out_path: str) -> str:
        shapes: Dict[str, List[tuple]] = {}
        for row in rows:
            try:
                shape_id = row["shape_id"]
                seq = int(row["shape_pt_sequence"])
                lon = float(row["shape_pt_lon"])
                lat = float(row["shape_pt_lat"])
            except (KeyError, TypeError, ValueError):
                continue
            shapes.setdefault(shape_id, []).append((seq, lon, lat))

        features = []
        for shape_id, pts in shapes.items():
            ordered = [[lon, lat] for _, lon, lat in sorted(pts)]
            if len(ordered) < 2:
                continue
            features.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "LineString", "coordinates": ordered},
                    "properties": {"shape_id": shape_id},
                }
            )
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump({"type": "FeatureCollection", "features": features}, fh)
        return out_path


register_importer(GtfsImporter())
