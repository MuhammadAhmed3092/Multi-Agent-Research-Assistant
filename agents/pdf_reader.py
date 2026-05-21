"""
pdf_reader.py — PDF Reader Agent.
Uses PyMuPDF to extract text, sentence-transformers for local embeddings,
and ChromaDB (local) for semantic retrieval. Fully free, runs offline.
"""

from __future__ import annotations
import uuid
from pathlib import Path
from loguru import logger

from state import (
    ResearchState, ResearchStatus, AgentName,
    Source, append_step,
)
from config import settings


def _get_or_create_collection(pdf_paths: list[str]):
    """Chunk PDFs, embed locally, store in ChromaDB. Returns the collection."""
    import chromadb
    from sentence_transformers import SentenceTransformer
    import fitz  # PyMuPDF

    client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
    collection = client.get_or_create_collection("pdf_chunks")
    model = SentenceTransformer(settings.embedding_model)

    for pdf_path in pdf_paths:
        path = Path(pdf_path)
        if not path.exists():
            logger.warning(f"[PDFReader] File not found: {pdf_path}")
            continue

        doc_id = path.stem
        # Skip if already indexed
        existing = collection.get(where={"source": doc_id})
        if existing["ids"]:
            logger.info(f"[PDFReader] Already indexed: {doc_id}")
            continue

        logger.info(f"[PDFReader] Indexing: {pdf_path}")
        doc = fitz.open(pdf_path)
        full_text = " ".join(page.get_text() for page in doc)
        doc.close()

        # Chunk the text
        chunks, chunk_size, overlap = [], settings.max_pdf_chunk_size, settings.chunk_overlap
        for i in range(0, len(full_text), chunk_size - overlap):
            chunk = full_text[i:i + chunk_size].strip()
            if chunk:
                chunks.append(chunk)

        if not chunks:
            continue

        embeddings = model.encode(chunks).tolist()
        ids = [f"{doc_id}_{j}" for j in range(len(chunks))]
        collection.add(
            ids=ids,
            documents=chunks,
            embeddings=embeddings,
            metadatas=[{"source": doc_id, "chunk": j} for j in range(len(chunks))],
        )
        logger.info(f"[PDFReader] Indexed {len(chunks)} chunks from {doc_id}")

    return collection, model


def run_pdf_reader(state: ResearchState) -> dict:
    """Node — semantically search uploaded PDFs and return relevant Source objects."""
    pdf_paths = state.get("uploaded_pdf_paths", [])
    query = state.get("user_query", "")

    steps = append_step(
        state, AgentName.PDF_READER,
        action=f"Reading {len(pdf_paths)} PDF(s)",
        status=ResearchStatus.READING,
    )

    if not pdf_paths:
        logger.info("[PDFReader] No PDFs uploaded, skipping")
        return {"pdf_results": [], "steps": steps}

    results: list[Source] = []
    try:
        collection, model = _get_or_create_collection(pdf_paths)
        query_embedding = model.encode([query]).tolist()

        hits = collection.query(
            query_embeddings=query_embedding,
            n_results=min(5, collection.count()),
        )

        for i, (doc, meta, dist) in enumerate(zip(
            hits["documents"][0],
            hits["metadatas"][0],
            hits["distances"][0],
        )):
            score = max(0.0, 1.0 - dist)  # cosine distance → similarity score
            results.append(Source(
                id=str(uuid.uuid4()),
                title=f"{meta['source']} — chunk {meta['chunk']}",
                url=None,
                snippet=doc[:500],
                agent=AgentName.PDF_READER,
                score=score,
            ))

        logger.info(f"[PDFReader] Retrieved {len(results)} relevant chunks")
        steps = append_step(
            state, AgentName.PDF_READER,
            action=f"Found {len(results)} relevant PDF sections",
            status=ResearchStatus.READING,
        )

    except Exception as e:
        logger.error(f"[PDFReader] Failed: {e}")
        steps = append_step(
            state, AgentName.PDF_READER,
            action="PDF reading failed",
            status=ResearchStatus.ERROR,
            detail=str(e),
        )

    return {
        "pdf_results": results,
        "all_sources": [*state.get("all_sources", []), *results],
        "steps": steps,
    }
