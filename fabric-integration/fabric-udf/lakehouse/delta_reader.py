"""OneLake Delta Lake Reader for Microsoft Fabric User Data Functions.

Provides high-performance, strictly read-only access to OneLake Delta tables
via Delta-rs and PyArrow, with column projection, schema validation,
transient retry handling, and zero-write safety boundaries.
"""

import logging
import time
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc
from deltalake import DeltaTable
from deltalake.exceptions import TableNotFoundError

from .auth import OneLakeAuthManager
from .config import LakehouseReaderConfig

logger = logging.getLogger("finops_udf.lakehouse.delta_reader")


class OneLakeDeltaReader:
    """Read-only driver for Microsoft Fabric Lakehouse Delta tables on OneLake."""

    def __init__(
        self,
        auth_manager: OneLakeAuthManager | None = None,
        config: LakehouseReaderConfig | None = None,
    ) -> None:
        self.config = config or LakehouseReaderConfig.load()
        self.auth_manager = auth_manager or OneLakeAuthManager(self.config)

    def _get_storage_options(self) -> dict[str, str]:
        """Obtain storage options configured with fresh bearer token."""
        return self.auth_manager.get_storage_options()

    def get_table_metadata(self, table_name: str) -> dict[str, Any]:
        """Inspect Delta table version, file count, and schema without loading full data."""
        table_uri = self.config.get_table_uri(table_name)
        storage_options = self._get_storage_options()

        try:
            dt = DeltaTable(table_uri, storage_options=storage_options)
            version = dt.version()
            files = len(dt.file_uris())
            schema_fields = [f.name for f in dt.schema().fields]
            return {
                "accessible": True,
                "table_name": table_name,
                "uri": table_uri,
                "version": version,
                "file_count": files,
                "columns": schema_fields,
            }
        except (TableNotFoundError, FileNotFoundError) as not_found:
            return {
                "accessible": False,
                "table_name": table_name,
                "uri": table_uri,
                "error": f"Table '{table_name}' does not exist on OneLake: {not_found}",
            }
        except Exception as exc:
            return {
                "accessible": False,
                "table_name": table_name,
                "uri": table_uri,
                "error": f"Failed inspecting Delta table '{table_name}': {exc}",
            }

    def read_table(
        self,
        table_name: str,
        columns: list[str] | None = None,
        partitions: list[tuple[str, str, Any]] | None = None,
    ) -> pa.Table:
        """Read a Delta table from OneLake with column projection and transient retries.

        Args:
            table_name: Name of analytical table (e.g. resource_inventory, cost_details).
            columns: Specific column names to project to reduce network load.
            partitions: Partition filters to push down.

        Returns:
            PyArrow Table containing the selected columns.
        """
        table_uri = self.config.get_table_uri(table_name)
        max_attempts = 3
        last_error = None

        for attempt in range(1, max_attempts + 1):
            try:
                storage_options = self._get_storage_options()
                dt = DeltaTable(table_uri, storage_options=storage_options)

                if dt.version() < 0:
                    # Empty initialized table
                    return pa.table({})

                # Project columns and load PyArrow table
                arrow_table = dt.to_pyarrow_table(
                    columns=columns,
                    partitions=partitions,
                )
                return arrow_table

            except (TableNotFoundError, FileNotFoundError) as not_found:
                logger.debug(
                    "Table '%s' not found on OneLake: %s", table_name, not_found
                )
                # Return empty table if table does not exist
                return pa.table({})

            except Exception as exc:
                last_error = exc
                logger.warning(
                    "OneLake Delta read attempt %d/%d failed for '%s': %s",
                    attempt,
                    max_attempts,
                    table_name,
                    exc,
                )
                time.sleep(1.0 * attempt)

        raise RuntimeError(
            f"Failed to read OneLake Delta table '{table_name}' after {max_attempts} attempts: {last_error}"
        ) from last_error

    def read_records_as_dicts(
        self,
        table_name: str,
        columns: list[str] | None = None,
        partitions: list[tuple[str, str, Any]] | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Read Delta table and convert rows to clean native Python dictionaries.

        Uses pyarrow compute casting for timestamps to ensure zero dependence on local
        operating system timezone / tzdata files.
        """
        arrow_table = self.read_table(
            table_name, columns=columns, partitions=partitions
        )
        if arrow_table.num_rows == 0:
            return []

        if limit and limit < arrow_table.num_rows:
            arrow_table = arrow_table.slice(0, limit)

        # Convert timestamp columns to string to avoid platform-specific tzdata failures
        converted_columns: dict[str, Any] = {}
        for col_name in arrow_table.column_names:
            field = arrow_table.schema.field(col_name)
            col_data = arrow_table.column(col_name)

            if pa.types.is_timestamp(field.type):
                converted_columns[col_name] = pc.cast(col_data, pa.string()).to_pylist()
            elif pa.types.is_date(field.type):
                converted_columns[col_name] = [
                    d.isoformat() if hasattr(d, "isoformat") else str(d)
                    for d in col_data.to_pylist()
                ]
            elif pa.types.is_decimal(field.type):
                converted_columns[col_name] = col_data.to_pylist()
            else:
                converted_columns[col_name] = col_data.to_pylist()

        num_rows = arrow_table.num_rows
        records: list[dict[str, Any]] = []
        for i in range(num_rows):
            rec = {col: converted_columns[col][i] for col in arrow_table.column_names}
            records.append(rec)

        return records
