"""Caso de uso de preparação e indexação de PDFs e CSVs."""

from pathlib import Path

from deep_research.config import DOCLING_MAX_TOKENS
from deep_research.models import UploadResponse

from .docling_service import count_chunk_tokens, create_chunks
from .csv_service import create_csv_chunks
from .vectorstore_service import index_chunks


def prepare_document(content: bytes, filename: str) -> UploadResponse:
    file_type = Path(filename).suffix.lower().lstrip(".")
    if file_type == "csv":
        chunks, row_count = create_csv_chunks(content, filename)
        page_count = None
        chunking_method = "csv_rows"
    else:
        chunks, page_count = create_chunks(content, filename)
        row_count = None
        chunking_method = "docling_hybrid"

    token_counts = count_chunk_tokens(chunks)
    document_id = index_chunks(chunks)
    return UploadResponse(
        document_id=document_id,
        filename=filename,
        file_type=file_type,
        pages=page_count,
        rows=row_count,
        chunks=len(chunks),
        chunking_method=chunking_method,
        max_tokens_per_chunk=DOCLING_MAX_TOKENS,
        minimum_chunk_tokens=min(token_counts),
        average_chunk_tokens=round(sum(token_counts) / len(token_counts)),
        maximum_chunk_tokens=max(token_counts),
        average_chunk_characters=round(
            sum(len(chunk.page_content) for chunk in chunks) / len(chunks)
        ),
    )
