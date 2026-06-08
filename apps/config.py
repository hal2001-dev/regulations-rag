from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # OpenAI
    openai_api_key: str = ""

    # Postgres
    postgres_user: str = "regulations"
    postgres_password: str = "regulations"
    postgres_db: str = "regulations"
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_url: str = ""

    # Qdrant
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "regulations"

    # Models
    embedding_model: str = "intfloat/multilingual-e5-large"
    embedding_dim: int = 1024
    sparse_model: str = "Qdrant/bm25"
    llm_model: str = "gpt-4o-mini"
    # fastembed 가 지원하는 다국어 cross-encoder (한국어 포함). bge-reranker-v2-m3 는 fastembed 미지원.
    reranker_model: str = "jinaai/jina-reranker-v2-base-multilingual"
    rerank_enabled: bool = True
    rerank_candidate_k: int = 60  # RRF 상위 N 을 rerank 입력으로 (별표 다수 환경서 정답 누락 방지, ISSUE-001)
    linearize_appendix_tables: bool = True  # 별표 표 → 행 단위 자연어 청크 (ISSUE-001)
    ocr_lang: str = "ko-KR"

    # Dirs
    ingest_dir: Path = Path("./ingest")
    data_dir: Path = Path("./data")

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "http://localhost:3001"

    # Worker
    indexer_poll_interval_sec: float = 2.0
    indexer_batch_size: int = 1

    # LangGraph
    langgraph_checkpoint_url: str = ""

    def db_url(self) -> str:
        if self.postgres_url:
            return self.postgres_url
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    def checkpoint_url(self) -> str:
        return self.langgraph_checkpoint_url or self.db_url()

    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
