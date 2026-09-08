from flask import Flask, request, jsonify, send_from_directory, send_file
from pathlib import Path
import requests
import json
import re
import os
import sys
import time
import subprocess
from urllib.parse import quote, urljoin

# personas.py lives at the project root (one level up from python/), shared
# with terminal/diana_coding.py so Texty's prompt/model config never drifts
# between the web UI and the CLI. Imported here, early, because MODELS below
# needs TEXTY_MODEL/TEXTY_FALLBACKS/TEXTY_OPTIONS already defined.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from personas import (
    SYSTEM_PROMPT_TEXTY, TEXTY_MODEL, TEXTY_FALLBACKS, TEXTY_OPTIONS,
    build_time_context_note,
)

try:
    from bs4 import BeautifulSoup
except Exception:
    BeautifulSoup = None
try:
    import numpy as np
    import soundfile as sf
    SOUND_IMPORT_ERROR = None
except Exception as exc:
    np = None
    sf = None
    SOUND_IMPORT_ERROR = str(exc)
try:
    from TTS.api import TTS
    TTS_IMPORT_ERROR = None
except Exception as exc:
    TTS = None
    TTS_IMPORT_ERROR = str(exc)
from language_filter import clean_response
from agent_orchestrator import AgentOrchestrator
from agent_runtime import make_agent_executor


BASE_DIR = Path(__file__).resolve().parent
UI_DIR = BASE_DIR.parent / 'renderer'
app = Flask(__name__, static_folder=str(UI_DIR), static_url_path='')
DATA_DIR = Path(os.getenv('DIANA_DATA_DIR', str(BASE_DIR / 'data'))).expanduser().resolve()
AUDIO_DIR = DATA_DIR / 'generated_audio'
REFERENCE_VOICE_PATH = Path(os.getenv('DIANA_REFERENCE_VOICE', str(BASE_DIR / 'reference_voice.wav'))).expanduser().resolve()
OLLAMA_URL = os.getenv('OLLAMA_URL', 'http://127.0.0.1:11434/api/chat')
SILENCE_SECONDS = 0.25


def ollama_is_available():
    """Return a fast, non-blocking readiness signal for the local Ollama service."""
    tags_url = OLLAMA_URL.rsplit('/api/chat', 1)[0].rstrip('/') + '/api/tags'
    try:
        response = requests.get(tags_url, timeout=0.8)
        return 200 <= response.status_code < 300
    except requests.RequestException:
        return False

DATA_DIR.mkdir(parents=True, exist_ok=True)
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

@app.get('/health')
def health_endpoint():
    return jsonify({
        'status': 'ok',
        'service': 'diana',
        'tts_imported': TTS is not None,
        'audio_support': SOUND_IMPORT_ERROR is None,
        'device': tts_device,
        'ollama_available': ollama_is_available(),
        'backend_version': '2.5.6-beta',
    })

# ---------- Setup ----------
try:
    import torch
    _default_tts_device = 'cuda' if torch.cuda.is_available() else 'cpu'
except Exception:
    _default_tts_device = 'cpu'
tts_device = os.getenv('DIANA_TTS_DEVICE', _default_tts_device)
tts = None
tts_error = None

def get_tts():
    global tts, tts_error
    if tts is not None:
        return tts
    if tts_error is not None:
        raise RuntimeError(f"XTTS-v2 is unavailable: {tts_error}")
    if TTS is None:
        tts_error = TTS_IMPORT_ERROR or 'TTS package is not installed'
        raise RuntimeError(f"XTTS-v2 is unavailable: {tts_error}")
    try:
        print(f"Loading Diana (XTTS-v2) on {tts_device}...", flush=True)
        tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(tts_device)
        return tts
    except Exception as exc:
        tts_error = str(exc)
        raise RuntimeError(f"XTTS-v2 is unavailable: {exc}") from exc

# ---------- Model registry ----------
# Two personas, two models, two separate memory files.
# keep_alive=0 makes Ollama unload the model from VRAM the instant the
# response finishes - this is what lets Texty and Coding share the same
# 6GB card without fighting each other or the TTS engine.
# num_ctx caps how much context each model keeps in VRAM - smaller context
# window means a smaller KV cache means more VRAM headroom.

MODELS = {
    "texty": {
        "model": TEXTY_MODEL,
        "memory_file": str(DATA_DIR / "diana_texty_memory.json"),
        "fallbacks": TEXTY_FALLBACKS,
        "options": TEXTY_OPTIONS,
    },
    "coding": {
        "model": "qwen2.5-coder:7b",
        "memory_file": str(DATA_DIR / "diana_coding_memory.json"),
        "fallbacks": ["diana-coding:latest", "qwen2.5:7b"],
        "options": {
            "temperature": 0.4,
            "repeat_penalty": 1.15,
            "repeat_last_n": 256,
            "top_p": 0.9,
            "num_ctx": 16384,  # coding tasks need more room for pasted code
        },
    },
}

KEEP_ALIVE = "30s"  # short window so Ollama's automatic prompt-cache reuse
# still helps back-to-back messages to the SAME persona, without the model
# sitting resident long enough to risk both personas overlapping in VRAM if
# you switch quickly - 0 paid full prompt-reprocessing cost on every single
# message with no benefit at all, this is a deliberate middle ground.
_model_catalog_cache = {"checked_at": 0.0, "names": set()}


def available_ollama_models():
    now = time.time()
    if now - _model_catalog_cache["checked_at"] < 5:
        return _model_catalog_cache["names"]
    tags_url = OLLAMA_URL.rsplit('/api/chat', 1)[0].rstrip('/') + '/api/tags'
    try:
        response = requests.get(tags_url, timeout=0.8)
        response.raise_for_status()
        names = {str(item.get("name", "")).strip() for item in response.json().get("models", []) if item.get("name")}
        _model_catalog_cache.update({"checked_at": now, "names": names})
        return names
    except (requests.RequestException, ValueError, AttributeError):
        _model_catalog_cache.update({"checked_at": now, "names": set()})
        return set()


def resolve_model(persona):
    cfg = MODELS[persona]
    candidates = [cfg["model"], *cfg.get("fallbacks", [])]
    available = available_ollama_models()
    if not available:
        return candidates[0]
    return next((candidate for candidate in candidates if candidate in available), candidates[0])

AGENT_USER_AGENT = 'DianaLocalAgent/1.0 (+offline-first; user-requested web retrieval)'
AGENT_MAX_SOURCES = 5

# ---------- Agent: sandboxed Python execution ----------
# Same idea as the old diana_clearly.py sandbox - run code in a throwaway
# file with a hard timeout - but reachable from the web UI's "Run" button
# instead of a terminal y/n prompt.
CODE_TIMEOUT_SECONDS = 10

def run_python_code(code):
    temp_file = f"_diana_exec_{int(time.time()*1000)}.py"
    with open(temp_file, "w", encoding="utf-8") as f:
        f.write(code)
    try:
        result = subprocess.run(
            ["python", temp_file],
            capture_output=True,
            text=True,
            timeout=CODE_TIMEOUT_SECONDS
        )
        return result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return "", f"[Execution stopped: exceeded {CODE_TIMEOUT_SECONDS} second time limit]"
    finally:
        try:
            os.remove(temp_file)
        except (PermissionError, FileNotFoundError):
            pass

# How many past turns (user+assistant pairs) actually get sent to the model
# per request. The full history still gets saved to disk - this only trims
# what travels in the prompt, which keeps VRAM/prompt-eval cost down as a
# conversation grows long.
MAX_TURNS_SENT = 12

# ---------- Personalities ----------
# Diana Coding's web-chat prompt is deliberately simpler than the terminal
# one in terminal/diana_coding.py - no read_file/run_shell_command/ADB tools
# here, just the sandboxed run_python_code via /agent/run_code. Sharing a
# single string with the terminal would either overclaim tools this surface
# doesn't have, or hide the ones it does.
SYSTEM_PROMPT_CODING = """You are Diana Coding - the engineering side of Diana.
You're talking with the user through the web chat, not the terminal, so you
don't have file or shell tools here - if a task genuinely needs them, say so
plainly and suggest they use the Diana Coding terminal (diana.bat) instead.

Be direct and technical, with a light touch of personality and humor - not
stiff, not a comedian, just someone who's actually enjoyable to work with.
When you're debugging or explaining a problem, work through it calmly and
directly, without hedging every sentence - confidence in HOW you talk
doesn't mean skipping the verification of WHAT you claim (see "before you
say a task is done" below, that part is non-negotiable).

Code quality comes from concrete habits, not from claiming expertise -
telling yourself "act like a veteran" doesn't add knowledge you don't
already have, it just risks sounding more confident than you've verified.
These habits are what "senior-level" code actually looks like in practice:

- Fix root causes, not symptoms. Before writing a fix, ask: is this the
  simplest, most direct change that addresses why the problem happens - not
  just a check that papers over one symptom of it?
- Match complexity to the task. A simple, well-defined request gets a
  simple, direct solution - no speculative configurability, no abstraction
  for a use case that doesn't exist yet. Complexity is earned by a real
  requirement in front of you, not added by default.
- Public/exported functions get a short docstring even when comments are
  otherwise off by default (see below) - that's the contract other code
  relies on, not narration.

None of this is about sounding impressive - it's about the code still
making sense to someone reading it (including you) in six months.

Match effort to the task: for a quick or well-defined ask, just answer or
write the code directly. For anything nontrivial or ambiguous, briefly lay
out your plan before diving in.

If the user's approach isn't the one you'd pick, say so and explain the
better option before you commit to writing it their way.

If someone doesn't understand a piece of code, teach it step by step like an
actual teacher would, not a wall of text - check they're following before
moving to the next bit.

Keep code comments minimal by default - only add them when asked, or where a
line is genuinely non-obvious, or on public/exported functions (see above).
Don't narrate the obvious.

If the user's technical call is clearly wrong, tell them plainly why, then
wait for their decision - don't just override it and don't just go along
with it either.

If you spot a bug or issue outside what was actually asked, flag it clearly
and move on - don't fix it without being asked.

Wrap up with a short, clear summary of what changed - not a full essay.

Before you say a task is done, actually double-check the result (re-read the
code, reason through the logic, or note explicitly what you weren't able to
verify) - never claim something works without having checked it.

Match the user's language for explanations - Arabic in, Arabic out; English
in, English out. Code itself stays in English regardless.

No emojis.

Never say you are Qwen or mention being made by Alibaba - you are Diana
Coding, full stop.
"""

SYSTEM_PROMPTS = {
    "texty": SYSTEM_PROMPT_TEXTY,
    "coding": SYSTEM_PROMPT_CODING,
}

agent_executor = make_agent_executor(
    models=MODELS,
    system_prompts=SYSTEM_PROMPTS,
    ollama_url=OLLAMA_URL,
    keep_alive=KEEP_ALIVE,
    max_sources=AGENT_MAX_SOURCES,
)
agent_orchestrator = AgentOrchestrator(DATA_DIR, agent_executor)

# ---------- Memory ----------
def load_memory(persona):
    cfg = MODELS[persona]
    if os.path.exists(cfg["memory_file"]):
        try:
            with open(cfg["memory_file"], "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError):
            print(f"[Warning: {persona} memory file was corrupted, starting fresh]")
    return [{"role": "system", "content": SYSTEM_PROMPTS[persona]}]

def save_memory(persona, history):
    cfg = MODELS[persona]
    with open(cfg["memory_file"], "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

conversation_histories = {
    "texty": load_memory("texty"),
    "coding": load_memory("coding"),
}

# Private conversations deliberately live only in this Python process. They are
# never written to the public persona memory files and disappear when the local
# backend restarts.
private_conversation_histories = {}


def build_outgoing_messages_from_history(history):
    system_msg = history[0]
    rest = history[1:]
    trimmed = rest[-(MAX_TURNS_SENT * 2):]
    return [system_msg] + trimmed


def build_outgoing_messages(persona):
    """System prompt + last MAX_TURNS_SENT turns only. Keeps prompt size
    (and therefore VRAM/prompt-eval time) bounded even after weeks of
    conversation, while the full history still lives on disk untouched."""
    history = conversation_histories[persona]
    system_msg = history[0]  # always the system prompt, saved at index 0
    rest = history[1:]
    trimmed = rest[-(MAX_TURNS_SENT * 2):]
    return [system_msg] + trimmed

# ---------- Anti-repetition tracking ----------
# We keep a short rolling log of how recent replies opened and closed so we
# can nudge the model away from reusing the same patterns, without baking
# that instruction permanently into saved memory.

RECENT_PATTERNS_WINDOW = 6

def _first_words(text, n=6):
    words = text.strip().split()
    return " ".join(words[:n])

def _last_words(text, n=6):
    words = text.strip().split()
    return " ".join(words[-n:])

def get_recent_patterns(persona):
    history = conversation_histories[persona]
    assistant_msgs = [m["content"] for m in history if m["role"] == "assistant"]
    recent = assistant_msgs[-RECENT_PATTERNS_WINDOW:]
    openings = [_first_words(m) for m in recent if m.strip()]
    closings = [_last_words(m) for m in recent if m.strip()]
    return openings, closings

def build_anti_repetition_note(persona):
    openings, closings = get_recent_patterns(persona)
    if not openings and not closings:
        return None
    lines = []
    if openings:
        lines.append("Recent reply openings to avoid repeating: " + " | ".join(openings))
    if closings:
        lines.append("Recent reply closings to avoid repeating: " + " | ".join(closings))
    lines.append("Open and close this reply differently from all of the above.")
    return "\n".join(lines)

# ---------- Helpers ----------
def remove_emojis(text):
    return text.encode('ascii', 'ignore').decode('ascii')

def contains_code(text):
    return "```" in text

ARABIC_RANGE = re.compile(r'[\u0600-\u06FF]')

def detect_tts_language(text):
    """XTTS-v2 needs the correct language code to pronounce text properly.
    The old code hardcoded language='en' for every reply, which means any
    Arabic reply was being spoken with the wrong phonetic model. This does
    a simple character-range check and falls back to English otherwise."""
    return "ar" if ARABIC_RANGE.search(text) else "en"

def speak(text, filepath):
    if np is None or sf is None:
        raise RuntimeError(f"audio dependencies are unavailable: {SOUND_IMPORT_ERROR}")
    lang = detect_tts_language(text)
    get_tts().tts_to_file(
        text=text,
        speaker_wav=REFERENCE_VOICE_PATH,
        language=lang,
        file_path=filepath,
        speed=1.0
    )
    data, samplerate = sf.read(filepath)
    silence = np.zeros(int(SILENCE_SECONDS * samplerate), dtype=data.dtype)
    padded = np.concatenate([silence, data])
    sf.write(filepath, padded, samplerate)

# ---------- Routes: serve the UI ----------
@app.route('/')
def index():
    return send_from_directory(str(UI_DIR), 'index.html')

@app.route('/ide')
@app.route('/ide.html')
def ide():
    return send_from_directory(str(UI_DIR), 'ide.html')

@app.route('/vendor/<path:filename>')
def vendor(filename):
    return send_from_directory(str(BASE_DIR.parent / 'vendor'), filename)

@app.route('/style.css')
def style():
    return send_from_directory(str(UI_DIR), 'style.css')

@app.route('/audio/<filename>')
def audio(filename):
    filepath = str(AUDIO_DIR / filename)
    return send_file(filepath, mimetype='audio/wav')

# ---------- Route: real GPU VRAM status (for the sidebar panel) ----------
@app.route('/vram_status')
def vram_status():
    """Reads real GPU memory usage via nvidia-smi. The browser has no way to
    see actual VRAM, so the frontend used to show an honest N/A - this gives
    it real numbers instead, straight from the machine Diana runs on."""
    candidates = [
        "nvidia-smi",
        r"C:\Windows\System32\nvidia-smi.exe",
        r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe",
    ]
    last_error = None
    for exe in candidates:
        try:
            result = subprocess.run(
                [exe, "--query-gpu=memory.used,memory.total",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=3
            )
            if result.returncode != 0:
                last_error = f"{exe} exited with code {result.returncode}: {result.stderr.strip()}"
                continue
            used_mb, total_mb = result.stdout.strip().split(",")
            used_gb = float(used_mb.strip()) / 1024
            total_gb = float(total_mb.strip()) / 1024
            percent = (used_gb / total_gb) * 100 if total_gb > 0 else 0
            return jsonify({
                "available": True,
                "used_gb": round(used_gb, 2),
                "total_gb": round(total_gb, 2),
                "percent": round(percent, 1)
            })
        except FileNotFoundError:
            last_error = f"{exe} not found"
            continue
        except Exception as e:
            last_error = f"{exe} raised: {e}"
            continue

    print(f"[/vram_status] all candidates failed - last error: {last_error}")
    return jsonify({"available": False, "debug_error": last_error})

# ---------- Routes: local Agent Orchestrator ----------
@app.route('/agents/tasks', methods=['GET'])
def agents_tasks_endpoint():
    try:
        limit = int(request.args.get('limit', 12))
    except (TypeError, ValueError):
        limit = 12
    return jsonify({"tasks": agent_orchestrator.list_tasks(limit)})


@app.route('/agents/run', methods=['POST'])
def agents_run_endpoint():
    data = request.get_json(force=True) or {}
    command = str(data.get('command') or '').strip()
    if not command:
        return jsonify({"error": "empty agent command"}), 400
    try:
        task = agent_orchestrator.create_task(
            command=command,
            persona=data.get('persona', 'texty'),
            mode=data.get('mode', 'auto'),
            private=bool(data.get('private', False)),
            source=data.get('source', 'chat'),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"task": task}), 202


@app.route('/agents/tasks/<task_id>', methods=['GET'])
def agents_task_endpoint(task_id):
    task = agent_orchestrator.get_task(task_id)
    if not task:
        return jsonify({"error": "task not found"}), 404
    return jsonify({"task": task})


@app.route('/agents/tasks/<task_id>/cancel', methods=['POST'])
def agents_cancel_endpoint(task_id):
    if not agent_orchestrator.cancel_task(task_id):
        return jsonify({"error": "task is not running"}), 409
    return jsonify({"status": "cancelling", "task_id": task_id})


@app.route('/agents/schedules', methods=['GET', 'POST'])
def agents_schedules_endpoint():
    if request.method == 'GET':
        return jsonify({"schedules": agent_orchestrator.list_schedules()})
    data = request.get_json(force=True) or {}
    command = str(data.get('command') or '').strip()
    if not command:
        return jsonify({"error": "empty scheduled command"}), 400
    schedule = agent_orchestrator.create_schedule(
        name=data.get('name', 'DIANA ROUTINE'),
        command=command,
        frequency=data.get('frequency', 'daily'),
        time_text=data.get('time', '09:00'),
        interval_minutes=data.get('interval_minutes', 1440),
        persona=data.get('persona', 'texty'),
        mode=data.get('mode', 'auto'),
    )
    return jsonify({"schedule": schedule}), 201


@app.route('/agents/knowledge', methods=['GET'])
def agents_knowledge_endpoint():
    try:
        limit = int(request.args.get('limit', 20))
    except (TypeError, ValueError):
        limit = 20
    return jsonify({"notes": agent_orchestrator.list_knowledge(limit)})


@app.route('/agents/schedules/<schedule_id>', methods=['PATCH', 'DELETE'])
def agents_schedule_item_endpoint(schedule_id):
    if request.method == 'DELETE':
        return jsonify({"deleted": agent_orchestrator.delete_schedule(schedule_id)})
    data = request.get_json(force=True) or {}
    schedule = agent_orchestrator.toggle_schedule(schedule_id, bool(data.get('enabled', True)))
    if not schedule:
        return jsonify({"error": "schedule not found"}), 404
    return jsonify({"schedule": schedule})

# ---------- Route: reset a persona's memory ----------
@app.route('/reset', methods=['POST'])
def reset_endpoint():
    data = request.get_json(force=True)
    persona = data.get('persona', 'texty')
    if persona not in MODELS:
        return jsonify({"error": f"unknown persona '{persona}'"}), 400
    conversation_histories[persona] = [{"role": "system", "content": SYSTEM_PROMPTS[persona]}]
    private_conversation_histories.clear()
    save_memory(persona, conversation_histories[persona])
    return jsonify({"status": "ok", "persona": persona})

# ---------- Route: agent code execution ----------
@app.route('/agent/run_code', methods=['POST'])
def agent_run_code():
    data = request.get_json(force=True)
    code = (data.get('code') or '').strip()
    persona = data.get('persona', 'coding')

    if not code:
        return jsonify({"error": "empty code"}), 400
    if persona not in MODELS:
        return jsonify({"error": f"unknown persona '{persona}'"}), 400

    output, error = run_python_code(code)

    # Feed the result back into that persona's memory as a user-role message,
    # the same way diana_clearly.py did it - so on the next turn Diana
    # already knows what happened when the code ran, without us having to
    # trigger an extra LLM call right now.
    result_summary = f"[Code execution result]\nOutput: {output}\nError: {error}"
    history = conversation_histories[persona]
    history.append({"role": "user", "content": result_summary})
    save_memory(persona, history)

    return jsonify({"output": output, "error": error})

# ---------- Route: chat ----------
@app.route('/chat', methods=['POST'])
def chat_endpoint():
    data = request.get_json(force=True)
    message = (data.get('message') or '').strip()
    persona = data.get('persona', 'texty')
    voice = bool(data.get('voice', False))

    if not message:
        return jsonify({"error": "empty message"}), 400

    if persona not in MODELS:
        return jsonify({"error": f"unknown persona '{persona}'"}), 400

    cfg = MODELS[persona]
    model_name = resolve_model(persona)
    is_private = bool(data.get('private_chat', False))
    private_id = str(data.get('private_id') or '').strip()
    if is_private and (not private_id or len(private_id) > 160):
        return jsonify({"error": "private chat requires a valid session id"}), 400

    if is_private:
        private_key = f"{persona}:{private_id}"
        history = private_conversation_histories.setdefault(
            private_key,
            [{"role": "system", "content": SYSTEM_PROMPTS[persona]}]
        )
        history.append({"role": "user", "content": message})
        outgoing_messages = build_outgoing_messages_from_history(history)
        note = None
        if persona == "texty":
            outgoing_messages = outgoing_messages + [{"role": "system", "content": build_time_context_note()}]
    else:
        history = conversation_histories[persona]
        history.append({"role": "user", "content": message})
        # Build the outgoing message list: trimmed history + transient
        # notes (anti-repetition, and for Texty, the current time/occasion).
        # None of these transient notes are ever saved to memory.
        outgoing_messages = build_outgoing_messages(persona)
        note = build_anti_repetition_note(persona)
        if note:
            outgoing_messages = outgoing_messages + [{"role": "system", "content": note}]
        if persona == "texty":
            outgoing_messages = outgoing_messages + [{"role": "system", "content": build_time_context_note()}]

    def call_ollama():
        payload = {
            "model": model_name,
            "messages": outgoing_messages,
            "stream": False,
            "keep_alive": KEEP_ALIVE,
            "options": cfg["options"],
        }
        resp = requests.post(OLLAMA_URL, json=payload, timeout=180)
        resp.raise_for_status()
        return resp.json().get("message", {}).get("content", "").strip()

    try:
        raw_reply = call_ollama()
        reply = clean_response(raw_reply, regenerate_fn=call_ollama, max_retries=2)
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Can't reach Ollama - is it running? (ollama serve)"}), 503
    except requests.exceptions.Timeout:
        return jsonify({"error": f"{model_name} took too long to respond"}), 504
    except Exception as e:
        return jsonify({"error": f"LLM error: {e}"}), 500

    history.append({"role": "assistant", "content": reply})
    if not is_private:
        save_memory(persona, history)

    audio_url = None
    if voice and reply and not contains_code(reply):
        clean = remove_emojis(reply).strip()
        if clean:
            filename = f"reply_{int(time.time()*1000)}.wav"
            filepath = str(AUDIO_DIR / filename)
            try:
                speak(clean, filepath)
                audio_url = f"/audio/{filename}"
            except Exception as e:
                print(f"[TTS error: {e}]")

    return jsonify({"reply": reply, "audio_url": audio_url, "persona": persona, "model": model_name, "private": is_private})

if __name__ == '__main__':
    print("\nServer running at http://localhost:5000\n")
    app.run(host=os.getenv('DIANA_HOST', '127.0.0.1'), port=int(os.getenv('DIANA_PORT', '5000')), debug=False, use_reloader=False)