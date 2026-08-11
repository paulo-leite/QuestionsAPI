"""Integração com o serviço externo de embeddings."""

from functools import lru_cache

from langchain_core.embeddings import Embeddings
from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI

from deep_research.config import (
    EMBEDDING_BATCH_SIZE,
    EMBEDDING_MAX_RETRIES,
    EMBEDDING_MODEL,
    EMBEDDING_TIMEOUT_SECONDS,
    require_env,
)
from deep_research.errors import ApplicationError


class OpenAICompatibleEmbeddings(Embeddings):
    """Embeddings configuráveis expostos por uma API compatível com OpenAI."""

    def __init__(self) -> None:
        self.model = EMBEDDING_MODEL
        self.client = OpenAI(
            base_url=require_env("LLM_BASE_URL"),
            api_key=require_env("LLM_API_KEY"),
            timeout=EMBEDDING_TIMEOUT_SECONDS,
            max_retries=EMBEDDING_MAX_RETRIES,
        )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Gera embeddings em lotes para evitar requisições grandes e timeouts."""
        if not texts:
            return []

        if EMBEDDING_BATCH_SIZE < 1:
            raise RuntimeError("EMBEDDING_BATCH_SIZE deve ser maior que zero.")

        embeddings: list[list[float]] = []
        try:
            for start in range(0, len(texts), EMBEDDING_BATCH_SIZE):
                batch = texts[start:start + EMBEDDING_BATCH_SIZE]
                response = self.client.embeddings.create(
                    model=self.model,
                    input=batch,
                )
                ordered = sorted(response.data, key=lambda item: item.index)
                if len(ordered) != len(batch):
                    raise ApplicationError(
                        "O serviço de embeddings retornou um lote incompleto.",
                        502,
                    )
                embeddings.extend(item.embedding for item in ordered)
        except APITimeoutError as exc:
            raise ApplicationError(
                "O serviço de embeddings excedeu o tempo limite.", 504
            ) from exc
        except APIStatusError as exc:
            if exc.status_code == 408:
                raise ApplicationError(
                    "O serviço de embeddings excedeu o tempo limite.", 504
                ) from exc
            raise ApplicationError(
                "O serviço de embeddings recusou a indexação do documento.",
                502,
            ) from exc
        except APIConnectionError as exc:
            raise ApplicationError(
                "Não foi possível conectar ao serviço de embeddings.", 502
            ) from exc
        return embeddings

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


@lru_cache(maxsize=1)
def get_embedding_service() -> OpenAICompatibleEmbeddings:
    """Retorna o adaptador de embeddings configurado para a aplicação."""
    return OpenAICompatibleEmbeddings()
