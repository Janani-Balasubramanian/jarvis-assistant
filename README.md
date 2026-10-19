# Jarvis Personal Assistant

A Python desktop assistant with text chat, optional voice input, persistent local memory, task tracking, and tools for approved laptop actions. AI requests run through Groq; speech recognition and speech output run locally.

## Features

- Text conversation with model-selected tool calls.
- SQLite memory and preferences saved between sessions.
- Tasks, due dates, duplicate detection, completion, and offline briefings.
- Optional push-to-talk and "hey Jarvis" wake word.
- Local Whisper speech recognition and pyttsx3 speech output.
- Configurable app/website actions and confirmation before terminal commands.
- Unit tests for core behavior and confirmation handling.

This is a desktop application, so the repository link opens the source and setup instructions. It is not a hosted browser app.

## Setup

Requires Python 3.10 or newer. Windows PowerShell example:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:GROQ_API_KEY = "YOUR_GROQ_API_KEY"
Copy-Item actions.example.json actions.json
python jarvis.py
```

Create a key in your own [Groq account](https://console.groq.com/keys). Keep it in your environment; never commit it. The `.env.example` file is a reference only: this application does not automatically load `.env` files. Legacy setups using `OPENAI_API_KEY` are supported, but that value must be a Groq key because requests go to Groq.

The default model is `openai/gpt-oss-20b`, served by Groq. Override with `JARVIS_MODEL` if needed. Check [Groq's supported models](https://console.groq.com/docs/models) for availability.

Try: "Remember my preferred language is English", "Add a task to prepare my project demo", or "List my tasks". Type `exit` to quit.

## Voice mode

```powershell
python -m pip install -r requirements-voice.txt
python jarvis.py --voice
```

Press Enter and speak, or type a message. The first transcription downloads a Whisper model. A microphone and audio output device are required.

Optional wake word:

```powershell
python -m pip install "openwakeword>=0.6.0"
python jarvis.py --voice --wake --greet
```

`jarvis_startup.bat` starts voice mode on Windows from its own folder. Set your API key in the environment before launching it. Linux voice installations may also need PortAudio and eSpeak system libraries.

## Offline briefing and tests

```powershell
python jarvis.py --briefing
python -m unittest -v
```

Briefings and tests need no API key. Tests use an in-memory database and mock API calls; they do not alter saved personal data or run laptop commands.

## Configuration and privacy

| Variable | Purpose |
| --- | --- |
| `GROQ_API_KEY` | Groq authentication for chat |
| `JARVIS_MODEL` | Model ID; defaults to `openai/gpt-oss-20b` |
| `JARVIS_DB` | Database path; defaults to `jarvis.db` beside the script |
| `JARVIS_ACTIONS_FILE` | Path to a local actions configuration |
| `JARVIS_WHISPER_MODEL` | Speech model size; defaults to `small` |
| `JARVIS_LANG` | Speech language; defaults to `en`; accepts `auto` |
| `JARVIS_MIC_THRESHOLD` | Optional microphone threshold override |
| `JARVIS_VOICE_RATE` | Speech speed; defaults to `175` |

The database, API keys, virtual environments, and personal action settings are excluded from Git. Saved memory and conversation text are included in AI requests when you chat. Review actions before enabling them; terminal commands require confirmation.

The code has extension hooks for notes, coding projects, Gmail, and Calendar. Their modules are not included in this repository, and their integrations are unavailable unless implemented separately.

## Validation

Checked on 19 October 2026 using Windows and Python 3.12:

- 11 automated tests passed.
- Live Groq text generation passed.
- Live model tool calling (`get_current_time`) and final response passed.
- Voice dependencies were present in the existing local environment. Microphone recording, transcription, wake-word recognition, and speaker playback have not been tested end to end.

The previous default Llama model was unavailable to the configured account. This version uses a model verified by a live request. No performance or latency benchmark is claimed.
