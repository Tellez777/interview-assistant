"""Configuración centralizada de la app, leída desde .env.

Todo lo que otros módulos necesiten parametrizar (modelos, rutas, proveedor
de LLM) vive aquí. Nada de leer os.environ suelto en otros archivos.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- LLM ---
    llm_provider: str = "anthropic"
    anthropic_api_key: str = ""

    openai_compat_base_url: str = ""
    openai_compat_api_key: str = ""
    openai_compat_model: str = ""
    # Modelo más grande para preguntas técnicas/de código en vivo (ver
    # app.live.pipeline). Vacío = usa openai_compat_model para todo.
    openai_compat_technical_model: str = ""

    # --- ASR ---
    asr_device: str = "cuda"
    asr_compute_type: str = "int8_float16"
    asr_model: str = "small.en"
    asr_realtime_model: str = "tiny.en"
    # Variantes multilingües para Live Mode en español (ver app.live.manager):
    # los modelos ".en" son especializados en inglés y no sirven para otro
    # idioma — no es solo una bandera, son pesos de modelo distintos.
    asr_model_es: str = "small"
    asr_realtime_model_es: str = "tiny"

    # --- App ---
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    data_dir: Path = Path("./data")

    @property
    def profile_path(self) -> Path:
        return self.data_dir / "profile.json"

    @property
    def questions_path(self) -> Path:
        return self.data_dir / "questions.yaml"

    @property
    def answers_dir(self) -> Path:
        return self.data_dir / "answers"

    @property
    def practice_db_path(self) -> Path:
        return self.data_dir / "practice.db"

    @property
    def live_db_path(self) -> Path:
        return self.data_dir / "live.db"


settings = Settings()
