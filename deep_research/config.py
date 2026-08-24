"""Configurações compartilhadas da aplicação."""

import json
import os

from dotenv import load_dotenv


load_dotenv()

MAX_FILE_SIZE = 20 * 1024 * 1024
MAX_RESEARCH_ROUNDS = 3
MAX_SUBQUESTIONS = 4
RETRIEVAL_CANDIDATES = 10
RERANK_TOP_N = 10
RERANK_TIMEOUT_SECONDS = 30
DOCLING_MAX_TOKENS = 512
DOCLING_TOKENIZER_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text-v1.5")
EMBEDDING_BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", "16"))
EMBEDDING_TIMEOUT_SECONDS = float(
    os.getenv("EMBEDDING_TIMEOUT_SECONDS", "60")
)
EMBEDDING_MAX_RETRIES = int(os.getenv("EMBEDDING_MAX_RETRIES", "2"))
GUARDRAIL_MAX_QUESTION_CHARS = int(
    os.getenv("GUARDRAIL_MAX_QUESTION_CHARS", "2000")
)
GUARDRAIL_MAX_CLARIFICATION_CHARS = int(
    os.getenv("GUARDRAIL_MAX_CLARIFICATION_CHARS", "1000")
)
GUARDRAIL_USE_LLM = os.getenv("GUARDRAIL_USE_LLM", "true").lower() in {
    "1",
    "true",
    "yes",
}


def _load_guardrail_blocked_terms() -> tuple[str, ...]:
    """Carrega palavras bloqueadas de uma lista JSON ou texto separado por vírgulas."""
    raw = os.getenv("GUARDRAIL_BLOCKED_TERMS", "[]").strip()
    if not raw:
        return ()

    try:
        values = json.loads(raw)
    except json.JSONDecodeError:
        values = [value.strip() for value in raw.split(",")]

    if not isinstance(values, list) or not all(
        isinstance(value, str) for value in values
    ):
        raise RuntimeError(
            "GUARDRAIL_BLOCKED_TERMS deve ser uma lista JSON de textos."
        )
    return tuple(value.strip() for value in values if value.strip())


GUARDRAIL_BLOCKED_TERMS = _load_guardrail_blocked_terms()


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Configure {name} no arquivo .env")
    return value
