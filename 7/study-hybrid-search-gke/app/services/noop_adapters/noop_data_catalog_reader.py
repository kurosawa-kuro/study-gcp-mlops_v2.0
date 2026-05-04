"""Null ``DataCatalogReader`` for local / disabled-search boot paths."""

from __future__ import annotations

from app.services.protocols.data_catalog_reader import DataCatalogReader, DataCatalogSnapshot


class NoopDataCatalogReader(DataCatalogReader):
    def read_snapshot(self) -> DataCatalogSnapshot:
        return DataCatalogSnapshot(tables=[])
