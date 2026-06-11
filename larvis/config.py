from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    vault_path: Path
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"
    ollama_embed_model: str = "nomic-embed-text"
    chroma_host: str = "http://localhost:8000"
    chroma_collection: str = "vault"
    rag_top_k: int = 5
    chunk_size: int = 500
    chunk_overlap: int = 50
    ynab_api_key: str = ""
    ynab_budget_id: str = "last-used"
    gcal_credentials_path: str = ".gcal/credentials.json"
    gcal_token_path: str = ".gcal/token.json"
    gcal_calendar_ids: str = "primary"
    gcal_work_start: str = "09:00"
    gcal_work_end: str = "17:00"


settings = Settings()
