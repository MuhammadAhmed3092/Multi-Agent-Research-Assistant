"""
memory/vector_store.py — ChromaDB vector store helper (Phase 5).
Used by pdf_reader.py for persistent embedding storage.
"""

from config import settings


def get_client():
    import chromadb
    return chromadb.PersistentClient(path=settings.chroma_persist_dir)


def get_collection(name: str = "pdf_chunks"):
    return get_client().get_or_create_collection(name)
