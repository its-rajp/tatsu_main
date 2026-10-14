# Tatsu — Interaction Workflows

> This document describes every major **end-to-end interaction workflow** in the Tatsu system, from the user's first action to the final system response. All flows are traced through the code path with the relevant files and functions identified.

---

## Workflow Index

| # | Workflow | Trigger |
|---|---------|---------|
| W-1 | Voice Conversation | User speaks into mic |
| W-2 | Tool Execution (Agentic Loop) | Gemini decides to use a tool |
| W-3 | Memory Write | Gemini calls `save_memory` |
| W-4 | Memory Read (Session Start) | TatsuLive.run() startup |
| W-5 | Vision Session (Screen/Camera) | User asks "what's on my screen?" |
| W-6 | Dashboard Text Command | User types in phone dashboard |
| W-7 | Phone Mic Relay | User speaks via phone browser |
| W-8 | File Upload & Analysis | User uploads file from dashboard |
| W-9 | Dev Agent Task | User asks Tatsu to build a project |
| W-10 | Wake Word Trigger | User says "Hey Tatsu" |
| W-11 | Session Reconnect | Network drop / Gemini timeout |
| W-12 | Reminder Fire | Scheduled time reached |
| W-13 | Morning Briefing | Startup with `morning_brief_enabled: true` |
| W-14 | Proactive Check-in | 60s idle loop fires |
| W-15 | System Emergency Alert | CPU/RAM/GPU exceeds threshold |

---

## W-1: Voice Conversation

```
TRIGGER: User speaks into microphone

1. sounddevice InputStream (16 kHz PCM int16)
   └─ Callback: raw_audio_bytes → out_queue.put_nowait()

2. _send_realtime() [coroutine, always running]
   └─ out_queue.get() → session.send_realtime_input(audio_chunk)

3. Gemini Live Session processes speech
   └─ Automatic speech recognition (ASR) by Gemini
   └─ LLM reasoning (Tatsu persona context + memory context)
   └─ Generates audio response

4. _receive_audio() [coroutine, always running]
   ├─ event.data (PCM bytes at 24 kHz) → audio_in_queue
   ├─ event.server_content.input_transcription.text
   │   └─ write_log("You: <text>") → Qt signal → HUD JS
   └─ event.server_content.output_transcription.text
       └─ write_log("Tatsu: <text>") → Qt signal → HUD JS

5. _play_audio() [coroutine, always running]
   └─ audio_in_queue.get() → sounddevice RawOutputStream.write()
   └─ User hears Tatsu's voice response

FILES: main.py (_send_realtime, _receive_audio, _listen_audio, _play_audio)
       ui.py (Qt signals, write_log)
       dashboard/static/app.html (JS: addMemoryLog)
```

---

## W-2: Tool Execution (Agentic Loop)

```
TRIGGER: Gemini decides the user's request requires a tool

1. _receive_audio() detects: event.tool_call.function_calls[]
   └─ For each function_call in list:
       name = function_call.name
       args = function_call.args  (dict)

2. asyncio.get_event_loop().run_in_executor(
       None,                    ← default ThreadPoolExecutor
       _execute_tool,           ← blocking function
       name,                    ← tool name string
       args                     ← dict of arguments
   )
   └─ Runs tool in background thread (doesn't block audio I/O)

3. _execute_tool(name, args) dispatch table:
   "open_app"          → actions/open_app.py :: open_application(app_name, args)
   "web_search"        → actions/web_search.py :: search_web(query, num_results)
   "browser_control"   → actions/browser_control.py :: control_browser(action, ...)
   "screen_process"    → main.py :: _handle_screen_process(args)  [inline]
   "save_memory"       → memory/memory_manager.py :: update_memory(...)  [no executor]
   "system_status"     → actions/system_monitor.py :: get_system_status()
   ...

4. Tool returns: result_string (str)

5. session.send_tool_response(
       function_responses=[
           {"id": call.id, "name": call.name, "response": {"result": result_string}}
       ]
   )

6. Gemini processes tool result → generates next audio/text response
   └─ Back to W-1 step 4

FILES: main.py (_execute_tool, _handle_screen_process)
       core/tool_declarations.py (JSON schemas)
       actions/*.py (individual tool implementations)
```

---

## W-3: Memory Write

```
TRIGGER: User mentions a personal fact; Gemini decides to save it

1. Gemini calls tool: save_memory(category, key, value)
   Example: save_memory("preferences", "favorite_food", "sushi")

2. _execute_tool("save_memory", {"category": "preferences", "key": "favorite_food", "value": "sushi"})
   └─ NO asyncio executor — runs inline (JSON I/O is fast)

3. memory/memory_manager.py :: update_memory({
       "preferences": {
           "favorite_food": {
               "value": "sushi",
               "updated": "2026-09-03"
           }
       }
   })
   ├─ acquire RLock
   ├─ load long_term.json
   ├─ deep merge update
   ├─ json.dump → long_term.json (flush + fsync)
   └─ release RLock

4. session.send_tool_response(result="Memory saved successfully")

5. Tatsu says: "Got it! I've made a note of that."

FILES: main.py (_execute_tool)
       memory/memory_manager.py (update_memory, save_memory_to_disk)
       memory/long_term.json (persistent store)
```

---

## W-4: Memory Read (Session Start)

```
TRIGGER: TatsuLive.run() is called (every process start / reconnect)

1. _build_config() called in TatsuLive
   ├─ load prompt from core/prompt.txt
   ├─ format_memory_for_prompt() → memory string
   │   └─ Reads long_term.json → formats as:
   │      "### USER MEMORY\n**Identity:**\n  - name: Alex (updated 2026-09-03)"
   ├─ get_config_value("user_name") → "Alex"
   └─ builds final system_instruction:
      "{base_prompt}\n\nUser: Alex\n\n{memory_string}"

2. client.aio.live.connect(
       model="gemini-2.5-flash-native-audio-preview",
       config=types.LiveConnectConfig(
           system_instruction=full_system_instruction,
           tools=[...tool_declarations...],
           ...
       )
   )

3. Gemini session starts with full context of user's life

FILES: main.py (_build_config, run)
       core/prompt.txt (base persona)
       memory/memory_manager.py (format_memory_for_prompt)
       memory/long_term.json (data source)
```

---

## W-5: Vision Session (Screen / Camera)

```
TRIGGER: User asks "What do you see on my screen?" or "Look at this"

1. Gemini calls: screen_process(angle="screen", text="What am I looking at?")

2. _handle_screen_process(args) in main.py:
   ├─ Check cooldown: if last_vision_time < 4s → return "Vision on cooldown"
   ├─ _capture_screen(angle="screen"):
   │   ├─ mss.mss() context manager
   │   ├─ sct.grab(monitor) → raw BGRA pixels
   │   ├─ PIL.Image.fromarray(numpy_array)
   │   ├─ img.thumbnail((1280, 720), PIL.Image.BILINEAR)
   │   └─ BytesIO JPEG compress (quality=82)
   ├─ pending_vision = (jpeg_bytes, "What am I looking at?")
   ├─ last_vision_time = now
   └─ return "Processing screen..."

3. Gemini responds with intermediate: "Looking at your screen now..."
   └─ Audio plays while we wait for next turn_complete event

4. _receive_audio() sees: event.server_content.turn_complete = True
   └─ If pending_vision:
       session.send_client_content(
           turns={"parts": [
               {"inline_data": {"data": jpeg_bytes, "mime_type": "image/jpeg"}},
               {"text": "What am I looking at?"}
           ]},
           turn_complete=True
       )

5. Gemini sees the JPEG frame + question → analyzes → responds
   └─ Back to W-1 for audio response

CAMERA VARIANT: angle="camera"
   ├─ cv2.VideoCapture(0)
   ├─ ret, frame = cap.read()
   ├─ cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
   └─ Same flow from step 3

FILES: main.py (_handle_screen_process, _capture_screen)
       actions/screen_processor.py (helper functions)
```

---

## W-6: Dashboard Text Command

```
TRIGGER: User types a message in the phone dashboard UI

1. Phone browser: user types "Turn on dark mode" → clicks Send

2. JavaScript (dashboard/static/app.html):
   const enc = CryptoJS.AES.encrypt(JSON.stringify({cmd: "Turn on dark mode"}), sessionKey)
   ws.send(JSON.stringify({type: "command", enc: enc.toString()}))

3. FastAPI WebSocket handler (dashboard/server.py):
   ├─ Receives JSON message
   ├─ _decrypt_cbc(session_aes_key, enc_b64) → '{"cmd": "Turn on dark mode"}'
   └─ command_queue.put_nowait({"cmd": "Turn on dark mode"})

4. _process_dashboard_commands() [asyncio task in main.py]:
   ├─ command_queue.get() → {"cmd": "Turn on dark mode"}
   └─ session.send_client_content(
           turns={"parts": [{"text": "Turn on dark mode"}]},
           turn_complete=True
       )

5. Gemini processes as if user spoke the text
   └─ Tatsu responds via audio (and dashboard text feed)

FILES: dashboard/server.py (WebSocket handler, _decrypt_cbc, command_queue)
       dashboard/static/app.html (JS: CryptoJS.AES.encrypt, ws.send)
       main.py (_process_dashboard_commands)
```

---

## W-7: Phone Mic Relay

```
TRIGGER: User taps "Use Phone Mic" in dashboard

1. JavaScript: navigator.mediaDevices.getUserMedia({audio: true})
   └─ MediaRecorder captures PCM chunks (AudioContext, 16 kHz)
   └─ ws_audio.send(pcm_chunk_bytes)  [binary WebSocket]

2. FastAPI WebSocket /ws/phone-audio (dashboard/server.py):
   └─ phone_audio_queue.put_nowait(pcm_chunk_bytes)

3. _relay_phone_audio() [asyncio task in main.py]:
   ├─ _phone_active = True  (suppresses PC mic)
   └─ out_queue.put_nowait({"data": pcm_chunk_bytes, "mime_type": "audio/pcm;rate=16000"})

4. _send_realtime() picks up from out_queue → same as W-1 step 2

5. Tatsu responds via PC speakers (audio_in_queue → sounddevice)

CLEANUP: When phone mic WebSocket closes:
   └─ _phone_active = False  (PC mic resumes)

FILES: dashboard/server.py (_phone_audio_queue, /ws/phone-audio)
       main.py (_relay_phone_audio, _phone_active flag)
```

---

## W-8: File Upload and Analysis

```
TRIGGER: User drags a file onto the dashboard upload area

1. JavaScript: FormData upload → POST /api/upload
   Headers: Authorization: Bearer <token>

2. FastAPI /api/upload (dashboard/server.py):
   ├─ Verify Bearer token
   ├─ sanitize_filename(filename) → re.sub(r'[<>:"/\\|?*]', '_', name)
   ├─ Save to user's configured safe_root/uploads/filename
   └─ command_queue.put_nowait({"cmd": f"I uploaded a file: {safe_path}"})

3. Flows into W-6 from step 4 (dashboard command relay)

4. Gemini receives: "I uploaded a file: /Users/alex/uploads/report.pdf"
   └─ Gemini calls file_processor(file_path=safe_path, task="analyze")

5. actions/file_processor.py:
   ├─ Detect file type (extension)
   ├─ Read content (text, CSV parsed, image → base64, PPTX → text)
   └─ Send to Gemini 2.5 Flash for analysis
   └─ Return analysis summary string

6. Tatsu reads the summary aloud

FILES: dashboard/server.py (/api/upload)
       actions/file_processor.py
       main.py (_execute_tool)
```

---

## W-9: Dev Agent Task

```
TRIGGER: User says "Build me a Python web scraper for news articles"

1. Gemini calls: dev_agent(description="Python web scraper for news articles", project_dir="/Users/alex/projects/news-scraper")

2. actions/dev_agent.py:
   PLANNING PHASE:
   ├─ Gemini 2.5 Flash: "Generate a file list and architecture plan for: ..."
   ├─ Parse response → list of files to create
   └─ Tatsu says: "I'll create 4 files: main.py, scraper.py, utils.py, requirements.txt"

   IMPLEMENTATION PHASE:
   ├─ For each file:
   │   ├─ Gemini 2.5 Flash: "Write complete code for {filename}"
   │   └─ Write to disk at project_dir/filename
   └─ Tatsu says: "Files created. Running now..."

   EXECUTION + ERROR-FIX LOOP (max 5 iterations):
   ├─ subprocess.run(["python", "main.py"]) → capture stdout, stderr
   ├─ If error:
   │   ├─ Gemini 2.5 Flash: "Fix this error: {stderr}. File content: {code}"
   │   ├─ Apply fix
   │   └─ Retry
   └─ If success: Tatsu says "Your scraper is running!"

3. Return summary of what was created

FILES: actions/dev_agent.py
       main.py (_execute_tool)
```

---

## W-10: Wake Word Trigger

```
TRIGGER: User says "Hey Tatsu" while Tatsu is not running

WAKE SERVICE (wake_service.py) — runs constantly as background process:

1. sr.Recognizer() loop with Google Web Speech API (free)
   └─ Listens for "hey tatsu" / "tatsu" / "wake up"

2. On detection: socket.create_connection(("127.0.0.1", 39152), timeout=0.1)
   ├─ Connected → Tatsu already running → send wake signal via HTTP POST /api/wake
   └─ Refused → Tatsu not running → subprocess.Popen(["python", "main.py", "--wake-word"])

3. main.py receives --wake-word flag:
   └─ After session start, immediately sends:
      session.send_client_content(
          turns={"parts": [{"text": "The user just said 'hey Tatsu' — please respond warmly."}]},
          turn_complete=True
      )

4. Tatsu responds: "Hey! What do you need?"

FILES: wake_service.py
       main.py (--wake-word argument handling)
```

---

## W-11: Session Reconnect

```
TRIGGER: Network drop, Gemini timeout, or API error

1. _receive_audio() or _send_realtime() raises exception

2. asyncio.TaskGroup propagates exception → all tasks cancelled

3. Outer retry loop in TatsuLive.run():
   ├─ Log error to logs/tatsu.log
   ├─ await asyncio.sleep(2)  ← backoff
   ├─ _build_config()  ← reload memory, config
   ├─ client.aio.live.connect(...)  ← new session
   └─ Restart all TaskGroup tasks

4. Tatsu automatically resumes — user hears silence, then Tatsu is back

FILES: main.py (run(), retry loop)
```

---

## W-12: Reminder Fire

```
TRIGGER: reminder_manager finds a past-due reminder

1. On session start, _check_reminders() called

2. reminder_manager.py:
   ├─ Load memory/reminders.json
   ├─ For each reminder where trigger_time <= datetime.now():
   │   ├─ Add to due_list
   │   └─ Update trigger_time based on repeat schedule
   └─ Save updated reminders.json

3. For each due reminder:
   └─ session.send_client_content(
           turns={"parts": [{"text": f"REMINDER: {reminder.text}"}]},
           turn_complete=True
       )

4. Tatsu speaks: "Just a reminder — {reminder.text}"

FILES: memory/reminder_manager.py
       main.py (_check_reminders)
```

---

## W-13: Morning Briefing

```
TRIGGER: Startup with morning_brief_enabled = true

1. TatsuLive.run() → after session established:
   └─ If morning_brief_enabled:
       await _send_startup_briefing()

2. _send_startup_briefing():
   └─ session.send_client_content(
           turns={"parts": [{"text": """
               Give the user a brief, warm morning briefing. Include:
               - The current date and time
               - Any reminders due today
               - A summary of their active projects from memory
               - A single friendly motivational note
               Keep it under 60 seconds of speech.
           """}]},
           turn_complete=True
       )

3. Tatsu delivers the briefing via audio

FILES: main.py (_send_startup_briefing, run)
```

---

## W-14: Proactive Check-in

```
TRIGGER: _run_proactive_mode() asyncio task fires

1. await asyncio.sleep(60) loop

2. On fire: Check if user has been silent for > 60 seconds

3. session.send_client_content(
       turns={"parts": [{"text": """
           The user has been quiet for a while. Based on their recent projects and goals,
           offer a brief, natural check-in. Ask if they need help with anything.
           Keep it to one sentence.
       """}]},
       turn_complete=True
   )

4. Tatsu: "Still working on that scraper? Need anything?"

FILES: main.py (_run_proactive_mode)
```

---

## W-15: System Emergency Alert

```
TRIGGER: _run_system_monitor() detects critical resource usage

1. asyncio task loops every 2 seconds:
   └─ cpu = psutil.cpu_percent(interval=None)
   └─ ram = psutil.virtual_memory().percent
   └─ gpu = ctypes NVML query (if NVIDIA present)

2. If cpu > 95% for 3 consecutive checks:
   └─ session.send_client_content(
           turns={"parts": [{"text": "SYSTEM ALERT: CPU usage is critically high at {cpu}%. Please advise the user."}]},
           turn_complete=True
       )

3. Tatsu: "Heads up — your CPU is maxed out at 97%. Want me to check what's running?"

THRESHOLDS:
   CPU:  95% for 3 consecutive readings
   RAM:  90%
   GPU:  95% VRAM

FILES: actions/system_monitor.py
       main.py (_run_system_monitor)
```
