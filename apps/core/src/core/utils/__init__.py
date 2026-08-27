# Standard library imports
import asyncio
import os
import random
import re
import shutil
import string
import subprocess
import time
import zipfile
from functools import wraps
from typing import Any, AsyncIterator, Callable, TypeVar, cast

import aiohttp

# Third party imports
from fastapi import UploadFile
from geoalchemy2.shape import to_shape
from geojson import Feature, FeatureCollection
from geojson import loads as geojsonloads
from rich import print as print
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from core.core.config import settings
from core.utils.partial import optional  # canonical single impl (re-exported)


async def table_exists(db: AsyncSession, schema_name: str, table_name: str) -> bool:
    sql_check_table = (
        select(func.count())
        .where(text("table_name = :table_name AND table_schema = :schema_name"))
        .select_from(text("information_schema.tables"))
    )
    params = {"table_name": table_name, "schema_name": schema_name}
    table_exists = await db.execute(sql_check_table, params)
    result = table_exists.scalar()
    return result is not None and result > 0


def delete_file(file_path: str) -> None:
    """Delete file from disk."""

    if os.path.exists(file_path):
        os.remove(file_path)


def delete_dir(dir_path: str) -> None:
    """Delete file from disk."""

    if os.path.exists(dir_path):
        shutil.rmtree(dir_path)


def create_dir(dir_path: str) -> None:
    """Create directory if it does not exist."""
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)


def print_hashtags() -> None:
    print(
        "#################################################################################################################"
    )


def print_info(message: str) -> None:
    print(f"[bold green]INFO[/bold green]: {message}")


def print_warning(message: str) -> None:
    print(f"[bold red]WARNING[/bold red]: {message}")


F = TypeVar("F", bound=Callable[..., Any])


def timing(f: F) -> F:
    @wraps(f)
    def wrap(*args: Any, **kw: Any) -> Any:
        ts = time.time()
        result = f(*args, **kw)
        te = time.time()
        total_time = te - ts
        if total_time > 1:
            total_time = round(total_time, 2)
            total_time_string = f"{total_time} seconds"
        else:
            time_miliseconds = int((total_time) * 1000)
            total_time_string = f"{time_miliseconds} miliseconds"

        print(f"func: {f.__name__} took: {total_time_string}")

        return result

    return cast(F, wrap)


def get_random_string(length: int) -> str:
    # choose from all lowercase letter
    letters = string.ascii_lowercase
    return "".join(random.choice(letters) for i in range(length))


def sanitize_error_message(message: str) -> str:
    replacements = {
        settings.POSTGRES_SERVER: "HIDDEN_SERVER",
        settings.POSTGRES_DB: "HIDDEN_DB",
        settings.POSTGRES_USER: "HIDDEN_USER",
        settings.POSTGRES_PASSWORD: "HIDDEN_PASSWORD",
        settings.POSTGRES_PORT: "HIDDEN_PORT",
    }
    for key, value in replacements.items():
        message = message.replace(str(key), value)
    return message


async def async_delete_dir(path: str) -> None:
    """Asynchronously delete a directory and its contents."""
    try:
        await asyncio.to_thread(shutil.rmtree, path)
    except FileNotFoundError:
        pass


async def async_scandir(directory: str) -> AsyncIterator[os.DirEntry[str]]:
    for entry in os.scandir(directory):
        yield entry


async def async_zip_directory(output_filename: str, directory: str) -> None:
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, zip_directory, output_filename, directory)


def zip_directory(output_filename: str, directory: str) -> None:
    with zipfile.ZipFile(output_filename, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, _dirs, files in os.walk(directory):
            for file in files:
                zipf.write(
                    os.path.join(root, file),
                    os.path.relpath(
                        os.path.join(root, file), os.path.join(directory, "..")
                    ),
                )


def execute_cmd(cmd: str) -> None:
    subprocess.run(cmd, shell=True, check=True)


async def async_run_command(cmd: str) -> None:
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, execute_cmd, cmd)


async def check_file_size(file: UploadFile, max_size: int) -> bool:
    """
    Check the size of an uploaded file without reading it entirely into memory.
    Returns True if the file is within the allowed size, otherwise raises an HTTPException.
    """
    total_size = 0
    chunk_size = 128 * 1024  # 128KB

    while data := await file.read(chunk_size):
        total_size += len(data)
        if total_size > max_size:
            return False

    await file.seek(0)  # Reset file position for further processing if needed
    return True


async def async_get_with_retry(
    url: str, headers: dict[str, str], num_retries: int, retry_delay: int
) -> str | None:
    async with aiohttp.ClientSession() as session:
        for i in range(num_retries):
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    # Server is still processing request, retry shortly
                    if i == num_retries - 1:
                        raise Exception(
                            "GEOAPI-Server took too long to process request. It can be that the layer is not properly processed yet."
                        )
                    await asyncio.sleep(retry_delay)
                    continue
                elif response.status == 200:
                    # Server has finished processing request, break
                    result = await response.text()
                    return result
                else:
                    raise Exception(await response.text())
    return None


def hex_to_rgb(hex: str) -> tuple[int, ...]:
    hex = hex.lstrip("#")
    return tuple(int(hex[i : i + 2], 16) for i in (0, 2, 4))


def without_keys(d: dict[str, Any], keys: list[str]) -> dict[str, Any]:
    """
    Omit keys from a dict
    """
    return {x: d[x] for x in d if x not in keys}


def to_feature_collection(
    sql_result: Any,
    geometry_name: str = "geom",
    geometry_type: str = "wkb",
    exclude_properties: list[str] = [],
) -> FeatureCollection:
    """
    Generic method to convert sql result to geojson. Geometry field is expected to be in geojson or postgis hex format.
    """
    if not isinstance(sql_result, list):
        sql_result = [sql_result]

    exclude_properties.append(geometry_name)
    features = []
    for row in sql_result:
        if not isinstance(row, dict):
            dict_row = dict(row)
        else:
            dict_row = row
        geometry = None
        if dict_row.get(geometry_name) is not None:
            if geometry_type == "wkb":
                geometry = to_shape(dict_row[geometry_name])
            elif geometry_type == "geojson":
                geometry = geojsonloads(dict_row[geometry_name])

        features.append(
            Feature(
                id=dict_row.get("gid") or dict_row.get("id") or 0,
                geometry=geometry,
                properties=without_keys(dict_row, exclude_properties),
            )
        )
    return FeatureCollection(features)


def format_value_null_sql(value: Any) -> str:
    if value is None:
        return "NULL"
    else:
        return f"'{value}'"


def sanitize_filename(name: str) -> str:
    # Extract just the file name (no paths)
    name = os.path.basename(name)
    # Allow only safe chars
    name = re.sub(r"[^a-zA-Z0-9._()\-\s]", "_", name)
    return name
