from __future__ import annotations

from pathlib import Path
from typing import Any
import chromadb
from app.rag.parser import parse_policy_markdown


class ChromaPolicyStore:
    """Student scaffold for the real Chroma-backed policy index."""

    def __init__(
        self,
        persist_directory: Path,
        embedding_model: Any,
        collection_name: str = "policy_chunks",
    ) -> None:
        self.persist_directory = persist_directory
        self.embedding_model = embedding_model
        
        # Ensure parent directory of persist_directory exists
        persist_directory.parent.mkdir(parents=True, exist_ok=True)
        
        self.client = chromadb.PersistentClient(path=str(persist_directory))
        self.collection = self.client.get_or_create_collection(
            name=collection_name
        )

    def ensure_index(self, markdown_path: Path) -> None:
        if self.collection.count() == 0:
            self.rebuild(markdown_path)

    def rebuild(self, markdown_path: Path) -> None:
        # Read markdown
        with open(markdown_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        chunks = parse_policy_markdown(content)
        
        # Clear collection if not empty
        all_ids = self.collection.get()["ids"]
        if all_ids:
            self.collection.delete(ids=all_ids)
            
        if not chunks:
            return
            
        ids = []
        documents = []
        metadatas = []
        for i, chunk in enumerate(chunks):
            ids.append(f"chunk_{i}")
            documents.append(chunk["rendered_text"])
            metadatas.append({
                "section_h2": chunk["section_h2"],
                "section_h3": chunk["section_h3"],
                "citation": chunk["citation"]
            })
            
        # Get embeddings
        embeddings = self.embedding_model.embed_documents(documents)
        
        # Add to Chroma collection
        self.collection.add(
            ids=ids,
            embeddings=embeddings,
            metadatas=metadatas,
            documents=documents
        )

    def search(self, query: str, top_k: int = 4) -> list[dict[str, Any]]:
        query_embedding = self.embedding_model.embed_query(query)
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k
        )
        
        hits = []
        if results and "documents" in results and results["documents"]:
            docs = results["documents"][0]
            metas = results["metadatas"][0] if "metadatas" in results and results["metadatas"] else [{}] * len(docs)
            distances = results["distances"][0] if "distances" in results and results["distances"] else [0.0] * len(docs)
            
            for doc, meta, dist in zip(docs, metas, distances):
                hits.append({
                    "citation": meta.get("citation", "") if meta else "",
                    "content": doc,
                    "distance": dist
                })
        return hits
