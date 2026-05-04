"""Application settings."""

from common.config import BaseAppSettings


class Settings(BaseAppSettings):
    data_source: str = "postgres"
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "mlpipeline"
    postgres_user: str = "admin"
    postgres_password: str = "password"
    model_dir: str = "ml/registry/artifacts"
    model_path: str = "ml/registry/artifacts/latest/model.lgb"

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )
