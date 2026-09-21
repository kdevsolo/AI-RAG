from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "FastAPI Learning"
    app_version: str = "0.1.0"
    postgres_user: str
    postgres_password: str
    postgres_db: str
    postgres_port: int = 5432
    postgres_host: str = "localhost"

    openai_api_key: str
    openai_chat_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    openai_embedding_dimensions: int = 1536

    # Chunking / retrieval
    chunk_size: int = 1000
    chunk_overlap: int = 200
    retrieval_top_k: int = 5

    # Uploads
    upload_dir: Path = Path("var/uploads")
    max_upload_bytes: int = 25 * 1024 * 1024

    # Temporal
    temporal_host: str = "localhost:7233"
    temporal_namespace: str = "default"
    temporal_task_queue: str = "ingestion"

    # Agent
    agent_max_tool_iterations: int = 8
    http_fetch_timeout_seconds: int = 10
    http_fetch_max_bytes: int = 200_000

    # No default: a fallback signing key would silently forge valid tokens
    # in any deployment that forgot to set JWT_SECRET.
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30

    @property
    def database_url(self) -> URL:
        return URL.create(
            drivername="postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password,  # special chars handled automatically
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )

    @property
    def checkpointer_dsn(self) -> str:
        """Plain libpq DSN (Data Source Name) for the LangGraph checkpointer's own psycopg pool."""
        return self.database_url.set(drivername="postgresql").render_as_string(hide_password=False)


config = Config()
