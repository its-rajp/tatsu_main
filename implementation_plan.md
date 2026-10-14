# Implementation Plan: Rebuilding "Tatsu" from UltronMain (100% Free-Tier Architecture)

## Overview
This plan outlines the complete reverse-engineering and documentation strategy for the `ultronmain` repository, transforming it into **Tatsu** — an intelligent, human-communicatable desktop AI companion and autonomous operating system agent. The system is designed to run entirely on **100% free-tier, open-source, zero-cost local models and cloud endpoints**.

---

## User Review Required

> [!IMPORTANT]
> **Assistant Name & Persona Transition:**
> The previous project was configured as "ULTRON" (a cold, robotic cybernetic overlord persona). The new system will be named **Tatsu** and re-architected with a warm, conversational, and highly human-communicatable voice and personality, while preserving full computer control, visual reasoning, and tool execution capabilities.

> [!NOTE]
> **100% Free-Tier & Local-First Stack Guarantee:**
> All cloud dependencies (e.g., Gemini API keys) are supplemented or replaced with zero-cost alternatives:
> - **LLM Core:** Local Ollama (`qwen2.5:7b-instruct`, `llama3.2:3b`), LM Studio / vLLM (OpenAI-compatible), or Google AI Studio Free Tier (Gemini 2.5 Flash free tier, 15 RPM).
> - **STT (Speech-to-Text):** `faster-whisper` (int8/float16 offline) and Vosk (streaming local offline).
> - **TTS (Text-to-Speech):** Kokoro-82M (high-quality offline neural TTS), Piper (fast offline neural TTS), and Microsoft EdgeTTS (zero-cost cloud TTS without API key).
> - **Search Engine:** DuckDuckGo Search (`duckduckgo-search` / `ddgs`) with zero API key or usage limits.
> - **Browser Automation:** Playwright with headless/headful Chromium.
> - **Web Dashboard:** FastAPI + Uvicorn + WebSockets + Web Crypto AES-256-CBC.

---

## Deliverables Suite

We will generate 8 exhaustive Markdown documentation files in the repository root:

1. [Architecture.md](file:///Users/rajpujari/Downloads/ultronmain-main/Architecture.md)
   - High-level system architecture, ASCII component topology, dataflow pipelines.
   - Component interactions: **Memory Hub**, **Skill Hub (Actions)**, **Harness Hub (Runtime & OS Integration)**, and **UI/Dashboard Relay**.
   - Zero-cost tech stack matrix and fallback hierarchy.

2. [memory.md](file:///Users/rajpujari/Downloads/ultronmain-main/memory.md)
   - Project contextual memory, design rationale, architectural trade-offs.
   - Long-term memory structure (`long_term.json`, CRM/CMR contact records, Task Scheduler reminders).
   - KV-cache priming strategies, context budgeting (LRU char caps), and vector memory upgrade paths using free local ChromaDB.

3. [phase.md](file:///Users/rajpujari/Downloads/ultronmain-main/phase.md)
   - Chronological step-by-step implementation roadmap across 6 detailed phases.
   - Milestones, deliverables, verification criteria, and dependency gates for bootstrapping from zero.

4. [project requirement.md](file:///Users/rajpujari/Downloads/ultronmain-main/project%20requirement.md)
   - Comprehensive Functional Requirements (FRs) covering all 20 tools.
   - Non-Functional Requirements (NFRs): latency limits, memory footprint, offline survivability.
   - Hardware requirements (minimum vs. recommended: CPU, RAM, VRAM) and software dependencies.

5. [workflow.md](file:///Users/rajpujari/Downloads/ultronmain-main/workflow.md)
   - Developer workflows, local setup scripts (`SETUP.bat`, `START_TATSU.bat`, `wake_service.py`).
   - Testing protocols (unit testing tools, mocking audio streams, WebRTC/WebSocket verification).
   - Deployment & self-hosting instructions (LAN access, firewall automation, QR code device pairing).

6. [rules.md](file:///Users/rajpujari/Downloads/ultronmain-main/rules.md)
   - Architectural guardrails, coding standards (PEP 8, type hints, async/sync thread bridging).
   - Safety constraints: path traversal prevention, process isolation, single-instance socket locks (`39152`).
   - Naming conventions and error-handling paradigms.

7. [structure.md](file:///Users/rajpujari/Downloads/ultronmain-main/structure.md)
   - File-by-file and folder-by-folder technical inspection of all 35+ files in the repository.
   - Exact mapping of responsibilities, imports, entry points, and helper utilities.

8. [design.md](file:///Users/rajpujari/Downloads/ultronmain-main/design.md)
   - UI/UX design specifications for Tatsu: Qt6 WebEngine HUD, reactive state machines (`LISTENING`, `THINKING`, `SPEAKING`, `EMERGENCY`).
   - Sound design, human-communicatable persona prompt specifications, and mobile companion responsive UI design.

---

## Verification Plan

### Automated Verification
- Verify that all 8 Markdown files are created with valid UTF-8 encoding and clean GitHub Flavored Markdown formatting.
- Check cross-file references and link consistency.

### Manual Verification
- Review file-by-file alignment with reverse-engineered source modules (`main.py`, `ui.py`, `dashboard/server.py`, `core/*`, `actions/*`, `memory/*`).
- Ensure all instances of "Ultron" are cleanly replaced with "Tatsu", maintaining the human-communicatable persona and 100% free-tier architecture.
