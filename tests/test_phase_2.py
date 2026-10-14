"""Test suite for Phase 2: Long-Term Brain (Persistent Memory & Knowledge Graph)."""

import sys
import shutil
import tempfile
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.memory.episodic_store import EpisodicMemoryStore
from src.memory.semantic_graph import SemanticKnowledgeGraph
from src.core.agent_graph import perceive_node
from src.core.state import AgentState


def test_episodic_memory_persistence():
    print("=== Testing Episodic Memory & Persistence Across Restarts ===")
    test_dir = Path(tempfile.mkdtemp(prefix="tatsu_chroma_test_"))
    try:
        # Step 1: Store an event
        store1 = EpisodicMemoryStore(db_dir=test_dir)
        event_id = store1.store_event(
            event_type="user_preference",
            content="User likes coffee",
            metadata={"session_id": "test_sess_1", "source": "voice"},
        )
        assert event_id is not None and len(event_id) > 0
        print(f"[PASS] Event stored with ID: {event_id}")

        # Step 2: Restart simulation (delete store1 instance from RAM, reload DB from disk)
        del store1
        store2 = EpisodicMemoryStore(db_dir=test_dir)

        # Verify semantic retrieval from disk
        similar = store2.retrieve_similar("What is my favorite hot drink?", k=1)
        print("[PASS] Retrieved after reload:", similar)
        assert len(similar) > 0
        assert "coffee" in similar[0]["content"].lower()

        # Verify chronological recent events
        recent = store2.get_recent_events(n=5)
        assert len(recent) > 0
        assert "coffee" in recent[0]["content"].lower()
        print("[PASS] Episodic memory persisted across reloads successfully.")

        # Test purge session
        deleted = store2.purge_session("test_sess_1")
        assert deleted >= 1
        assert len(store2.get_recent_events()) == 0
        print("[PASS] Session purged cleanly.")

    finally:
        shutil.rmtree(test_dir, ignore_errors=True)


def test_semantic_knowledge_graph():
    print("\n=== Testing Semantic Knowledge Graph (NetworkX + SQLite) ===")
    test_db = Path(tempfile.mktemp(suffix=".db", prefix="tatsu_sem_test_"))
    try:
        # Step 3: Add relationship ("Raj" -> "likes" -> "Coffee")
        graph1 = SemanticKnowledgeGraph(db_path=test_db)
        graph1.add_entity("Raj", "Person", {"role": "Creator"})
        graph1.add_entity("Coffee", "Beverage")
        graph1.add_relationship("Raj", "Coffee", "likes")

        # Step 4: Query graph facts
        facts = graph1.query_facts("Raj")
        print("[PASS] Facts for 'Raj':", facts)
        assert any("Raj likes Coffee" in f for f in facts)

        # Context inference
        inferred = graph1.infer_context("Tell me what Raj wants to drink today")
        print("[PASS] Inferred context for query:", inferred)
        assert any("Raj likes Coffee" in f for f in inferred)

        # Verify persistence across restart
        del graph1
        graph2 = SemanticKnowledgeGraph(db_path=test_db)
        reloaded_facts = graph2.query_facts("Raj")
        assert any("Raj likes Coffee" in f for f in reloaded_facts)
        print("[PASS] Semantic graph persisted to SQLite and reloaded into NetworkX successfully.")

        # Automated fact extraction
        learned = graph2.extract_and_learn_facts("I am working on TATSU")
        print("[PASS] Automatically learned from statement:", learned)
        assert len(learned) > 0
        assert graph2.graph.has_edge("User", "TATSU")

    finally:
        if test_db.exists():
            test_db.unlink()


def test_agent_prompt_memory_injection():
    print("\n=== Testing Agent Prompt Injection with Recalled Memories ===")
    # Create test state with user query mentioning an entity
    state: AgentState = {
        "current_task": "What does Raj like?",
        "messages": [],
        "tool_calls": [],
        "observations": [],
        "persona_config": {
            "name": "TATSU",
            "role": "Sovereign Digital Companion",
            "tone": "Concise",
            "loyalty_protocol": "Obey Raj",
        },
        "turn_count": 0,
    }

    # Populate temporary test entity in the active graph so perceive_node sees it
    from src.core.agent_graph import get_semantic_graph, get_episodic_store
    sem_graph = get_semantic_graph()
    if sem_graph:
        sem_graph.add_entity("Raj", "Person")
        sem_graph.add_entity("Coffee", "Beverage")
        sem_graph.add_relationship("Raj", "Coffee", "likes")

    ep_store = get_episodic_store()
    if ep_store:
        ep_store.store_event("interaction", "User likes espresso and coffee")

    # Run perceive_node
    result = perceive_node(state)
    assert "messages" in result
    system_msg = result["messages"][0].content
    print("[PASS] Injected System Prompt snippet:\n", system_msg[:400], "...")

    # Verify memory context was injected into system prompt
    assert "[KNOWN FACTS ABOUT USER/ENVIRONMENT]" in system_msg or "[RELEVANT PAST CONVERSATIONS]" in system_msg
    assert "memory_context" in result
    assert result["memory_context"] is not None
    print("[PASS] Memory context successfully injected into Agent prompt.")


def run_all():
    test_episodic_memory_persistence()
    test_semantic_knowledge_graph()
    test_agent_prompt_memory_injection()
    print("\n✅ ALL PHASE 2 LONG-TERM BRAIN TESTS PASSED.")


if __name__ == "__main__":
    run_all()
