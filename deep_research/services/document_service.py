"""Caso de uso de preparação e indexação de PDFs e CSVs."""

import logging
from pathlib import Path
from time import perf_counter

from deep_research.config import DOCLING_MAX_TOKENS
from deep_research.models import UploadResponse

from .docling_service import count_chunk_tokens, create_chunks
from .csv_service import create_csv_chunks
from .vectorstore_service import index_chunks


logger = logging.getLogger("uvicorn.error.deep_research.document")


def prepare_document(content: bytes, filename: str) -> UploadResponse:
    preparation_started_at = perf_counter()
    logger.info(
        "Preparação de documento: iniciada [arquivo=%r tamanho_bytes=%d].",
        filename,
        len(content),
    )

    phase = "identificacao_tipo"
    phase_started_at = perf_counter()
    logger.info(
        "Preparação de documento: fase iniciada [arquivo=%r fase=%s].",
        filename,
        phase,
    )
    file_type = Path(filename).suffix.lower().lstrip(".")
    logger.info(
        "Preparação de documento: fase concluída "
        "[arquivo=%r fase=%s tipo=%s duracao_ms=%.2f].",
        filename,
        phase,
        file_type,
        (perf_counter() - phase_started_at) * 1000,
    )

    try:
        phase = "extracao_e_chunking"
        phase_started_at = perf_counter()
        logger.info(
            "Preparação de documento: fase iniciada "
            "[arquivo=%r fase=%s metodo=%s].",
            filename,
            phase,
            "csv_rows" if file_type == "csv" else "docling_hybrid",
        )
        if file_type == "csv":
            chunks, row_count = create_csv_chunks(content, filename)
            page_count = None
            chunking_method = "csv_rows"
        else:
            chunks, page_count = create_chunks(content, filename)
            row_count = None
            chunking_method = "docling_hybrid"
        logger.info(
            "Preparação de documento: fase concluída "
            "[arquivo=%r fase=%s metodo=%s chunks=%d paginas=%s linhas=%s "
            "duracao_ms=%.2f].",
            filename,
            phase,
            chunking_method,
            len(chunks),
            page_count,
            row_count,
            (perf_counter() - phase_started_at) * 1000,
        )

        phase = "calculo_metricas"
        phase_started_at = perf_counter()
        logger.info(
            "Preparação de documento: fase iniciada [arquivo=%r fase=%s chunks=%d].",
            filename,
            phase,
            len(chunks),
        )
        token_counts = count_chunk_tokens(chunks)
        minimum_chunk_tokens = min(token_counts)
        average_chunk_tokens = round(sum(token_counts) / len(token_counts))
        maximum_chunk_tokens = max(token_counts)
        average_chunk_characters = round(
            sum(len(chunk.page_content) for chunk in chunks) / len(chunks)
        )
        logger.info(
            "Preparação de documento: fase concluída "
            "[arquivo=%r fase=%s tokens_min=%d tokens_media=%d tokens_max=%d "
            "caracteres_media=%d duracao_ms=%.2f].",
            filename,
            phase,
            minimum_chunk_tokens,
            average_chunk_tokens,
            maximum_chunk_tokens,
            average_chunk_characters,
            (perf_counter() - phase_started_at) * 1000,
        )

        phase = "indexacao"
        phase_started_at = perf_counter()
        logger.info(
            "Preparação de documento: fase iniciada [arquivo=%r fase=%s chunks=%d].",
            filename,
            phase,
            len(chunks),
        )
        document_id = index_chunks(chunks)
        logger.info(
            "Preparação de documento: fase concluída "
            "[arquivo=%r fase=%s documento_id=%s duracao_ms=%.2f].",
            filename,
            phase,
            document_id,
            (perf_counter() - phase_started_at) * 1000,
        )

        response = UploadResponse(
            document_id=document_id,
            filename=filename,
            file_type=file_type,
            pages=page_count,
            rows=row_count,
            chunks=len(chunks),
            chunking_method=chunking_method,
            max_tokens_per_chunk=DOCLING_MAX_TOKENS,
            minimum_chunk_tokens=minimum_chunk_tokens,
            average_chunk_tokens=average_chunk_tokens,
            maximum_chunk_tokens=maximum_chunk_tokens,
            average_chunk_characters=average_chunk_characters,
        )
    except Exception:
        logger.exception(
            "Preparação de documento: falhou "
            "[arquivo=%r fase=%s duracao_total_ms=%.2f].",
            filename,
            phase,
            (perf_counter() - preparation_started_at) * 1000,
        )
        raise

    logger.info(
        "Preparação de documento: concluída "
        "[arquivo=%r documento_id=%s chunks=%d duracao_total_ms=%.2f].",
        filename,
        document_id,
        len(chunks),
        (perf_counter() - preparation_started_at) * 1000,
    )
    return response
