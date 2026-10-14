# Tatsu — Visual & Interaction Design System

> This document defines the visual philosophy, user experience guidelines, design tokens, HUD layout specifications, and dynamic animation states for the **Tatsu** desktop assistant and mobile dashboard.

---

## 1. Design Philosophy: Human, Warm & High-Tech

Traditional AI interfaces often lean toward cold, clinical, or overly militaristic aesthetics (e.g., sharp neon reds, harsh monochrome terminals). Tatsu rejects this in favor of a **warm, organic cyberpunk** visual language:

- **Ethereal Glassmorphism**: Translucent surfaces, subtle back-drop blurs, soft boundary highlights, and organic depth.
- **Warm Futuristic Accents**: Balanced blends of cyan (`#00D4FF`), violet (`#7928CA`), soft amber (`#F5A623`), and deep obsidian (`#0A0B10`).
- **Alive & Responsive Feedback**: Micro-animations, glowing pulse rings during listening, ripple effects on voice output, and dynamic state transitions that make Tatsu feel attentive and present.

---

## 2. Design Tokens & Color Palette

### 2.1 Core Palette

| Token | Hex Value | Semantic Role |
|-------|-----------|---------------|
| `--bg-base` | `#0A0B10` | Primary deep void canvas background |
| `--bg-surface-glass` | `rgba(18, 20, 29, 0.72)` | Primary frosted panel surface |
| `--bg-surface-elevated` | `rgba(28, 31, 46, 0.85)` | Floating dialogs, popovers, and active cards |
| `--border-subtle` | `rgba(255, 255, 255, 0.08)` | Standard card and container borders |
| `--border-accent` | `rgba(0, 212, 255, 0.40)` | Focus, active state, and listening highlight borders |
| `--accent-cyan` | `#00D4FF` | Primary active accent (listening, online, interactive) |
| `--accent-violet` | `#7928CA` | Secondary depth accent (AI thinking, processing) |
| `--accent-amber` | `#FF9900` | Warning, system resource alerts, and reminder badges |
| `--accent-emerald` | `#00E676` | Success status, memory save confirmation, tool finished |
| `--text-primary` | `#F3F4F6` | High-contrast body text and headers |
| `--text-secondary` | `#9CA3AF` | Subtitles, timestamps, and secondary captions |
| `--text-dim` | `#6B7280` | Log timestamps, version labels, and subtle markers |

### 2.2 Glassmorphism Specification
```css
.glass-panel {
  background: var(--bg-surface-glass);
  backdrop-filter: blur(16px) saturate(180%);
  -webkit-backdrop-filter: blur(16px) saturate(180%);
  border: 1px solid var(--border-subtle);
  border-radius: 16px;
  box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
}
```

---

## 3. Typography & Font Hierarchy

- **Primary Font**: `Inter`, `system-ui`, `-apple-system`, `sans-serif` (clean, modern legibility).
- **Code & Metric Font**: `JetBrains Mono`, `Fira Code`, `Consolas`, `monospace` (clear distinction for tool outputs and system specs).

| Hierarchy | Size | Weight | Line Height | Usage |
|-----------|------|--------|-------------|-------|
| Display H1 | 24px | 700 | 1.2 | Main HUD header / modal title |
| Section H2 | 18px | 600 | 1.3 | Panel categories (Memory, Skills, Status) |
| Body Main | 14px | 400 | 1.5 | Conversation transcript & messages |
| Metadata | 12px | 500 | 1.4 | Timestamps, tool names, badges |
| Monospace | 12px | 400 | 1.4 | Code blocks, system stats, JSON |

---

## 4. HUD Visual States & Animations

The desktop HUD widget transitions across 5 distinct visual states reflecting Tatsu's internal cognitive mode:

```
┌──────────────────────────────────────────────────────────────┐
│                      TATSU HUD MODES                         │
│                                                              │
│  1. IDLE (Ambient Presence)                                  │
│     Soft breathing glow, minimal UI footprint                │
│     Pulse: 0.2 Hz, Opacity: 0.6, Cyan/Dark Violet aura       │
│                                                              │
│  2. LISTENING (Audio Ingestion)                              │
│     Dynamic soundwave visualizer, bright cyan glow ring      │
│     Reactive waveform scaled by mic amplitude                │
│                                                              │
│  3. THINKING / PROCESSING (Tool Routing & LLM Inference)     │
│     Rotating dual-ring particle orbit, violet accent         │
│     Speed: 1.2 rev/sec, gradient stroke                      │
│                                                              │
│  4. SPEAKING (Synthesizing & Streaming Voice)                │
│     Concentric pulsing ripples radiating outward             │
│     Modulated frequency matching audio playback level        │
│                                                              │
│  5. EMERGENCY / ALERT (Hardware Warning)                     │
│     Subtle amber flash border with warning badge             │
└──────────────────────────────────────────────────────────────┘
```

### Keyframe Animation Snippets

```css
/* Breathing idle pulse */
@keyframes ambientGlow {
  0%, 100% {
    box-shadow: 0 0 15px rgba(0, 212, 255, 0.2), inset 0 0 15px rgba(0, 212, 255, 0.1);
  }
  50% {
    box-shadow: 0 0 28px rgba(121, 40, 202, 0.35), inset 0 0 20px rgba(121, 40, 202, 0.15);
  }
}

/* Audio active pulse */
@keyframes voiceRipple {
  0% {
    transform: scale(0.98);
    border-color: rgba(0, 212, 255, 0.8);
  }
  50% {
    transform: scale(1.02);
    border-color: rgba(0, 230, 118, 0.9);
  }
  100% {
    transform: scale(0.98);
    border-color: rgba(0, 212, 255, 0.8);
  }
}
```

---

## 5. Desktop Floating HUD Layout

The desktop UI (`ui.py`) uses a compact, non-intrusive floating WebEngine widget positioned at the bottom-right of the primary monitor by default:

```
┌───────────────────────────────────────────────────────────────┐
│  [●] TATSU AI              [ 82% CPU | 45% RAM ]     [_] [X]  │  <- Title Bar
├───────────────────────────────────────────────────────────────┤
│                                                               │
│   ┌───────────────────────────────────────────────────────┐   │
│   │                     ORB VISUALIZER                    │   │
│   │                 (((   ● TATSU   )))                  │   │
│   │                    State: Listening...                │   │
│   └───────────────────────────────────────────────────────┘   │
│                                                               │
│   TRANSCRIPT FEED                                             │
│   ┌───────────────────────────────────────────────────────┐   │
│   │ [14:21] You: What is on my schedule today?            │   │
│   │ [14:21] Tatsu: You have a team sync at 3 PM and an    │   │
│   │         unresolved code review for the API layer.     │   │
│   └───────────────────────────────────────────────────────┘   │
│                                                               │
│   ACTIVE ACTION BANNER                                        │
│   ┌───────────────────────────────────────────────────────┐   │
│   │ ⚡ [Tool Executed: reminder.list_reminders()]          │   │
│   └───────────────────────────────────────────────────────┘   │
│                                                               │
│   ┌─────────────────────────────────────────────────┬─────┐   │
│   │ Type a command or ask a question...             │ Mic │   │  <- Input bar
│   └─────────────────────────────────────────────────┴─────┘   │
└───────────────────────────────────────────────────────────────┘
```

---

## 6. Mobile Dashboard UX Layout (`app.html`)

For remote control via smartphone browser:

- **Single Column Stacked**: Optimized for vertical mobile viewport (375px–430px width).
- **Sticky Voice PTT Button**: Large floating action button at bottom center for Push-To-Talk microphone streaming.
- **Direct Upload Dropzone**: One-tap camera/file picker to stream photos or documents directly to Tatsu's vision engine.
- **Live Memory Inspector**: Expandable drawer revealing categorized long-term memories with swipe-to-delete support.
- **Hardware Dashboard**: Live miniature sparklines for CPU, memory, and GPU usage updated via WebSocket every 2 seconds.
