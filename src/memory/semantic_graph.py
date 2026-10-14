"""Semantic Knowledge Graph for TATSU Sovereign Agent — Phase 2.

Maintains structured factual relationships (Entities + Relationships) using
NetworkX for in-memory graph operations and SQLite for persistent storage.
Thread-safe and fast (<10ms queries).
"""

import json
import time
import sqlite3
import logging
import threading
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

import networkx as nx

logger = logging.getLogger("TATSU.SemanticGraph")
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_DB_PATH = BASE_DIR / "data" / "tatsu_memory.db"


class SemanticKnowledgeGraph:
    """Persistent graph of entities and directed relationships."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path or DEFAULT_DB_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._lock = threading.RLock()
        self.graph = nx.DiGraph()

        self._init_sqlite()
        self._load_graph_from_sqlite()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_sqlite(self) -> None:
        """Initializes SQLite schema for entities and relationships."""
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS entities (
                    name TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    attributes TEXT,
                    updated_at REAL NOT NULL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS relationships (
                    source TEXT NOT NULL,
                    target TEXT NOT NULL,
                    relation_type TEXT NOT NULL,
                    attributes TEXT,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY (source, target, relation_type),
                    FOREIGN KEY (source) REFERENCES entities (name) ON DELETE CASCADE,
                    FOREIGN KEY (target) REFERENCES entities (name) ON DELETE CASCADE
                )
            """)
            conn.commit()

    def _load_graph_from_sqlite(self) -> None:
        """Hydrates the in-memory NetworkX DiGraph from SQLite."""
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()

            # Load nodes
            cursor.execute("SELECT name, type, attributes FROM entities")
            for row in cursor.fetchall():
                attrs = json.loads(row["attributes"]) if row["attributes"] else {}
                attrs["type"] = row["type"]
                self.graph.add_node(row["name"], **attrs)

            # Load edges
            cursor.execute("SELECT source, target, relation_type, attributes FROM relationships")
            for row in cursor.fetchall():
                attrs = json.loads(row["attributes"]) if row["attributes"] else {}
                attrs["relation"] = row["relation_type"]
                self.graph.add_edge(row["source"], row["target"], **attrs)

    def add_entity(
        self,
        name: str,
        entity_type: str = "Concept",
        attributes: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Adds or updates an entity node in both memory and SQLite."""
        name = name.strip()
        if not name:
            return

        now = time.time()
        attrs = attributes or {}
        attrs_json = json.dumps(attrs)

        with self._lock:
            # 1. Update SQLite
            with self._get_connection() as conn:
                conn.execute("""
                    INSERT INTO entities (name, type, attributes, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(name) DO UPDATE SET
                        type=excluded.type,
                        attributes=excluded.attributes,
                        updated_at=excluded.updated_at
                """, (name, entity_type, attrs_json, now))
                conn.commit()

            # 2. Update NetworkX
            node_data = dict(attrs)
            node_data["type"] = entity_type
            self.graph.add_node(name, **node_data)

    def add_relationship(
        self,
        source: str,
        target: str,
        relation_type: str,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Creates or updates a directed relationship edge between two entities."""
        source = source.strip()
        target = target.strip()
        relation_type = relation_type.strip().lower()

        if not source or not target or not relation_type:
            return

        now = time.time()
        attrs = attributes or {}
        attrs_json = json.dumps(attrs)

        with self._lock:
            # Ensure source and target entities exist in SQLite
            with self._get_connection() as conn:
                conn.execute("""
                    INSERT OR IGNORE INTO entities (name, type, attributes, updated_at)
                    VALUES (?, 'Concept', '{}', ?)
                """, (source, now))
                conn.execute("""
                    INSERT OR IGNORE INTO entities (name, type, attributes, updated_at)
                    VALUES (?, 'Concept', '{}', ?)
                """, (target, now))

                conn.execute("""
                    INSERT INTO relationships (source, target, relation_type, attributes, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(source, target, relation_type) DO UPDATE SET
                        attributes=excluded.attributes,
                        updated_at=excluded.updated_at
                """, (source, target, relation_type, attrs_json, now))
                conn.commit()

            # Update NetworkX
            if not self.graph.has_node(source):
                self.graph.add_node(source, type="Concept")
            if not self.graph.has_node(target):
                self.graph.add_node(target, type="Concept")

            edge_data = dict(attrs)
            edge_data["relation"] = relation_type
            self.graph.add_edge(source, target, **edge_data)

    def query_facts(self, entity_name: str) -> List[str]:
        """Returns all known facts and relationships for a specific entity."""
        facts = []
        name = entity_name.strip()

        with self._lock:
            # Check outgoing relationships
            if self.graph.has_node(name):
                node_type = self.graph.nodes[name].get("type", "Entity")
                facts.append(f"{name} is a {node_type}.")

                # Outgoing edges: (name -> relation -> target)
                for _, target, data in self.graph.out_edges(name, data=True):
                    rel = data.get("relation", "relates to")
                    facts.append(f"{name} {rel} {target}.")

                # Incoming edges: (source -> relation -> name)
                for source, _, data in self.graph.in_edges(name, data=True):
                    rel = data.get("relation", "relates to")
                    facts.append(f"{source} {rel} {name}.")

        return facts

    def infer_context(self, user_query: str) -> List[str]:
        """Scans query for known entities and returns relevant subgraph facts."""
        matched_facts = []
        query_lower = user_query.lower()

        with self._lock:
            nodes_to_inspect = []
            for node in self.graph.nodes:
                if node.lower() in query_lower:
                    nodes_to_inspect.append(node)

            for node in nodes_to_inspect:
                node_facts = self.query_facts(node)
                for f in node_facts:
                    if f not in matched_facts:
                        matched_facts.append(f)

        return matched_facts

    def extract_and_learn_facts(self, text: str) -> List[Tuple[str, str, str]]:
        """Heuristically extracts simple subject-relation-object facts from user statements.
        
        Example statements learned:
          - "My name is Raj" -> (User, has_name, Raj)
          - "I like coffee" -> (User, likes, Coffee)
          - "I am working on TATSU" -> (User, works_on, TATSU)
          - "Laptop runs macOS" -> (Laptop, runs, macOS)
        """
        import re
        learned = []

        patterns = [
            (r"\bmy name is\s+([A-Za-z0-9_]+)", "User", "has_name"),
            (r"\bi\s+(?:really\s+)?(like|love|prefer)\s+([A-Za-z0-9_ ]+)", "User", None),
            (r"\bi am working on\s+([A-Za-z0-9_ ]+)", "User", "works_on"),
            (r"\bi work on\s+([A-Za-z0-9_ ]+)", "User", "works_on"),
            (r"\b([A-Za-z0-9_]+)\s+runs\s+([A-Za-z0-9_]+)", None, "runs"),
            (r"\b([A-Za-z0-9_]+)\s+owns\s+([A-Za-z0-9_]+)", None, "owns"),
        ]

        for pat in patterns:
            match = re.search(pat[0], text, re.IGNORECASE)
            if match:
                groups = match.groups()
                if len(groups) == 1 and pat[1] and pat[2]:
                    subj, rel, obj = pat[1], pat[2], groups[0].strip()
                elif len(groups) == 2 and pat[1]:
                    subj = pat[1]
                    rel = groups[0].strip().lower()
                    obj = groups[1].strip()
                elif len(groups) == 2 and pat[2]:
                    subj = groups[0].strip()
                    rel = pat[2]
                    obj = groups[1].strip()
                else:
                    continue

                if subj and rel and obj:
                    self.add_entity(subj, "Person" if subj == "User" else "Concept")
                    self.add_entity(obj, "Concept")
                    self.add_relationship(subj, obj, rel)
                    learned.append((subj, rel, obj))

        return learned
