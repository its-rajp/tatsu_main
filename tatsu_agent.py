#!/usr/bin/env python3
"""TATSU Sovereign Agent — Unified Entry Point.

Usage:
    python tatsu_agent.py              # Interactive mode (voice if available, text fallback)
    python tatsu_agent.py --text       # Force text-only mode
    python tatsu_agent.py --query "check system stats"   # Single query, then exit
"""

import argparse
import sys
from pathlib import Path

# Ensure project root is on sys.path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from src.core.agent_graph import TatsuAgent, load_persona_config
from src.io.audio_engine import TatsuAudio
from src.tools.registry import AVAILABLE_TOOLS, audit_log
from src.proactive.alert_engine import AlertEngine
from src.perception.system_monitor import SystemMonitor

BANNER = r"""
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║   ████████╗ █████╗ ████████╗███████╗██╗   ██╗                ║
║   ╚══██╔══╝██╔══██╗╚══██╔══╝██╔════╝██║   ██║                ║
║      ██║   ███████║   ██║   ███████╗██║   ██║                ║
║      ██║   ██╔══██║   ██║   ╚════██║██║   ██║                ║
║      ██║   ██║  ██║   ██║   ███████║╚██████╔╝                ║
║      ╚═╝   ╚═╝  ╚═╝   ╚═╝   ╚══════╝ ╚═════╝                ║
║                                                              ║
║           S O V E R E I G N   D I G I T A L                  ║
║               C O M P A N I O N                              ║
║                                                              ║
║   • LangGraph Agentic Core       • Local Ollama LLM          ║
║   • Sandboxed Tool Registry      • Immutable Audit Ledger    ║
║   • Voice I/O (when available)   • Zero Cloud Dependencies   ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
"""


def run_single_query(agent: TatsuAgent, query: str) -> None:
    """Execute a single query and print the response."""
    print(f"\n📨 Query: {query}")
    print("⏳ Processing...")
    response = agent.process(query)
    print(f"\n🐉 TATSU:\n{response}")
    audit_log("SESSION", {"mode": "single_query", "query": query}, status="COMPLETE")


def run_interactive(
    agent: TatsuAgent,
    alert_engine: Optional[AlertEngine] = None,
    system_monitor: Optional[SystemMonitor] = None,
    text_only: bool = False,
) -> None:
    """Run the interactive REPL loop with voice or text input and proactive monitoring."""
    # Initialise audio engine
    audio = None
    if not text_only:
        try:
            audio = TatsuAudio()
            caps = audio.capabilities
            voice_parts = []
            if caps["wake_word"]:
                voice_parts.append("Wake Word ✓")
            if caps["stt"]:
                voice_parts.append("STT ✓")
            if caps["tts"] or audio.has_tts:
                voice_parts.append("TTS ✓")
            if caps["audio_io"]:
                voice_parts.append("Audio I/O ✓")

            if voice_parts:
                print(f"🎙️  Voice capabilities: {' | '.join(voice_parts)}")
            else:
                print("⌨️  No voice libraries detected. Running in text-only mode.")
                audio = None
        except Exception as e:
            print(f"⌨️  Audio init failed ({e}). Running in text-only mode.")
            audio = None
    else:
        print("⌨️  Text-only mode (--text flag).")

    # Connect AlertEngine to TTS if audio is available
    if alert_engine and audio and audio.has_tts:
        alert_engine.voice_callback = lambda msg: audio.speak(msg[:200])

    # Start background monitoring loop
    if system_monitor:
        system_monitor.start_background_loop()
        print("💓 Proactive system health monitor active (background).")

    print("\nType 'quit', 'exit', or press Ctrl+C to stop.\n")

    audit_log("SESSION", {
        "mode": "interactive",
        "voice": audio is not None and audio.has_voice,
        "tts": audio is not None and audio.has_tts,
        "monitor": system_monitor is not None,
    }, status="STARTED")

    turn = 0
    try:
        while True:
            try:
                # Get input — voice or text
                if audio and audio.has_voice:
                    user_input = audio.listen_once()
                else:
                    try:
                        user_input = input("\n🐉 TATSU > ").strip()
                    except EOFError:
                        break

                if not user_input:
                    continue
                if user_input.lower() in ("quit", "exit", "bye", "goodbye"):
                    farewell = "TATSU signing off. The stars watch over you."
                    print(f"\n🐉 {farewell}")
                    if audio and audio.has_tts:
                        audio.speak(farewell)
                    break

                turn += 1

                # Check if this is an affirmation for a pending proactive alert action
                normalized_input = user_input.lower().strip(" .!?,")
                if (
                    alert_engine
                    and normalized_input in ("yes", "do it", "yes do it", "proceed", "kill it", "sure")
                    and alert_engine.get_latest_pending_action()
                ):
                    pending = alert_engine.pop_pending_action()
                    action = pending.get("action", {})
                    tool_name = action.get("tool")
                    args = action.get("args", {})
                    tool = AVAILABLE_TOOLS.get(tool_name)
                    if tool:
                        print(f"\n⚡ Executing suggested action: {tool_name} with {args}...")
                        result = tool.execute(args)
                        print(f"\n🐉 TATSU:\n{result}")
                        if audio and audio.has_tts:
                            audio.speak(result[:300])
                        continue

                print(f"\n⏳ Processing (turn {turn})...")
                response = agent.process(user_input)
                print(f"\n🐉 TATSU:\n{response}")

                # Speak the response
                if audio and audio.has_tts:
                    speak_text = response[:500] if len(response) > 500 else response
                    audio.speak(speak_text)

            except KeyboardInterrupt:
                print("\n\n🐉 TATSU interrupted. Signing off.")
                break
            except Exception as e:
                print(f"\n⚠️  Error: {e}")
                audit_log("SESSION_ERROR", {"turn": turn, "error": str(e)}, status="ERROR")
                continue
    finally:
        if system_monitor:
            system_monitor.stop_background_loop()
        audit_log("SESSION", {"mode": "interactive", "total_turns": turn}, status="ENDED")


def main():
    parser = argparse.ArgumentParser(
        description="TATSU — Sovereign Digital Companion",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--text", action="store_true",
        help="Force text-only mode (skip voice initialisation).",
    )
    parser.add_argument(
        "--query", "-q", type=str, default=None,
        help="Run a single query and exit.",
    )
    parser.add_argument(
        "--config", type=str, default=None,
        help="Path to persona.yaml configuration file.",
    )
    args = parser.parse_args()

    print(BANNER)

    # Load agent
    config_path = Path(args.config) if args.config else None
    agent = TatsuAgent(config_path=config_path)
    persona = agent.persona_config
    print(f"🧠 Agent Core: {persona.get('name', 'TATSU')} — {persona.get('role', 'Sovereign Digital Companion')}")
    print(f"🤖 Model preference: {persona.get('ollama_model', 'auto')} (fallback: {persona.get('fallback_model', 'auto')})")

    # Instantiate proactive alert engine and health monitor
    alert_engine = AlertEngine()
    system_monitor = SystemMonitor(alert_engine=alert_engine)

    if args.query:
        run_single_query(agent, args.query)
    else:
        run_interactive(
            agent,
            alert_engine=alert_engine,
            system_monitor=system_monitor,
            text_only=args.text,
        )


if __name__ == "__main__":
    main()
