"""Episodic Memory Store for TATSU Sovereign Agent — Phase 2.

Provides persistent vector memory using ChromaDB and all-MiniLM-L6-v2 embeddings.
Stores user interactions, tool outcomes, and system observations.
Supports fast semantic similarity retrieval, chronological recall, and session purging.
"""

import os
import time
import uuid
import yaml
import logging
import threading
from pathlib import Path
from typing import Dict, Any, List, Optional

import chromadb
from chromadb.config import Settings
from chromadb.utils import embedding_functions

logger = logging.getLogger("TATSU.EpisodicMemory")
BASE_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = BASE_DIR / "config" / "memory.yaml"
DEFAULT_CHROMA_DIR = BASE_DIR / "data" / "chroma_db"


class EpisodicMemoryStore:
    """Persistent vector store for episodic conversation and action history."""

    def __init__(
        self,
        db_dir: Optional[Path] = None,
        config_path: Optional[Path] = None,
    ):
        self.config = self._load_config(config_path or CONFIG_PATH)
        self.db_dir = Path(db_dir or self.config.get("chroma_db_dir", DEFAULT_CHROMA_DIR))
        self.db_dir.mkdir(parents=True, exist_ok=True)

        self.collection_name = self.config.get("collection_name", "tatsu_episodic_memory")
        self.model_name = self.config.get("embedding_model", "all-MiniLM-L6-v2")
        self.retention_days = int(self.config.get("episodic_retention_days", 30))

        self._lock = threading.RLock()

        # Initialize Embedding Function with all-MiniLM-L6-v2
        self.embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=self.model_name
        )

        # Initialize Persistent Chroma Client
        self.client = chromadb.PersistentClient(
            path=str(self.db_dir),
            settings=Settings(anonymized_telemetry=False, is_persistent=True),
        )

        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            embedding_function=self.embedding_fn,
            metadata={"description": "TATSU episodic interaction memory"},
        )

    def _load_config(self, path: Path) -> dict:
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}
            except Exception as e:
                logger.error(f"Error loading {path}: {e}")
        return {
            "episodic_retention_days": 30,
            "max_episodes_per_session": 100,
            "collection_name": "tatsu_episodic_memory",
            "embedding_model": "all-MiniLM-L6-v2",
        }

    def store_event(
        self,
        event_type: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Saves an interaction, tool outcome, or user statement to episodic memory.
        
        Args:
            event_type: 'user_input', 'agent_response', 'tool_result', 'observation'
            content: Raw text content to embed and store
            metadata: Optional dict containing session_id, source (text/voice/screen), etc.

        Returns:
            Unique record ID.
        """
        content = content.strip()
        if not content:
            return ""

        now = time.time()
        record_id = f"evt_{int(now * 1000)}_{uuid.uuid4().hex[:8]}"

        meta = {
            "event_type": event_type,
            "timestamp": now,
            "session_id": (metadata or {}).get("session_id", "default"),
            "source": (metadata or {}).get("source", "agent"),
        }
        if metadata:
            for k, v in metadata.items():
                if k not in meta:
                    # Chroma metadata values must be primitive types (str, int, float, bool)
                    if isinstance(v, (str, int, float, bool)):
                        meta[k] = v
                    else:
                        meta[k] = str(v)

        with self._lock:
            self.collection.add(
                documents=[content],
                metadatas=[meta],
                ids=[record_id],
            )

        return record_id

    def retrieve_similar(self, query: str, k: int = 5) -> List[Dict[str, Any]]:
        """Returns top-k relevant past events based on semantic similarity."""
        query = query.strip()
        if not query:
            return []

        with self._lock:
            count = self.collection.count()
            if count == 0:
                return []

            n_results = min(k, count)
            results = self.collection.query(
                query_texts=[query],
                n_results=n_results,
            )

        events = []
        if results and results.get("documents") and results["documents"][0]:
            docs = results["documents"][0]
            metas = results["metadatas"][0] if results.get("metadatas") else [{}] * len(docs)
            distances = results["distances"][0] if results.get("distances") else [0.0] * len(docs)
            ids = results["ids"][0] if results.get("ids") else [""] * len(docs)

            for doc, m, dist, eid in zip(docs, metas, distances, ids):
                events.append({
                    "id": eid,
                    "content": doc,
                    "metadata": m,
                    "distance": dist,
                })

        return events

    def get_recent_events(self, n: int = 10) -> List[Dict[str, Any]]:
        """Returns a chronological list of the last n stored events."""
        with self._lock:
            count = self.collection.count()
            if count == 0:
                return []

            # Retrieve records and sort by timestamp
            data = self.collection.get()

        events = []
        if data and data.get("documents"):
            docs = data["documents"]
            metas = data.get("metadatas", [{}] * len(docs))
            ids = data.get("ids", [""] * len(docs))

            for doc, m, eid in zip(docs, metas, ids):
                events.append({
                    "id": eid,
                    "content": doc,
                    "metadata": m or {},
                    "timestamp": (m or {}).get("timestamp", 0.0),
                })

            events.sort(key=lambda x: x["timestamp"], reverse=True)

        return events[:n]

    def purge_session(self, session_id: str) -> int:
        """Deletes all events associated with a specific session ID."""
        if not session_id:
            return 0

        with self._lock:
            # Query matching IDs
            res = self.collection.get(where={"session_id": session_id})
            ids_to_delete = res.get("ids", []) if res else []
            if ids_to_delete:
                self.collection.delete(ids=ids_to_delete)
            return len(ids_to_delete)

    def prune_older_than(self, days: Optional[int] = None) -> int:
        """Prunes events older than the specified retention period."""
        retention = days if days is not None else self.retention_days
        cutoff = time.time() - (retention * 86400)

        with self._lock:
            # Get old records
            res = self.collection.get(where={"timestamp": {"$lt": cutoff}})
            ids_to_delete = res.get("ids", []) if res else []
            if ids_to_delete:
                self.collection.delete(ids=ids_to_delete)
            return len(ids_to_delete)
