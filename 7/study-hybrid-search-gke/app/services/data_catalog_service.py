"""Developer-facing service for previewing training / serving data tables."""

from __future__ import annotations

from app.services.protocols.data_catalog_reader import DataCatalogReader, DataCatalogSnapshot


class DataCatalogService:
    def __init__(self, *, reader: DataCatalogReader) -> None:
        self._reader = reader

    def read_snapshot(self) -> DataCatalogSnapshot:
        return self._reader.read_snapshot()
