from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"


@dataclass(frozen=True)
class Settings:
    database_path: Path = DATA_DIR / "raw" / "chinook" / "Chinook_Sqlite.sqlite"
    ddl_path: Path = DATA_DIR / "raw" / "chinook" / "Chinook_Sqlite.sql"
    schema_metadata_path: Path = DATA_DIR / "processed" / "schema_metadata.json"
    semantic_layer_path: Path = DATA_DIR / "processed" / "semantic_layer.json"
    demo_questions_path: Path = DATA_DIR / "processed" / "demo_questions.json"
    spider_database_root: Path = DATA_DIR / "raw" / "spider"
    spider_metadata_dir: Path = DATA_DIR / "processed" / "spider" / "metadata"
    spider_semantic_layer_dir: Path = DATA_DIR / "processed" / "spider" / "semantic_layers"
    spider_examples_path: Path = DATA_DIR / "processed" / "spider" / "examples.json"
    enable_spider_rag: bool = True
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = ""
    llm_timeout_seconds: int = 45
    llm_enable_thinking: bool = False
    llm_analysis_model: str = ""
    llm_thinking_model: str = ""
    llm_generation_model: str = ""
    llm_repair_model: str = ""
    llm_answer_model: str = ""


def get_settings() -> Settings:
    api_key = (
        os.getenv("NL2SQL_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or os.getenv("DASHSCOPE_API_KEY", "")
    )
    base_url = (
        os.getenv("NL2SQL_BASE_URL")
        or os.getenv("OPENAI_BASE_URL")
        or ("https://dashscope.aliyuncs.com/compatible-mode/v1" if os.getenv("DASHSCOPE_API_KEY") else "https://api.openai.com/v1")
    )
    model = (
        os.getenv("NL2SQL_MODEL")
        or os.getenv("OPENAI_MODEL")
        or os.getenv("WRITINGTUTOR_VLM_MODEL")
        or ("qwen3.5-flash-2026-02-23" if os.getenv("DASHSCOPE_API_KEY") else "")
    )

    return Settings(
        llm_api_key=api_key,
        llm_base_url=base_url,
        llm_model=model,
        enable_spider_rag=os.getenv("NL2SQL_ENABLE_SPIDER_RAG", "true").lower() == "true",
        llm_timeout_seconds=int(os.getenv("NL2SQL_TIMEOUT_SECONDS", "45")),
        llm_enable_thinking=(os.getenv("NL2SQL_ENABLE_THINKING", "true").lower() == "true") if "dashscope.aliyuncs.com" in base_url else False,
        llm_analysis_model=os.getenv("NL2SQL_ANALYSIS_MODEL") or model,
        llm_thinking_model=os.getenv("NL2SQL_THINKING_MODEL") or model,
        llm_generation_model=os.getenv("NL2SQL_GENERATION_MODEL") or model,
        llm_repair_model=os.getenv("NL2SQL_REPAIR_MODEL") or model,
        llm_answer_model=os.getenv("NL2SQL_ANSWER_MODEL") or model,
    )
