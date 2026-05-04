"""Protocol for developer-facing training / serving data previews."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class DataCatalogTablePreview:
    key: str
    title: str
    description: str
    table_fqn: str
    latest_marker: str | None
    columns: list[str]
    rows: list[dict[str, object | None]]


@dataclass(frozen=True)
class DataCatalogSnapshot:
    tables: list[DataCatalogTablePreview]


class DataCatalogReader(Protocol):
    def read_snapshot(self) -> DataCatalogSnapshot: ...
