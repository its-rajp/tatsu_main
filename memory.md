# Tatsu — Memory System

> Tatsu uses a **layered, file-backed memory model** — all persistent state is stored as JSON flat-files with `threading.RLock` for thread safety. This keeps the system entirely dependency-free for persistence (no database server required) while allowing a clean upgrade path to SQLite or ChromaDB.

---

## 1. Memory Layers Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                       TATSU MEMORY SYSTEM                            │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  LAYER 1 — WORKING MEMORY (in-process, ephemeral)            │   │
│  │  • Gemini Live session context window (last ~32k tokens)     │   │
│  │  • Injected system_instruction at session start              │   │
│  │  • Cleared when process exits                                │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  LAYER 2 — LONG-TERM MEMORY (memory/long_term.json)          │   │
│  │  • Persisted user facts: identity, preferences, projects     │   │
│  │  • Written via save_memory() tool call from Gemini           │   │
│  │  • Read at every session start → injected into prompt        │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  LAYER 3 — CONFIGURATION MEMORY (config/api_keys.json)       │   │
│  │  • API keys, persona settings, TTS/STT engine choices        │   │
│  │  • Read via LRU-cached get_config_value()                    │   │
│  │  • Written via set_config_value()                            │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  LAYER 4 — TASK MEMORY (memory/reminders.json)               │   │
│  │  • Scheduled reminders with ISO trigger timestamps           │   │
│  │  • Polled at session start; expired ones trigger speech      │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  LAYER 5 — RELATIONSHIP MEMORY (memory/cmr_records.json)     │   │
│  │  • Contacts, leads, business relationships                   │   │
│  │  • UUID-keyed JSON list                                      │   │
│  └──────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 2. Long-Term Memory (`memory/memory_manager.py`)

### 2.1 File Schema

```json
// memory/long_term.json
{
  "identity": {
    "name": {
      "value": "Alex",
      "updated": "2026-09-03"
    },
    "age": {
      "value": "27",
      "updated": "2026-09-01"
    }
  },
  "preferences": {
    "favorite_editor": {
      "value": "VS Code",
      "updated": "2026-09-02"
    },
    "preferred_language": {
      "value": "Python",
      "updated": "2026-09-01"
    }
  },
  "projects": {
    "main_project": {
      "value": "Building Tatsu AI assistant",
      "updated": "2026-09-03"
    }
  },
  "relationships": {
    "best_friend": {
      "value": "Jordan, met in university",
      "updated": "2026-08-30"
    }
  },
  "wishes": {
    "goal_2026": {
      "value": "Launch an indie SaaS product",
      "updated": "2026-09-01"
    }
  },
  "notes": {
    "health_note": {
      "value": "Allergic to peanuts",
      "updated": "2026-08-28"
    }
  }
}
```

### 2.2 Categories

| Category | Purpose | Examples |
|----------|---------|---------|
| `identity` | Core personal facts | name, age, location, job title |
| `preferences` | User taste and habit data | favorite tools, languages, music, food |
| `projects` | Ongoing work items | active project names, deadlines, tech stacks |
| `relationships` | People in the user's life | names, roles, relationship context |
| `wishes` | Goals, dreams, plans | life goals, career goals, purchase plans |
| `notes` | Miscellaneous facts | health data, reminders, custom notes |

### 2.3 Key Functions

```python
# memory/memory_manager.py

def load_memory() -> dict:
    """Loads long_term.json; returns empty dict if missing."""

def save_memory_to_disk(data: dict) -> None:
    """Thread-safe write with RLock. Atomic via json.dump + flush."""

def update_memory(updates: dict) -> None:
    """Deep-merges updates dict into existing memory.
    Creates categories/keys if they don't exist.
    Overwrites value+updated for existing keys."""

def format_memory_for_prompt() -> str:
    """Returns formatted string for system_instruction injection.
    Format: '### USER MEMORY\\n**Category:**\\n  - key: value (updated DATE)'
    Returns empty string if memory file is empty."""

def get_memory_summary() -> dict:
    """Returns memory stats: category count, total keys, last updated."""
```

### 2.4 Thread Safety Model

```python
_memory_lock = threading.RLock()

def update_memory(updates):
    with _memory_lock:
        data = load_memory()
        # deep merge...
        save_memory_to_disk(data)
```

The `RLock` (reentrant) allows the same thread to call `update_memory` recursively without deadlock. This is critical because `main.py` may call memory functions from within the asyncio executor thread pool.

### 2.5 Prompt Injection

At every session start (`_build_config()`), memory is injected into `system_instruction`:

```python
memory_str = format_memory_for_prompt()
system_instruction = f"""
{base_prompt}

{memory_str}
"""
```

This means **Tatsu always knows** everything the user has ever saved — without any retrieval step.

---

## 3. Configuration Memory (`memory/config_manager.py`)

### 3.1 File Schema

```json
// config/api_keys.json
{
    "gemini_api_key": "AIza...",
    "assistant_name": "Tatsu",
    "user_name": "Alex",
    "os_system": "windows",
    "morning_brief_enabled": true,
    "ui_color": "#00d4ff",
    "llm_provider": "ollama",
    "llm_url": "http://localhost:11434",
    "llm_model": "qwen2.5:7b-instruct",
    "tts_engine": "edgetts",
    "tts_voice": "en-US-BrianNeural",
    "tts_speed": 1.0,
    "stt_engine": "whisper",
    "stt_model": "base",
    "stt_language": "auto"
}
```

### 3.2 Key Functions

```python
def get_config_value(key: str, default=None):
    """LRU-cached read. Cache invalidated on any write."""

def set_config_value(key: str, value) -> None:
    """Thread-safe write. Clears LRU cache after write."""

def get_full_config() -> dict:
    """Returns entire config dict. NOT cached."""
```

### 3.3 Caching Strategy

```python
from functools import lru_cache

@lru_cache(maxsize=128)
def _load_config_cached() -> dict:
    ...

def set_config_value(key, value):
    with _config_lock:
        data = get_full_config()
        data[key] = value
        with open(CONFIG_PATH, "w") as f:
            json.dump(data, f, indent=2)
        _load_config_cached.cache_clear()  # Invalidate LRU
```

---

## 4. Reminder Memory (`memory/reminder_manager.py`)

### 4.1 File Schema

```json
// memory/reminders.json
[
  {
    "id": "uuid-1234",
    "text": "Take medication",
    "trigger_time": "2026-09-03T14:30:00",
    "repeat": "daily",
    "created": "2026-09-01T10:00:00"
  },
  {
    "id": "uuid-5678",
    "text": "Team standup meeting",
    "trigger_time": "2026-09-04T09:00:00",
    "repeat": "weekdays",
    "created": "2026-09-02T08:00:00"
  }
]
```

### 4.2 Repeat Options

| Value | Behavior |
|-------|---------|
| `"once"` | Fires once, then deleted |
| `"daily"` | Next trigger = today + 1 day |
| `"weekdays"` | Next trigger = next weekday |
| `"weekly"` | Next trigger = today + 7 days |
| `"monthly"` | Next trigger = today + 30 days |

### 4.3 Reminder Dispatch

At session start, `_check_reminders()` is called. It checks all reminders with `trigger_time <= now()`, fires a `session.send_client_content()` with the reminder text to Tatsu's live session, and updates `trigger_time` based on `repeat`.

---

## 5. CRM Memory (`memory/cmr_manager.py`)

### 5.1 File Schema

```json
// memory/cmr_records.json
[
  {
    "id": "uuid-abcd",
    "name": "Sarah Kim",
    "role": "Client",
    "company": "Acme Corp",
    "email": "sarah@acme.com",
    "phone": "+1-555-0100",
    "notes": "Interested in the Pro tier. Follow up by end of Sept.",
    "last_contact": "2026-09-01",
    "created": "2026-08-20"
  }
]
```

### 5.2 Key Functions

```python
def add_record(name, role, company, email, phone, notes) -> str:
    """Creates new UUID-keyed contact. Returns new ID."""

def get_all_records() -> list:
    """Returns full CRM list sorted by name."""

def update_record(record_id, **updates) -> bool:
    """Partial update by UUID. Returns False if ID not found."""

def delete_record(record_id) -> bool:
    """Removes record by UUID. Returns False if ID not found."""

def search_records(query: str) -> list:
    """Full-text search across name, company, notes fields."""
```

---

## 6. Environment Utilities (`utils/env.py`)

```python
import platform, functools

@functools.lru_cache(maxsize=1)
def get_os() -> str:
    """Returns 'windows', 'mac', or 'linux' — cached permanently."""

def get_config_value(key: str, default=None):
    """Thin wrapper → config_manager.get_config_value()"""

def set_config_value(key: str, value):
    """Thin wrapper → config_manager.set_config_value()"""
```

---

## 7. Upgrade Path

| Current | Upgrade To | When |
|---------|-----------|------|
| `long_term.json` (flat file) | SQLite via `aiosqlite` | >100k entries or multi-user |
| `long_term.json` (flat file) | ChromaDB (local vector store) | When semantic search is needed |
| `cmr_records.json` | SQLite full-text search | When CRM exceeds 1,000 contacts |
| `reminders.json` | APScheduler + SQLite job store | When >100 recurring reminders needed |

### Migrating to ChromaDB (zero cost, local)

```python
pip install chromadb

import chromadb
client = chromadb.PersistentClient(path="./memory/chromadb")
collection = client.get_or_create_collection("tatsu_memory")

# Insert existing long_term.json entries as embeddings
for category, items in load_memory().items():
    for key, val in items.items():
        collection.add(
            documents=[f"{key}: {val['value']}"],
            ids=[f"{category}_{key}"],
            metadatas=[{"category": category, "updated": val["updated"]}]
        )

# Query
results = collection.query(query_texts=["user's favorite editor"], n_results=5)
```
