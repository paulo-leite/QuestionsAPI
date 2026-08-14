"""Indexação e armazenamento em memória das coleções Chroma."""

from pathlib import Path
from threading import Lock
from uuid import uuid4

from chromadb.errors import NotFoundError
from langchain_chroma import Chroma
from langchain_core.documents import Document

from .embedding_service import get_embedding_service


vectorstores: dict[str, Chroma] = {}
_lock = Lock()
_PERSIST_DIRECTORY = "./vectorized_document"


def _collection_name(document_id: str) -> str:
    return f"document_{document_id.replace('-', '')}"


def index_chunks(chunks: list[Document]) -> str:
    document_id = str(uuid4())
    vectorstore = Chroma.from_documents(
        documents=chunks,
        embedding=get_embedding_service(),
        collection_name=_collection_name(document_id),
        persist_directory=_PERSIST_DIRECTORY,
    )
    with _lock:
        vectorstores[document_id] = vectorstore
    return document_id


def get_vectorstore(document_id: str) -> Chroma | None:
    with _lock:
        vectorstore = vectorstores.get(document_id)
        if vectorstore is not None:
            return vectorstore

        if not Path(_PERSIST_DIRECTORY).is_dir():
            return None

        try:
            vectorstore = Chroma(
                collection_name=_collection_name(document_id),
                embedding_function=get_embedding_service(),
                persist_directory=_PERSIST_DIRECTORY,
                create_collection_if_not_exists=False,
            )
        except NotFoundError:
            return None

        vectorstores[document_id] = vectorstore
        return vectorstore
