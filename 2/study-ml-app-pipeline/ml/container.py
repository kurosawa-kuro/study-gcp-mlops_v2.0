"""DI container."""

from dataclasses import dataclass

from ml.data.port import DatasetReader
from ml.data.postgres_dataset import PostgresDatasetAdapter
from ml.registry.filesystem_model_store import FilesystemModelStore
from ml.registry.port import ModelStore
from ml.serving.port import Predictor
from ml.serving.predictor import ModelStorePredictor


@dataclass(frozen=True)
class Container:
    dataset: DatasetReader
    model_store: ModelStore
    predictor: Predictor


def build_container(settings) -> Container:
    dataset = PostgresDatasetAdapter(settings.postgres_dsn)
    model_store = FilesystemModelStore(settings.model_dir)
    predictor = ModelStorePredictor(model_store)
    return Container(dataset=dataset, model_store=model_store, predictor=predictor)
