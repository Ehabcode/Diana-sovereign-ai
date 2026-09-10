import requests
import json
import re
import os
import time
import random
import math
import subprocess
import threading
import queue
import difflib
import tempfile
import shlex
import platform
import sys

from android_adb import (
    find_adb,
    get_device_info,
    list_devices,
    list_user_apps,
    read_only_device_check,
    run_adb,
    validate_package_name,
)
from network import local_network_inventory, local_open_ports, local_network_scan
from usb import list_directory as usb_list_directory
from usb import list_removable_mounts

# Voice is optional. The coding agent must still start when CUDA/audio/TTS
# dependencies are unavailable; the model is loaded lazily only when enabled.
try:
    import torchaudio as ta
    from chatterbox.tts_turbo import ChatterboxTurboTTS
    import sounddevice as sd
    import soundfile as sf
    HAS_TTS = True
except Exception:
    ta = None
    ChatterboxTurboTTS = None
    sd = None
    sf = None
    HAS_TTS = False

try:
    from colorama import init as colorama_init, Fore, Style
    colorama_init(autoreset=True)
    HAS_COLOR = True
except ImportError:
    HAS_COLOR = False

try:
    from ddgs import DDGS
    HAS_WEB_SEARCH = True
except ImportError:
    DDGS = None
    HAS_WEB_SEARCH = False

try:
    import trafilatura
    HAS_TRAFILATURA = True
except ImportError:
    trafilatura = None
    HAS_TRAFILATURA = False

try:
    import msvcrt  # Windows-only: lets us catch a keypress without blocking
    HAS_MSVCRT = True
except ImportError:
    HAS_MSVCRT = False

# On Linux/macOS, importing readline is enough to give input() free arrow-key
# history for the lifetime of the process - nothing else to do here. Windows
# has no built-in equivalent, so input_with_history() below hand-rolls it
# with msvcrt instead, further down the file.
try:
    import readline  # noqa: F401
except ImportError:
    pass


try:
    sys.stdout.reconfigure(encoding='utf-8')
except (AttributeError, ValueError):
    pass
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)

# personas.py lives at the project root, shared with python/server.py so
# Texty's prompt/model config is identical whether you talk to her here or
# in the web UI.
sys.path.insert(0, PROJECT_DIR)
from personas import (
    SYSTEM_PROMPT_TEXTY_TERMINAL, TEXTY_MODEL, TEXTY_FALLBACKS, TEXTY_OPTIONS,
    build_time_context_note,
)


# ---------- Dark purple (#6F4A8E) color palette (falls back to plain text if
# colorama isn't installed - "pip install colorama --break-system-packages") ----------
def _c(code):
    return code if HAS_COLOR else ""

def _rgb(r, g, b):
    # 24-bit ANSI true-color escape. Needs a modern terminal (Windows
    # Terminal / PowerShell 7 both support this); falls back cleanly via
    # HAS_COLOR the same way the old Fore.* codes did.
    return f"\033[38;2;{r};{g};{b}m"

PURPLE = _rgb(0x6F, 0x4A, 0x8E)          # #6F4A8E - base brand color
PURPLE_LIGHT = _rgb(0x9B, 0x7B, 0xC0)    # lighter tint, for emphasis/bright text
PURPLE_PALE = _rgb(0xC9, 0xB8, 0xE0)     # pale tint, for the banner glow

# ---------- Softer purple text tone (a bit less bold/bright than the base) ----------
PURPLE_SOFT = _rgb(0x87, 0x6B, 0xA3)     # muted mid-tone, kept for tool/system lines

# ---------- Gray tones for the actual conversation text ----------
GRAY_LIGHT = _rgb(0xD4, 0xD4, 0xD4)      # #D4D4D4 - Diana's replies (same as VS Code's default editor foreground)
GRAY_DARK = _rgb(0x6E, 0x6E, 0x6E)       # #6E6E6E - your own lines

C_BANNER = _c(PURPLE_LIGHT + Style.BRIGHT) if HAS_COLOR else ""
C_DIANA = _c(GRAY_LIGHT) if HAS_COLOR else ""
C_YOU = _c(GRAY_DARK) if HAS_COLOR else ""
C_TOOL = _c(PURPLE + Style.DIM) if HAS_COLOR else ""
C_TOOL_RESULT = _c(PURPLE + Style.DIM) if HAS_COLOR else ""
C_CONFIRM = _c(PURPLE_LIGHT + Style.BRIGHT) if HAS_COLOR else ""
C_ERROR = _c(Fore.RED + Style.BRIGHT) if HAS_COLOR else ""
C_BLOCKED = _c(Fore.RED + Style.BRIGHT) if HAS_COLOR else ""
C_SYSTEM = _c(PURPLE + Style.DIM) if HAS_COLOR else ""
C_RESET = _c(Style.RESET_ALL) if HAS_COLOR else ""

# ---------- Optional VS Code Dark+-style syntax highlighting for code blocks ----------
try:
    from pygments import highlight as _pyg_highlight
    from pygments.lexers import (
        get_lexer_by_name as _pyg_lexer_by_name, guess_lexer as _pyg_guess_lexer,
        get_lexer_for_filename as _pyg_lexer_for_filename,
    )
    from pygments.util import ClassNotFound as _PygClassNotFound
    from pygments.formatters import Terminal256Formatter as _PygTerminalFormatter
    from pygments.style import Style as _PygStyle
    from pygments.token import (
        Token as _PygToken, Keyword as _PygKeyword, Name as _PygName,
        Comment as _PygComment, String as _PygString, Number as _PygNumber,
        Operator as _PygOperator,
    )
    HAS_PYGMENTS = True

    class _VSCodeDarkPlusStyle(_PygStyle):
        # Matches VS Code's built-in "Dark+" theme token colors.
        background_color = "#1e1e1e"
        styles = {
            _PygToken: "#d4d4d4",
            _PygComment: "italic #6a9955",
            _PygKeyword: "#569cd6",
            _PygKeyword.Constant: "#569cd6",
            _PygName.Builtin: "#4ec9b0",
            _PygName.Function: "#dcdcaa",
            _PygName.Class: "#4ec9b0",
            _PygName.Decorator: "#dcdcaa",
            _PygString: "#ce9178",
            _PygNumber: "#b5cea8",
            _PygOperator: "#d4d4d4",
        }

    _PYG_FORMATTER = _PygTerminalFormatter(style=_VSCodeDarkPlusStyle)
except ImportError:
    HAS_PYGMENTS = False

_CODE_FENCE_RE = re.compile(r"```(\w+)?\n?(.*?)```", re.DOTALL)

def print_diana_reply(text, color=None):
    """Print Diana's reply, highlighting ```fenced``` code blocks VS Code-style
    if pygments is installed; falls back to plain color for everyone else."""
    color = color if color is not None else C_DIANA
    if not HAS_PYGMENTS or "```" not in text:
        print(f"{color}{text}{C_RESET}")
        return

    pos = 0
    for m in _CODE_FENCE_RE.finditer(text):
        prose = text[pos:m.start()]
        if prose:
            print(f"{color}{prose}{C_RESET}", end="")
        lang, code = m.group(1), m.group(2)
        try:
            lexer = _pyg_lexer_by_name(lang) if lang else _pyg_guess_lexer(code)
        except Exception:
            lexer = _pyg_guess_lexer(code) if code.strip() else None
        if lexer:
            print(_pyg_highlight(code, lexer, _PYG_FORMATTER), end="")
        else:
            print(f"{color}{code}{C_RESET}", end="")
        pos = m.end()
    tail = text[pos:]
    if tail:
        print(f"{color}{tail}{C_RESET}")
    else:
        print()

FILE_PREVIEW_MAX_LINES = 60

def print_file_preview(path, content):
    """Show the file Diana just read on screen, VS Code-style highlighted by
    its extension if pygments is available - so you actually see what she's
    looking at instead of it going straight to the model unseen. Truncated
    for display only; the full content (up to the tool's own 20000-char cap)
    is still what gets sent to the model."""
    print(f"\n{C_TOOL}[Reading: {path}]{C_RESET}")
    print(C_SYSTEM + "-" * 40 + C_RESET)
    if not content:
        print(f"{C_SYSTEM}[file is empty]{C_RESET}")
        print(C_SYSTEM + "-" * 40 + C_RESET)
        return
    lines = content.splitlines()
    truncated = len(lines) > FILE_PREVIEW_MAX_LINES
    preview_text = "\n".join(lines[:FILE_PREVIEW_MAX_LINES])

    lexer = None
    if HAS_PYGMENTS:
        try:
            lexer = _pyg_lexer_for_filename(path, preview_text)
        except _PygClassNotFound:
            lexer = _pyg_guess_lexer(preview_text) if preview_text.strip() else None
        except Exception:
            lexer = None

    if lexer:
        print(_pyg_highlight(preview_text, lexer, _PYG_FORMATTER), end="")
        if not preview_text.endswith("\n"):
            print()
    else:
        print(f"{C_SYSTEM}{preview_text}{C_RESET}")
    if truncated:
        print(f"{C_SYSTEM}[... {len(lines) - FILE_PREVIEW_MAX_LINES} more line(s) not shown on screen ...]{C_RESET}")
    print(C_SYSTEM + "-" * 40 + C_RESET)

def _spaced_caps(text):
    """'DIANA CODING' -> 'D I A N A   C O D I N G' (fake small-caps header look)."""
    return " ".join(text)

def _scale_line(line, factor):
    """Horizontally compress a line toward its center, simulating the line
    turning edge-on as part of a Y-axis 3D rotation."""
    width = len(line)
    new_width = max(1, round(width * factor))
    if new_width >= width:
        return line
    scaled_chars = []
    for i in range(new_width):
        src_i = min(width - 1, int(i / factor)) if factor > 0 else width // 2
        scaled_chars.append(line[src_i])
    scaled = "".join(scaled_chars)
    pad_left = (width - new_width) // 2
    pad_right = width - new_width - pad_left
    return (" " * pad_left) + scaled + (" " * pad_right)

def _depth_shade(factor):
    """Interpolate between a dim 'turned away' tone and a bright 'facing us'
    tone based on how wide the current frame is - a cheap lighting trick
    that makes the flat width-squeeze read as an actual 3D rotation."""
    if not HAS_COLOR:
        return ""
    dim = (0x3A, 0x28, 0x4A)      # deep shadow purple, logo edge-on
    bright = (0xC9, 0xB8, 0xE0)   # PURPLE_PALE, logo facing us
    r = int(dim[0] + (bright[0] - dim[0]) * factor)
    g = int(dim[1] + (bright[1] - dim[1]) * factor)
    b = int(dim[2] + (bright[2] - dim[2]) * factor)
    return _rgb(r, g, b)

_LOGO_ART = [
    r"   ___  _   _   _   _   _   _ ",
    r"  |   \| | / \ | \ | | / \ | |",
    r"  | |) | |/ _ \|  \| |/ _ \|_|",
    r"  |___/|_/_/ \_\_|\__/_/ \_(_)",
]
_LOGO_WIDTH = max(len(l) for l in _LOGO_ART)
_LOGO_ART_PADDED = [l.ljust(_LOGO_WIDTH) for l in _LOGO_ART]

def _clear_block(n_lines):
    """Move the cursor up n_lines and erase them - used to remove an
    animated block cleanly once it's done, or between its own frames."""
    print(f"\033[{n_lines}A", end="")
    for _ in range(n_lines):
        print("\033[2K", end="\n")
    print(f"\033[{n_lines}A", end="")

def _draw_logo_frame(angle, first_frame):
    factor = max(abs(math.cos(angle)), 0.035)
    color = _depth_shade(factor)
    if not first_frame:
        print(f"\033[{len(_LOGO_ART_PADDED)}A", end="")
    for line in _LOGO_ART_PADDED:
        print(f"\r\033[2K{color}{_scale_line(line, factor)}{C_RESET}")

def spin_logo(turns=2, steps_per_turn=28, frame_delay=0.026):
    """Play the DIANA ascii logo spinning a full 360 degrees on its vertical
    axis - width-squeeze plus a light/dark depth shade - then settle facing
    forward at full brightness. Used once at startup."""
    if not HAS_COLOR:
        for line in _LOGO_ART:
            print(line)
        return
    total_steps = steps_per_turn * turns
    for step in range(total_steps):
        angle = (step % steps_per_turn) / steps_per_turn * 2 * math.pi
        _draw_logo_frame(angle, first_frame=(step == 0))
        time.sleep(frame_delay)
    # final resting frame - full width, brightest tone, facing forward
    print(f"\033[{len(_LOGO_ART_PADDED)}A", end="")
    for line in _LOGO_ART_PADDED:
        print(f"\r\033[2K{C_BANNER}{line}{C_RESET}")

def spin_logo_while(stop_event, steps_per_turn=28, frame_delay=0.026):
    """Keep the logo spinning continuously until stop_event is set, then
    erase it completely. Used as the 'Diana is thinking' indicator so the
    logo never really stops turning while she's busy."""
    if not HAS_COLOR:
        return
    step = 0
    while not stop_event.is_set():
        angle = (step % steps_per_turn) / steps_per_turn * 2 * math.pi
        _draw_logo_frame(angle, first_frame=(step == 0))
        step += 1
        time.sleep(frame_delay)
    _clear_block(len(_LOGO_ART_PADDED))

# ---------- Purple rain: the everyday "thinking" indicator ----------
# Falling-sand style: every non-empty cell drops one row per frame if the
# cell below it is empty; once it lands on the floor or on top of another
# settled character, it just stays there - that's what makes it visibly
# "fall and pile up" instead of endlessly scrolling through. Brightness is
# keyed to row (fresh/falling = bright near the top, settled/resting =
# dim near the bottom), so no per-character age bookkeeping is needed.
_RAIN_WIDTH = 30
_RAIN_HEIGHT = 5
_RAIN_CHARS = "01/\\|_+-.:*<>ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_RAIN_SHADES = [_c(GRAY_LIGHT), _c(PURPLE_LIGHT), _c(PURPLE), _c(PURPLE_SOFT), _c(PURPLE_SOFT)]

def _rain_step(grid):
    for col in range(_RAIN_WIDTH):
        for row in range(_RAIN_HEIGHT - 2, -1, -1):
            if grid[row][col] != " " and grid[row + 1][col] == " ":
                grid[row + 1][col] = grid[row][col]
                grid[row][col] = " "
    for col in range(_RAIN_WIDTH):
        if grid[0][col] == " " and random.random() < 0.12:
            grid[0][col] = random.choice(_RAIN_CHARS)

def _rain_is_full(grid):
    return all(grid[_RAIN_HEIGHT - 1][col] != " " for col in range(_RAIN_WIDTH))

def _draw_rain_frame(grid, first_frame):
    if not first_frame:
        print(f"\033[{_RAIN_HEIGHT}A", end="")
    for row in range(_RAIN_HEIGHT):
        shade = _RAIN_SHADES[row] if HAS_COLOR else ""
        line = "".join(grid[row])
        print(f"\r\033[2K{shade}{line}{C_RESET}")

def spin_matrix_rain_while(stop_event, frame_delay=0.09):
    """The everyday reply-waiting indicator: purple characters fall and
    pile up at the floor; once the floor is full it clears and starts over.
    Kept separate from spin_logo_while on purpose - the opening banner and
    the first reply right after a persona switch still use the logo spin,
    this one is only for ordinary replies."""
    if not HAS_COLOR:
        return
    grid = [[" "] * _RAIN_WIDTH for _ in range(_RAIN_HEIGHT)]
    first_frame = True
    while not stop_event.is_set():
        if _rain_is_full(grid):
            grid = [[" "] * _RAIN_WIDTH for _ in range(_RAIN_HEIGHT)]
        _rain_step(grid)
        _draw_rain_frame(grid, first_frame)
        first_frame = False
        time.sleep(frame_delay)
    _clear_block(_RAIN_HEIGHT)

# Set right after a persona switch so the very next reply still uses the
# familiar logo spin (consistent with the opening banner); every reply
# after that uses the purple rain. Consumed (reset) the moment it's read.
JUST_SWITCHED_PERSONA = False

def pick_thinking_animation():
    global JUST_SWITCHED_PERSONA
    if JUST_SWITCHED_PERSONA:
        JUST_SWITCHED_PERSONA = False
        return spin_logo_while
    return spin_matrix_rain_while

def ollama_is_reachable():
    try:
        base = OLLAMA_URL.rsplit("/api/", 1)[0]
        requests.get(base, timeout=0.6)
        return True
    except Exception:
        return False

def gpu_offload_status(model_name=None):
    """Best-effort: asks Ollama's /api/ps how much of the currently loaded
    model's memory footprint actually landed in VRAM vs spilled to CPU RAM.
    Returns None if Ollama isn't reachable or the model isn't loaded right
    now (e.g. right after keep_alive=0 unloaded it) - never raises."""
    try:
        base = OLLAMA_URL.rsplit("/api/", 1)[0]
        response = requests.get(f"{base}/api/ps", timeout=5)
        response.raise_for_status()
        data = response.json()
        target = model_name or current_model_name()
        for m in data.get("models", []):
            if m.get("name") == target or m.get("model") == target:
                size = m.get("size", 0)
                size_vram = m.get("size_vram", 0)
                return {"size": size, "size_vram": size_vram,
                        "fully_on_gpu": size > 0 and size_vram >= size}
        return None
    except Exception:
        return None

def handle_gpu():
    status = gpu_offload_status()
    if status is None:
        print(f"{C_SYSTEM}[Couldn't check - either Ollama isn't reachable, or "
              f"{current_model_name()} isn't currently loaded (keep_alive=0 unloads "
              f"it right after each reply, so this is most accurate mid-conversation)]{C_RESET}")
        return
    size_gb = status["size"] / (1024 ** 3)
    vram_gb = status["size_vram"] / (1024 ** 3)
    if status["fully_on_gpu"]:
        print(f"{C_SYSTEM}[{current_model_name()}: fully on GPU - {vram_gb:.2f} GB in VRAM]{C_RESET}")
        return
    pct = (status["size_vram"] / status["size"] * 100) if status["size"] else 0
    print(f"{_c(Fore.YELLOW + Style.BRIGHT)}[{current_model_name()}: only {pct:.0f}% on GPU "
          f"({vram_gb:.2f} of {size_gb:.2f} GB) - the rest is running on CPU, which will feel "
          f"noticeably slower.{C_RESET}")
    print(f"{C_SYSTEM}  Two things worth trying:{C_RESET}")
    print(f"{C_SYSTEM}  1. Lower num_ctx further (/model won't do this - edit "
          f"DIANA_CODING_NUM_CTX or the Modelfile){C_RESET}")
    if CURRENT_PERSONA == "texty":
        print(f"{C_SYSTEM}  2. start_ollama already sets OLLAMA_FLASH_ATTENTION=1 + "
              f"OLLAMA_KV_CACHE_TYPE=q8_0 for you - if you started 'ollama serve' "
              f"manually instead, set those two first, they shrink Texty's context "
              f"VRAM footprint noticeably (qwen3 supports it).{C_RESET}")
    else:
        print(f"{C_SYSTEM}  2. Note: OLLAMA_FLASH_ATTENTION/KV_CACHE_TYPE (which "
              f"start_ollama sets) don't help Diana Coding's qwen2.5-coder - that "
              f"architecture isn't on Ollama's flash-attention allowlist yet.{C_RESET}")

def query_vram_usage():
    """Raw hardware-level VRAM usage via nvidia-smi (used/total MB) - this is
    the WHOLE card, not just Ollama's share, so it also reflects your
    browser, desktop compositor, anything else running. Returns None if
    nvidia-smi isn't found (no NVIDIA card, or drivers/PATH not set up)."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None
        line = result.stdout.strip().splitlines()[0]
        used_str, total_str = [p.strip() for p in line.split(",")]
        return int(used_str), int(total_str)
    except (subprocess.SubprocessError, OSError, ValueError, IndexError):
        return None

def handle_vram():
    usage = query_vram_usage()
    if usage is None:
        print(f"{C_SYSTEM}[Couldn't read VRAM - nvidia-smi isn't available. This only "
              f"works with an NVIDIA card that has drivers installed.]{C_RESET}")
        return
    used_mb, total_mb = usage
    pct = (used_mb / total_mb * 100) if total_mb else 0
    used_gb, total_gb = used_mb / 1024, total_mb / 1024
    bar_width = 30
    filled = min(bar_width, int(bar_width * pct / 100))
    bar = "\u2588" * filled + "\u2591" * (bar_width - filled)
    if pct < 70:
        color = _c(Fore.GREEN)
    elif pct < 90:
        color = _c(Fore.YELLOW)
    else:
        color = _c(Fore.RED + Style.BRIGHT)
    print(f"{color}[VRAM] {bar} {used_gb:.1f}/{total_gb:.1f} GB ({pct:.0f}%){C_RESET}")
    if pct >= 90:
        print(f"{color}  Card is nearly full - close other GPU apps (browser, games) "
              f"or expect slowdowns/OOM.{C_RESET}")

def banner():
    if not HAS_COLOR:
        print("=" * 52)
        print("  DIANA CODING // TERMINAL AGENT")
        print("  LOCAL & OFFLINE // qwen2.5-coder:7b")
        print("=" * 52)
        print("  made by Ehab.R")
        return
    spin_logo()
    status_dot = f"{_c(Fore.GREEN)}\u25cf{C_RESET}" if ollama_is_reachable() else f"{_c(Fore.RED)}\u25cf{C_RESET}"
    print(f"{C_SYSTEM}  {_spaced_caps('DIANA CODING')} // {_spaced_caps('TERMINAL AGENT')}  {status_dot}{C_RESET}")
    print(C_SYSTEM + "  LOCAL & OFFLINE // qwen2.5-coder:7b" + C_RESET)
    print(C_SYSTEM + "  " + "\u2508" * 44 + C_RESET)
    print(_c(Style.DIM) + "  made by Ehab.R" + C_RESET)



# ---------- Setup ----------
# The agent core starts without loading the optional voice model.
tts_model = None
try:
    import torch
    _DEFAULT_TTS_DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
except Exception:
    _DEFAULT_TTS_DEVICE = "cpu"
TTS_DEVICE = os.environ.get("DIANA_TTS_DEVICE", _DEFAULT_TTS_DEVICE)
OLLAMA_URL = os.environ.get("DIANA_OLLAMA_URL", "http://127.0.0.1:11434/api/chat")
REFERENCE_VOICE_PATH = os.environ.get("DIANA_REFERENCE_VOICE", os.path.join(PROJECT_DIR, "python", "reference_voice.wav"))
MEMORY_DIR = os.environ.get("DIANA_MEMORY_DIR", os.path.join(PROJECT_DIR, "memory"))
EXECUTION_LOG_FILE = os.environ.get("DIANA_EXECUTION_LOG", os.path.join(PROJECT_DIR, "logs", "diana_execution_log.txt"))
os.makedirs(MEMORY_DIR, exist_ok=True)
if os.path.dirname(EXECUTION_LOG_FILE):
    os.makedirs(os.path.dirname(EXECUTION_LOG_FILE), exist_ok=True)
KEEP_ALIVE = os.environ.get("DIANA_KEEP_ALIVE", "5m")
MAX_AGENT_STEPS = 15  # safety cap so a confused model can't loop forever
SUB_AGENT_MAX_STEPS = 8
SHELL_TIMEOUT_SECONDS = int(os.environ.get("DIANA_SHELL_TIMEOUT", "30"))
OLLAMA_TIMEOUT_SECONDS = int(os.environ.get("DIANA_OLLAMA_TIMEOUT", "180"))
MAX_COMMAND_OUTPUT_CHARS = 60000
MAX_EXCHANGES_SENT = 6  # how many past user-turns actually get sent to the
                         # model - the full history still gets saved to disk

# ---------- Personality ----------
SYSTEM_PROMPT_BASE = """You are Diana Coding - the engineering side of Diana, now
running as a terminal-based coding agent with real tools.

Be relaxed and easygoing in how you talk - a bit more casual than a typical
technical assistant, still sharp, direct, and technical, just genuinely
comfortable to sit and work with, not stiff and not a comedian.
When you're debugging, work through it calmly and directly - state what
you're checking and why, without hedging every sentence. Confidence in HOW
you talk doesn't mean skipping the verification of WHAT you claim - see the
"before you say a task is done" rule below, that part is non-negotiable.

Code quality comes from concrete habits, not from claiming expertise -
telling yourself "act like a 40-year veteran" doesn't add any knowledge you
don't already have, it just risks making you sound more confident than
you've actually verified. These habits are what "senior-level" code
actually looks like in practice:

- Fix root causes, not symptoms. Before writing a fix, ask: is this the
  simplest, most direct change that actually addresses why the problem
  happens - not just a check that papers over one symptom of it?
- Match complexity to the task. A simple, well-defined request gets a
  simple, direct solution - no speculative configurability, no abstraction
  layer for a use case that doesn't exist yet, no helper class for
  something a single function handles fine. Complexity is earned by a real
  requirement in front of you, not added by default. Over-abstracted code
  is harder to read, test, and debug than it's worth.
- Check for something similar before writing something new. A duplicate
  helper or a near-identical function that already exists elsewhere in the
  project is a bug waiting to diverge - search_files first if you're not
  sure something's already there.
- Public/exported functions get a short docstring even when comments are
  otherwise off by default (see below) - that's the contract other code
  relies on, not narration.

None of this is about sounding impressive - it's about the code still
making sense to someone reading it (including you) in six months.

Match effort to the task: for something quick and well-defined, just do it.
For anything nontrivial or ambiguous, briefly lay out your plan before
diving in, so the user can redirect you before you've written a line.

For any multi-step task, use update_todos to lay out the steps before you
start, and update each item's status as you go. This list is shown to the
user, so it has to reflect reality: an item only becomes "done" once you've
actually verified it, never just because you attempted it. A confident
summary is not evidence - running the code, running the tests, or re-reading
the actual result is evidence. Don't call a task finished while any todo
item is still pending or in_progress.

You have web_search and web_fetch - use them freely for anything current,
anything outside your training data, or any API/library detail you're not
fully sure of. Search first, then web_fetch the most promising result to
actually read it rather than guessing from the snippet alone. When you use
information from the web in your answer, say where it came from.

If the user asks for something one way but you think there's a genuinely
better approach, say so and explain it BEFORE you execute - don't silently
do it your way, and don't silently do it their way if you think it's wrong.
If their technical call is clearly wrong even after you've said your piece,
tell them plainly why and then wait for their decision - don't override it
yourself.

If someone doesn't understand a piece of code or asks you to explain, teach
it step by step like an actual teacher would - check they're following
before moving to the next bit, don't just dump the whole explanation at once.

Keep code comments minimal by default - only add them when asked, or where a
line is genuinely non-obvious, or on public/exported functions (see above).
Don't narrate the obvious.

If you spot a bug or issue outside what was actually asked, flag it clearly
in your reply and move on - don't go fix it without being asked to.

Before you say a task is done, actually verify it - run the tests if there
are any, re-read the diff, or at minimum reason through the logic - never
claim something works without having checked. Once you're done, give a
short, clear summary of what changed, not a full essay.

You also have device-control tools: list_removable_drives (find removable USB
storage - use /cwd to work inside a selected mount), usb_list_directory,
list_android_devices, adb_device_info, adb_list_user_apps,
adb_read_only_check, list_android_apps, pull_from_android (read-only, free),
push_to_android (writes to the phone, confirmed), open_android_app
(confirmed), network_inventory (local interface inventory only),
check_open_ports (local listening ports/services only, no scanning),
scan_local_network (ping-sweeps your own LAN only, confirmed),
list_running_processes (free), open_application (confirmed), and
close_application (confirmed, and refuses critical system processes outright).
ADB discovery and read-only Android tools must be preferred over arbitrary adb
shell commands. Never change network settings, and never scan_local_network
without the user actually asking for a device/network scan - it always needs
their y/n anyway, but don't reach for it speculatively. These tools only work
if the relevant hardware/software is actually connected and available - if a
tool errors out because adb or a device isn't found, say so plainly instead
of pretending it worked.

Use them directly and naturally when a task calls for it - don't ask the
user to paste file contents to you, just read the file yourself. Don't
describe what you're about to do in vague terms; call the tool.

Tools that only read information (read_file, list_dir, search_files,
list_removable_drives, usb_list_directory, list_android_devices,
adb_device_info, adb_list_user_apps, adb_read_only_check, list_android_apps,
pull_from_android, network_inventory, check_open_ports, list_running_processes) run immediately without asking
the user anything. Tools that write, execute, or change something
(write_file, run_shell_command, push_to_android, open_android_app,
open_application, close_application) will always ask the user for a y/n
confirmation before anything happens - that confirmation step is handled
outside of you, so don't add your own "should I proceed?" question on top of
it, just call the tool and let the confirmation prompt do its job.

delegate_task spawns a focused sub-agent to handle one specific, well-scoped
piece of work (like "run the test suite and summarize failures" or "review
this file for bugs") and reports back a summary. Use it to split off
self-contained work, not for the main thread of the task.

Work in small, verifiable steps. After you get a tool result, look at it
before deciding the next action - don't chain many actions based on
assumptions about what a file probably contains.

When you're done with a task, say so plainly and stop - don't keep calling
tools "just to check" once the work is actually finished.

Language: default to clear English. If the user writes in a language that
displays correctly in a plain terminal (English, French, Spanish, German,
and similar Latin-script languages), you may reply in that same language.
Never reply in Arabic or Persian, or any other right-to-left or non-Latin
script, here - the terminal can't render it reliably - even if the user
writes to you in one of those; acknowledge them in English instead. Code
itself stays in English regardless. This restriction is terminal-only.

No emojis.

Never say you are Qwen or mention being made by Alibaba - you are Diana Coding.
"""

CODING_MODEL_DEFAULT = os.environ.get("DIANA_MODEL", "qwen2.5-coder:7b")
# num_ctx was 16384 - on a 6GB card, context is the thing that actually eats
# your VRAM budget (not just the model weights), and 16K risked silent CPU
# offload or an outright OOM on longer sessions. 8192 is the safer ceiling
# for this VRAM tier; raise DIANA_CODING_NUM_CTX if you upgrade the GPU.
CODING_OPTIONS = {
    "temperature": 0.4,
    "repeat_penalty": 1.15,
    "repeat_last_n": 256,
    "top_p": 0.9,
    "num_ctx": int(os.environ.get("DIANA_CODING_NUM_CTX", "8192")),
}
# Ollama auto-picks how many layers go on GPU vs CPU - usually right, but if
# /gpu shows partial CPU offload, you can force a specific layer count here
# once you know your card's real budget (check with `ollama ps` after a
# reply, or just watch /gpu's output over a few messages).
if os.environ.get("DIANA_CODING_NUM_GPU"):
    CODING_OPTIONS["num_gpu"] = int(os.environ["DIANA_CODING_NUM_GPU"])

# ---------- Persona switching ----------
# Diana Coding (agent, tools, project-aware) and Texty (companion, no
# DIANA.md project context) share this same terminal - /texty and /coding
# swap which one you're actually talking to, live, mid-session.
CURRENT_PERSONA = "coding"  # default on startup, unchanged from before

_PERSONA_DOT_COLOR = {"coding": _c(PURPLE_LIGHT), "texty": _c(PURPLE_PALE)}

def input_prompt_label():
    """The colored-dot prompt shown before you type - no 'You->' text,
    just a dot (colored per persona) plus the persona name."""
    dot = _PERSONA_DOT_COLOR.get(CURRENT_PERSONA, _c(PURPLE_LIGHT)) if HAS_COLOR else ""
    return f"{dot}\u25cf{C_RESET} {C_YOU}{persona_label()}{C_RESET} {C_SYSTEM}\u276f{C_RESET} "

def persona_label():
    return "Texty" if CURRENT_PERSONA == "texty" else "Diana Coding"

def build_system_prompt():
    """Coding: base agent prompt plus, if the current directory has a
    DIANA.md file, its contents appended as project context - read fresh
    every time this is called so switching /cwd or editing DIANA.md picks
    up automatically. Also appends Diana's own settings log (from Diana's
    own repo root, not the current project's cwd) so she can answer "what
    have you had customized" accurately in conversation. Texty: her prompt
    as-is, no project context - she's a companion, not a project-aware
    agent."""
    if CURRENT_PERSONA == "texty":
        return SYSTEM_PROMPT_TEXTY_TERMINAL
    prompt = SYSTEM_PROMPT_BASE
    diana_md_path = os.path.join(os.getcwd(), "DIANA.md")
    if os.path.exists(diana_md_path):
        try:
            with open(diana_md_path, "r", encoding="utf-8") as f:
                project_context = f.read().strip()
            if project_context:
                prompt += f"\n\nProject context from DIANA.md:\n{project_context}"
        except Exception:
            pass
    settings_log = read_settings_log()
    if settings_log:
        prompt += f"\n\nYour own applied customizations log (ground truth - quote from this, don't guess):\n{settings_log}"
    return prompt

def read_settings_log():
    """Diana's own settings/customizations log - always from her own repo
    root (PROJECT_DIR), regardless of whatever project /cwd currently points
    at. Returns "" if the file doesn't exist yet."""
    path = os.path.join(PROJECT_DIR, "DIANA_SETTINGS.md")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""

def handle_settings_command():
    log = read_settings_log()
    if not log:
        print(f"{C_SYSTEM}[No settings log found yet at {os.path.join(PROJECT_DIR, 'DIANA_SETTINGS.md')}]{C_RESET}")
        return
    print(f"\n{C_SYSTEM}{log}{C_RESET}\n")

def current_model_name():
    if MODEL_OVERRIDE:
        return MODEL_OVERRIDE
    return TEXTY_MODEL if CURRENT_PERSONA == "texty" else CODING_MODEL_DEFAULT

def current_options():
    return TEXTY_OPTIONS if CURRENT_PERSONA == "texty" else CODING_OPTIONS

# /model temporarily overrides just the model name for the CURRENT persona,
# without touching its prompt, options, or memory file. Reset by /coding,
# /texty, or restarting.
MODEL_OVERRIDE = None

def handle_model_command(arg):
    global MODEL_OVERRIDE
    arg = arg.strip()
    if not arg:
        print(f"{C_SYSTEM}Current model: {current_model_name()}"
              f"{'  (override)' if MODEL_OVERRIDE else ''}. Usage: /model <name> or /model reset{C_RESET}")
        return
    if arg.lower() == "reset":
        MODEL_OVERRIDE = None
        print(f"{C_SYSTEM}[Model override cleared - back to {current_model_name()}]{C_RESET}")
        return
    MODEL_OVERRIDE = arg
    print(f"{C_SYSTEM}[Now using model: {arg} for {persona_label()} - /model reset to undo]{C_RESET}")

# ---------- Rough context-window usage estimate ----------
# Not a real tokenizer count (Ollama doesn't expose one over this API) - a
# conservative ~4 chars/token heuristic, good enough to warn before you
# actually hit num_ctx and start losing early history.
def estimate_tokens(messages):
    total_chars = sum(len(m.get("content") or "") for m in messages)
    return max(1, total_chars // 4)

def context_usage_note(messages):
    used = estimate_tokens(messages)
    limit = current_options().get("num_ctx", 8192)
    pct = min(100, round(100 * used / limit))
    if pct < 60:
        return None  # don't clutter the screen when there's nothing to worry about
    color = _c(Fore.YELLOW) if pct < 85 else _c(Fore.RED + Style.BRIGHT)
    return f"{color}[context: ~{pct}% of {limit} tokens used]{C_RESET}"

# ---------- Tool definitions (Ollama function-calling format) ----------
# ---------- Web research (search + fetch) ----------
WEB_SEARCH_TIMEOUT_SECONDS = 15
WEB_FETCH_TIMEOUT_SECONDS = 15
WEB_FETCH_MAX_CHARS = 8000

def tool_web_search(query, max_results=5):
    if not HAS_WEB_SEARCH:
        return "[ERROR: web search isn't installed - pip install ddgs]"
    query = (query or "").strip()
    if not query:
        return "[ERROR: web_search needs a non-empty query]"
    max_results = max(1, min(int(max_results or 5), 10))
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
    except Exception as e:
        return f"[ERROR: web search failed ({e}) - DuckDuckGo may be rate-limiting or unreachable, try again shortly]"
    if not results:
        return "[No results found]"
    lines = []
    for i, r in enumerate(results, 1):
        title = r.get("title", "(no title)")
        href = r.get("href", "")
        body = (r.get("body") or "").strip()
        lines.append(f"{i}. {title}\n   {href}\n   {body[:250]}")
    log_execution(f"[web_search] {query!r} -> {len(results)} result(s)")
    return "\n\n".join(lines)

def tool_web_fetch(url):
    url = (url or "").strip()
    if not url.startswith(("http://", "https://")):
        return "[ERROR: web_fetch needs a full http(s):// URL]"
    try:
        response = requests.get(
            url, timeout=WEB_FETCH_TIMEOUT_SECONDS,
            headers={"User-Agent": "Mozilla/5.0 (compatible; DianaCoding/1.0)"},
        )
        response.raise_for_status()
    except Exception as e:
        return f"[ERROR fetching {url}: {e}]"

    if HAS_TRAFILATURA:
        extracted = trafilatura.extract(response.text, include_comments=False, include_tables=False)
        text = extracted if extracted else _strip_html_fallback(response.text)
    else:
        text = _strip_html_fallback(response.text)

    text = (text or "").strip()
    if not text:
        return f"[No readable text extracted from {url}]"
    log_execution(f"[web_fetch] {url} -> {len(text)} chars")
    if len(text) > WEB_FETCH_MAX_CHARS:
        return text[:WEB_FETCH_MAX_CHARS] + "\n\n[... truncated, page is longer ...]"
    return text

def _strip_html_fallback(html):
    """Used only when trafilatura isn't installed - a plain regex strip, far
    cruder than trafilatura's actual content extraction (keeps nav/ads/etc
    too), but good enough as a fallback rather than returning nothing."""
    text = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()

# ---------- Task tracking (visible todo list) ----------
# A structured list Diana Coding keeps and shows for any multi-step task -
# research found this single mechanism prevents most "claimed done, wasn't
# really done" failures far better than a prompt instruction alone, because
# the list is externally visible and checkable, not just the model's word.
current_todos = []  # list of {"text": str, "status": "pending"|"in_progress"|"done"}

def tool_update_todos(todos):
    global current_todos
    if not isinstance(todos, list):
        return "[ERROR: todos must be a list of {text, status} items]"
    cleaned = []
    for item in todos:
        if not isinstance(item, dict) or not item.get("text"):
            continue
        status = item.get("status", "pending")
        if status not in ("pending", "in_progress", "done"):
            status = "pending"
        cleaned.append({"text": str(item["text"]), "status": status})
    current_todos = cleaned
    print_todos()
    return f"[Todo list updated - {len(cleaned)} item(s)]"

def print_todos():
    if not current_todos:
        return
    print(f"\n{C_SYSTEM}Task list:{C_RESET}")
    marks = {"pending": "\u2610", "in_progress": "\u25d0", "done": "\u2611"}
    for item in current_todos:
        mark = marks.get(item["status"], "\u2610")
        color = C_SYSTEM if item["status"] != "in_progress" else _c(Fore.YELLOW)
        print(f"{color}  {mark} {item['text']}{C_RESET}")

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the full contents of a file on disk. Runs immediately, no confirmation needed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative or absolute file path to read."}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "List files and folders inside a directory. Runs immediately, no confirmation needed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path to list. Use '.' for the current directory."}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_files",
            "description": "Search for a text string across files in a directory tree. Runs immediately, no confirmation needed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Text to search for."},
                    "path": {"type": "string", "description": "Directory to search under. Defaults to the current directory."}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Replace an exact text block in a file. Always shows a diff and asks for y/n confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to edit."},
                    "old_string": {"type": "string", "description": "Exact existing text to replace."},
                    "new_string": {"type": "string", "description": "Replacement text."},
                    "replace_all": {"type": "boolean", "description": "Replace every occurrence; default is false."}
                },
                "required": ["path", "old_string", "new_string"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create or overwrite a file with new content. Always asks the user for y/n confirmation first.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to write to."},
                    "content": {"type": "string", "description": "Full new content of the file."}
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_shell_command",
            "description": "Run a shell command (PowerShell on Windows) and return its output. Always asks the user for y/n confirmation first.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The shell command to execute."}
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_removable_drives",
            "description": "List removable drive letters (USB sticks, external disks) currently plugged in. Runs immediately, no confirmation needed. Use /cwd to actually work inside one.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "adb_device_info",
            "description": "Read basic information from one authorized Android device. Read-only.",
            "parameters": {
                "type": "object",
                "properties": {"serial": {"type": "string"}},
                "required": ["serial"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "adb_list_user_apps",
            "description": "List third-party packages on one authorized Android device. Read-only.",
            "parameters": {
                "type": "object",
                "properties": {"serial": {"type": "string"}},
                "required": ["serial"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "adb_read_only_check",
            "description": "Read Android state, battery, and /sdcard storage information. Read-only.",
            "parameters": {
                "type": "object",
                "properties": {"serial": {"type": "string"}},
                "required": ["serial"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "network_inventory",
            "description": "Show local network interfaces and addresses only; never scans or changes networks.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_open_ports",
            "description": "List ports this machine itself is listening on, with the owning process and a plain-English service guess (e.g. port 22 -> SSH). Reads the local connection table only - equivalent to running netstat yourself. Never sends a packet to another host and never scans anyone else's device.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "scan_local_network",
            "description": "Ping-sweeps the private LAN subnet(s) this machine is directly connected to, then reads the OS's own ARP table for MAC addresses and tries a reverse-DNS hostname for each device that answers. Restricted to the user's own home/private network - never anything beyond it. Always asks the user for y/n confirmation first, since it actively sends traffic to other devices.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "usb_list_directory",
            "description": "List a directory inside the current selected project/storage root; read-only.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_android_devices",
            "description": "List Android devices currently connected and visible to adb. Runs immediately, no confirmation needed.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_android_apps",
            "description": "List installed app package names on the connected Android device. Runs immediately, no confirmation needed.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "pull_from_android",
            "description": "Copy a file from the connected Android device to the laptop (inside the project folder). Runs immediately, no confirmation needed - it only reads from the device.",
            "parameters": {
                "type": "object",
                "properties": {
                    "remote_path": {"type": "string", "description": "Path on the Android device."},
                    "local_path": {"type": "string", "description": "Destination path on the laptop, inside the project folder."}
                },
                "required": ["remote_path", "local_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "push_to_android",
            "description": "Copy a file from the laptop to the connected Android device. Always asks the user for y/n confirmation first.",
            "parameters": {
                "type": "object",
                "properties": {
                    "local_path": {"type": "string", "description": "Source path on the laptop, inside the project folder."},
                    "remote_path": {"type": "string", "description": "Destination path on the Android device."}
                },
                "required": ["local_path", "remote_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "open_android_app",
            "description": "Launch an app on the connected Android device by its package name. Always asks the user for y/n confirmation first.",
            "parameters": {
                "type": "object",
                "properties": {
                    "package_name": {"type": "string", "description": "Android package name, e.g. 'com.android.settings'."}
                },
                "required": ["package_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_running_processes",
            "description": "List processes currently running on the laptop. Runs immediately, no confirmation needed.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "open_application",
            "description": "Open a program or file on the laptop. Always asks the user for y/n confirmation first.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path_or_name": {"type": "string", "description": "Path to the executable or file to open."}
                },
                "required": ["path_or_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "close_application",
            "description": "Close a running program on the laptop by process name or PID. Always asks the user for y/n confirmation first. Refuses critical system processes outright.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name_or_pid": {"type": "string", "description": "Process name (e.g. 'notepad.exe') or numeric PID."}
                },
                "required": ["name_or_pid"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delegate_task",
            "description": "Spawn a focused sub-agent with a specific role to handle one self-contained piece of work, using the same tools. It reports back a summary when done. Not available to sub-agents themselves, to avoid infinite spawning.",
            "parameters": {
                "type": "object",
                "properties": {
                    "role": {"type": "string", "description": "Short role name, e.g. 'reviewer', 'tester', 'researcher'."},
                    "task": {"type": "string", "description": "The specific, self-contained task to hand off."}
                },
                "required": ["role", "task"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web (DuckDuckGo) for current information, documentation, or anything outside your training data. Returns titles, URLs, and short snippets - use web_fetch on a promising URL to read the full page. Runs immediately, no confirmation needed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query."},
                    "max_results": {"type": "integer", "description": "How many results to return (1-10, default 5)."}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "web_fetch",
            "description": "Fetch a web page by URL and return its readable text content (ads/nav/scripts stripped out). Use after web_search to actually read a page, not just its snippet. Runs immediately, no confirmation needed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The full http(s):// URL to fetch."}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_todos",
            "description": "Create or update your visible task list for the current multi-step piece of work. Call this before starting a nontrivial task to lay out the steps, and update each item's status as you actually complete it. The list is shown to the user, so it must reflect reality - only mark an item 'done' once you've actually verified it, not just attempted it. Runs immediately, no confirmation needed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "todos": {
                        "type": "array",
                        "description": "The full current list, replacing whatever was there before.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "text": {"type": "string"},
                                "status": {"type": "string", "enum": ["pending", "in_progress", "done"]}
                            },
                            "required": ["text", "status"]
                        }
                    }
                },
                "required": ["todos"]
            }
        }
    }
]

# Sub-agents get every tool except delegate_task itself - keeps delegation
# one level deep instead of a sub-agent spawning more sub-agents forever.
SUB_AGENT_TOOLS = [t for t in TOOLS if t["function"]["name"] != "delegate_task"]

# ---------- Safety: allowlist, project-root boundary, and full execution log ----------

# Only commands that START with one of these are allowed to run at all.
# Anything else is rejected before the confirmation prompt even shows up -
# a blacklist can always be phrased around, an allowlist can't.
ALLOWED_COMMAND_PREFIXES = [
    "git", "npm", "npx", "node", "python", "python3", "pip", "pip3", "pytest",
    "dir", "ls", "cat", "type", "echo", "pwd", "mkdir", "cd",
    "ollama", "pyinstaller", "black", "flake8", "ruff", "mypy",
]

# Kept as a second, belt-and-suspenders layer even with the allowlist above -
# catches dangerous flags tacked onto an otherwise-allowed command.
DANGEROUS_PATTERNS = [
    r"(^|[\s;&|])(rm|rmdir|del|format|shutdown|diskpart)([\s;&|]|$)",
    r"(^|[\s;&|])(sudo|su)([\s;&|]|$)",
    r"(^|[\s;&|])(taskkill)([\s;&|]|$)",
    r"(^|[\s;&|])(reg)([\s;&|]|$)",
    r"(^|[\s])(?:python|python3|node)(?:[\s]+(?:-c|-e|--eval|--command))",
    r"(?:\$\(|`)",
    r"(^|[\s])(?:curl|wget)[^\n]*[|]",
]

def split_shell_segments(command):
    """Split shell commands outside quotes for policy checks.

    This is intentionally conservative: it is not a shell interpreter. If the
    command contains unsupported syntax, policy rejects it instead of guessing.
    """
    segments = []
    current = []
    quote = None
    escape = False
    i = 0
    while i < len(command):
        ch = command[i]
        if escape:
            current.append(ch)
            escape = False
            i += 1
            continue
        if ch == "\\" and quote != '"':
            current.append(ch)
            escape = True
            i += 1
            continue
        if ch in ("'", '"'):
            if quote is None:
                quote = ch
            elif quote == ch:
                quote = None
            current.append(ch)
            i += 1
            continue
        if quote is None and command[i:i + 2] in ("&&", "||"):
            if ''.join(current).strip():
                segments.append(''.join(current).strip())
            current = []
            i += 2
            continue
        if quote is None and ch in ';|\n':
            if ''.join(current).strip():
                segments.append(''.join(current).strip())
            current = []
            i += 1
            continue
        current.append(ch)
        i += 1
    if quote is not None:
        raise ValueError("unclosed quote in shell command")
    if ''.join(current).strip():
        segments.append(''.join(current).strip())
    return segments

def _segment_first_word(segment):
    try:
        words = shlex.split(segment, posix=(os.name != "nt"))
    except ValueError as exc:
        raise ValueError(f"invalid shell syntax: {exc}") from exc
    while words and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", words[0]):
        words.pop(0)
    return words[0].lower() if words else ""

def contains_dangerous_command(text):
    lowered = text.lower()
    return any(re.search(pattern, lowered) for pattern in DANGEROUS_PATTERNS)

def _resolve_project_path(path):
    raw = os.path.expanduser(str(path))
    if not os.path.isabs(raw):
        raw = os.path.join(PROJECT_ROOT, raw)
    return os.path.realpath(os.path.abspath(raw))

def _is_path_token(token):
    token = token.strip().strip("'\"")
    if not token or token.startswith("-") or token.startswith(("http://", "https://")):
        return False
    return (token in {".", "..", "~"} or
            token.startswith(("./", "../", ".\\", "..\\", "/", "~\\", "~/")) or
            "/" in token or "\\" in token)

def command_paths_stay_inside_project(command):
    try:
        for segment in split_shell_segments(command):
            words = shlex.split(segment, posix=(os.name != "nt"))
            for token in words[1:]:
                if _is_path_token(token) and not is_inside_project_root(token):
                    return False
    except (ValueError, OSError):
        return False
    return True

def is_allowed_command(command):
    if not command.strip() or len(command) > 4000:
        return False
    # Redirections and command substitution make a text prefix allowlist
    # unsafe; file writes should use write_file/apply_patch instead.
    if re.search(r"(^|[^\\])[<>]", command) or "$(" in command or "`" in command:
        return False
    if not command_paths_stay_inside_project(command):
        return False
    if contains_dangerous_command(command):
        return False
    try:
        segments = split_shell_segments(command)
        words = [_segment_first_word(segment) for segment in segments]
    except ValueError:
        return False
    if not words or any(not word for word in words):
        return False
    return all(
        any(word == prefix or word.startswith(prefix + ".")
            for prefix in ALLOWED_COMMAND_PREFIXES)
        for word in words
    )

# All file/shell tools are only allowed to touch paths inside this root and
# its subfolders - PROJECT_ROOT tracks the current /cwd so it moves with you,
# but nothing can reach outside of wherever you're currently working.
PROJECT_ROOT = os.getcwd()

def is_inside_project_root(path):
    """Resolve symlinks against the current user-selected root.

    /cwd intentionally changes PROJECT_ROOT; this function only protects the
    currently selected root and does not restrict the user to the launch path.
    """
    try:
        root = os.path.realpath(os.path.abspath(PROJECT_ROOT))
        target = _resolve_project_path(path)
        return os.path.commonpath([target, root]) == root
    except (ValueError, OSError):
        return False

def log_execution(entry):
    with open(EXECUTION_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n{entry}\n")

def log_rejected(tool_name, detail):
    with open(EXECUTION_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')} [REJECTED: {tool_name}] ---\n{detail}\n")

# ---------- Tool implementations ----------
def tool_read_file(path):
    if not is_inside_project_root(path):
        log_rejected("read_file", f"path outside project root: {path}")
        return f"[BLOCKED: {path} is outside the current project folder ({PROJECT_ROOT})]"
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        print_file_preview(path, content)
        if len(content) > 20000:
            return content[:20000] + "\n\n[... truncated, file is longer than 20000 characters ...]"
        return content if content else "[file is empty]"
    except Exception as e:
        return f"[ERROR reading file: {e}]"

def tool_list_dir(path):
    if not is_inside_project_root(path):
        log_rejected("list_dir", f"path outside project root: {path}")
        return f"[BLOCKED: {path} is outside the current project folder ({PROJECT_ROOT})]"
    try:
        entries = os.listdir(path)
        return "\n".join(entries) if entries else "[empty directory]"
    except Exception as e:
        return f"[ERROR listing directory: {e}]"

def tool_list_removable_drives():
    """Return mounted storage information without writing or opening files."""
    try:
        return _json_result({"ok": True, "mounts": list_removable_mounts()})
    except Exception as exc:
        return _json_result({"ok": False, "error": str(exc)})

def tool_usb_list_directory(path):
    if not is_inside_project_root(path):
        log_rejected("usb_list_directory", f"path outside project root: {path}")
        return f"[BLOCKED: {path} is outside the current project folder ({PROJECT_ROOT})]"
    try:
        return _json_result(usb_list_directory(_resolve_project_path(path)))
    except Exception as exc:
        return _json_result({"ok": False, "error": str(exc)})

def tool_network_inventory():
    try:
        return _json_result(local_network_inventory())
    except Exception as exc:
        return _json_result({"ok": False, "error": str(exc)})

def tool_check_open_ports():
    try:
        return _json_result(local_open_ports())
    except Exception as exc:
        return _json_result({"ok": False, "error": str(exc)})

def tool_scan_local_network():
    print(f"\n{C_TOOL}[Diana wants to ping-sweep your own LAN to list connected devices]{C_RESET}")
    confirm = input(f"{C_CONFIRM}This sends traffic to every device on your network - only your own private LAN, nothing beyond it. Proceed? (y/n) > {C_RESET}").strip().lower()
    if confirm != "y":
        return _json_result({"ok": False, "error": "User declined the network scan."})
    try:
        return _json_result(local_network_scan())
    except Exception as exc:
        return _json_result({"ok": False, "error": str(exc)})

SEARCH_IGNORE_DIRS = {".git", "node_modules", "__pycache__", ".venv",
                       "venv_fast", "venv_quality", "dist", "build", "project_memories",
                       ".diana_checkpoints"}
SEARCH_MAX_MATCHES = 60

def tool_search_files(query, path="."):
    if not is_inside_project_root(path):
        log_rejected("search_files", f"path outside project root: {path}")
        return f"[BLOCKED: {path} is outside the current project folder ({PROJECT_ROOT})]"
    if not query.strip():
        return "[ERROR: empty search query]"
    matches = []
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in SEARCH_IGNORE_DIRS]
        for fname in files:
            fpath = os.path.join(root, fname)
            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    for lineno, line in enumerate(f, start=1):
                        if query.lower() in line.lower():
                            matches.append(f"{fpath}:{lineno}: {line.strip()}")
                            if len(matches) >= SEARCH_MAX_MATCHES:
                                break
            except Exception:
                continue
            if len(matches) >= SEARCH_MAX_MATCHES:
                break
        if len(matches) >= SEARCH_MAX_MATCHES:
            break
    if not matches:
        return f"[No matches found for '{query}']"
    suffix = "\n...[results truncated at " + str(SEARCH_MAX_MATCHES) + "]" if len(matches) >= SEARCH_MAX_MATCHES else ""
    return "\n".join(matches) + suffix

def tool_edit_file(path, old_string, new_string, replace_all=False):
    if not path or not old_string:
        return "[ERROR: edit_file requires path and non-empty old_string]"
    if not is_inside_project_root(path):
        log_rejected("edit_file", f"path outside project root: {path}")
        return f"[BLOCKED: {path} is outside the current project folder ({PROJECT_ROOT})]"
    target = _resolve_project_path(path)
    try:
        with open(target, "r", encoding="utf-8") as f:
            current = f.read()
    except Exception as e:
        return f"[ERROR reading file for edit: {e}]"
    occurrences = current.count(old_string)
    if occurrences == 0:
        return "[ERROR: old_string was not found; file was not changed]"
    if not replace_all and occurrences != 1:
        return f"[ERROR: old_string occurs {occurrences} times; provide a more specific block or set replace_all=true]"
    new_content = current.replace(old_string, new_string, -1 if replace_all else 1)
    return tool_write_file(target, new_content)

CHECKPOINTS_DIRNAME = ".diana_checkpoints"

def _checkpoints_dir():
    d = os.path.join(PROJECT_ROOT, CHECKPOINTS_DIRNAME)
    os.makedirs(d, exist_ok=True)
    return d

def save_checkpoint(path, old_content):
    """Keep every pre-write version of a file, not just the last one - lets
    /undo step back more than one write, unlike the single rolling .bak."""
    rel = os.path.relpath(os.path.abspath(path), PROJECT_ROOT).replace(os.sep, "__")
    stamp = time.strftime("%Y%m%d_%H%M%S")
    checkpoint_path = os.path.join(_checkpoints_dir(), f"{rel}.{stamp}.bak")
    try:
        with open(checkpoint_path, "w", encoding="utf-8") as f:
            f.write(old_content)
    except Exception:
        return None
    return checkpoint_path

def list_checkpoints(path=None):
    d = _checkpoints_dir()
    entries = sorted(os.listdir(d), reverse=True)
    if path:
        rel_prefix = os.path.relpath(os.path.abspath(path), PROJECT_ROOT).replace(os.sep, "__")
        entries = [e for e in entries if e.startswith(rel_prefix + ".")]
    return [os.path.join(d, e) for e in entries]

def handle_checkpoints(arg):
    entries = list_checkpoints(arg.strip() or None)
    if not entries:
        print(f"{C_SYSTEM}[No checkpoints yet - they're created automatically on every write_file]{C_RESET}")
        return
    print(f"{C_SYSTEM}Checkpoints (newest first):{C_RESET}")
    for i, e in enumerate(entries[:20]):
        print(f"{C_SYSTEM}  [{i}] {os.path.basename(e)}{C_RESET}")

def handle_undo(arg):
    arg = arg.strip()
    if not arg:
        print(f"{C_ERROR}[Usage: /undo <file path> [index]  - index 0 is the most recent checkpoint]{C_RESET}")
        return
    parts = arg.rsplit(" ", 1)
    index = 0
    file_arg = arg
    if len(parts) == 2 and parts[1].isdigit():
        file_arg, index = parts[0], int(parts[1])
    entries = list_checkpoints(file_arg)
    if not entries:
        print(f"{C_ERROR}[No checkpoints found for {file_arg}]{C_RESET}")
        return
    if index >= len(entries):
        print(f"{C_ERROR}[Only {len(entries)} checkpoint(s) exist for this file]{C_RESET}")
        return
    checkpoint_path = entries[index]
    target = _resolve_project_path(file_arg)
    try:
        with open(checkpoint_path, "r", encoding="utf-8") as f:
            restored = f.read()
        with open(target, "w", encoding="utf-8") as f:
            f.write(restored)
        print(f"{C_SYSTEM}[Restored {file_arg} from {os.path.basename(checkpoint_path)}]{C_RESET}")
    except Exception as e:
        print(f"{C_ERROR}[ERROR restoring checkpoint: {e}]{C_RESET}")

def tool_write_file(path, content):
    if not is_inside_project_root(path):
        log_rejected("write_file", f"path outside project root: {path}")
        return f"[BLOCKED: {path} is outside the current project folder ({PROJECT_ROOT})]"

    old_content = None
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                old_content = f.read()
        except Exception:
            old_content = None

    print(f"\n{C_TOOL}[Diana wants to write to: {path}]{C_RESET}")
    print(C_SYSTEM + "-" * 40 + C_RESET)
    if old_content is not None:
        diff_lines = list(difflib.unified_diff(
            old_content.splitlines(keepends=True),
            content.splitlines(keepends=True),
            fromfile=f"{path} (current)",
            tofile=f"{path} (new)"
        ))
        if diff_lines:
            for line in diff_lines[:200]:
                stripped = line.rstrip("\n")
                if line.startswith('+') and not line.startswith('+++'):
                    print(f"{Fore.GREEN if HAS_COLOR else ''}{stripped}{C_RESET}")
                elif line.startswith('-') and not line.startswith('---'):
                    print(f"{C_ERROR}{stripped}{C_RESET}")
                else:
                    print(f"{C_SYSTEM}{stripped}{C_RESET}")
        else:
            print(f"{C_SYSTEM}[no changes - new content is identical to the current file]{C_RESET}")
    else:
        print(f"{C_SYSTEM}[new file]{C_RESET}")
        preview = content if len(content) < 2000 else content[:2000] + "\n...[preview truncated]..."
        print(preview)
    print(C_SYSTEM + "-" * 40 + C_RESET)

    confirm = input(f"{C_CONFIRM}Write this file? (y/n) > {C_RESET}").strip().lower()
    if confirm != "y":
        log_rejected("write_file", f"user declined: {path}")
        return "[SKIPPED: user declined the write]"

    try:
        backup_note = ""
        if old_content is not None:
            backup_path = path + ".bak"
            with open(backup_path, "w", encoding="utf-8") as f:
                f.write(old_content)
            checkpoint_path = save_checkpoint(path, old_content)
            backup_note = f" (previous version backed up to {backup_path}, checkpoint: {os.path.basename(checkpoint_path)})" if checkpoint_path else f" (previous version backed up to {backup_path})"
        target = os.path.realpath(os.path.abspath(os.path.expanduser(path)))
        parent = os.path.dirname(target)
        if parent:
            os.makedirs(parent, exist_ok=True)
        # Atomic replace prevents a crash from leaving a half-written file.
        fd, temp_path = tempfile.mkstemp(prefix=".diana-write-", dir=parent, text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, target)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        log_execution(f"[write_file] {target}\n{content}")
        return f"[OK: wrote {len(content)} characters to {target}{backup_note}]"
    except Exception as e:
        return f"[ERROR writing file: {e}]"

# Patterns that pass the hard allowlist/dangerous-pattern block above but are
# still worth flagging visually before the y/n prompt - things that touch
# git history, uninstall packages, or force-overwrite, without being outright
# blocked like rm/format/sudo are.
SOFT_WARNING_PATTERNS = [
    r"--force\b", r"-f\b(?!ile)", r"\breset\s+--hard\b", r"\bpush\b.*--force",
    r"\buninstall\b", r"\bclean\b.*-[dfx]", r"\bcheckout\b.*--\s*\.",
    r">\s*\S", r"\boverwrite\b",
]

def _shell_command_risk_note(command):
    lowered = command.lower()
    for pattern in SOFT_WARNING_PATTERNS:
        if re.search(pattern, lowered):
            return "this command can overwrite or discard something - double check it"
    return None

# ---------- Trusted commands (skip confirmation for known-safe repeats) ----------
# Per-project allowlist the USER builds explicitly (via the 'a' option below
# or /trust) - separate from and layered on top of the hard allowlist/
# dangerous-pattern checks above, which always apply regardless of trust.
def _trusted_commands_path():
    return os.path.join(PROJECT_ROOT, ".diana_trusted_commands.json")

def load_trusted_commands():
    path = _trusted_commands_path()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError):
            return []
    return []

def save_trusted_commands(commands):
    try:
        with open(_trusted_commands_path(), "w", encoding="utf-8") as f:
            json.dump(commands, f, ensure_ascii=False, indent=2)
    except OSError:
        pass

def is_trusted_command(command):
    command = command.strip()
    for pattern in load_trusted_commands():
        if pattern.endswith("*"):
            if command.startswith(pattern[:-1]):
                return True
        elif command == pattern:
            return True
    return False

def handle_trust(arg):
    arg = arg.strip()
    trusted = load_trusted_commands()
    if not arg:
        if not trusted:
            print(f"{C_SYSTEM}[No trusted commands yet for this project. Usage: /trust <command or prefix*>]{C_RESET}")
        else:
            print(f"{C_SYSTEM}Trusted commands for this project:{C_RESET}")
            for i, c in enumerate(trusted):
                print(f"{C_SYSTEM}  [{i}] {c}{C_RESET}")
        return
    if arg not in trusted:
        trusted.append(arg)
        save_trusted_commands(trusted)
    print(f"{C_SYSTEM}[Trusted: {arg} - runs without asking from now on in this project]{C_RESET}")

def handle_untrust(arg):
    arg = arg.strip()
    trusted = load_trusted_commands()
    removed = None
    if arg.isdigit() and int(arg) < len(trusted):
        removed = trusted.pop(int(arg))
    elif arg in trusted:
        trusted.remove(arg)
        removed = arg
    if removed is None:
        print(f"{C_ERROR}[Not found: {arg!r} - use /trust with no argument to see the list]{C_RESET}")
        return
    save_trusted_commands(trusted)
    print(f"{C_SYSTEM}[Removed from trusted: {removed}]{C_RESET}")

# Read-only commands (or read-only git subcommands) that are safe to
# auto-run without a y/n prompt at all - even on the very first time, before
# the user has ever /trust'ed anything. This is narrower than /trust: it's a
# small fixed list picked because none of them can change project state, and
# it never overrides the allowlist/dangerous-pattern checks that run first.
SAFE_AUTO_COMMANDS = {"ls", "dir", "pwd", "cat", "type"}
SAFE_AUTO_GIT_SUBCOMMANDS = {"status", "log", "diff", "branch", "show", "remote"}

def is_safe_auto_command(command):
    try:
        segments = split_shell_segments(command)
    except ValueError:
        return False
    if not segments:
        return False
    for segment in segments:
        try:
            words = shlex.split(segment, posix=(os.name != "nt"))
        except ValueError:
            return False
        if not words:
            return False
        first = words[0].lower()
        if first in SAFE_AUTO_COMMANDS:
            continue
        if first == "git" and len(words) > 1 and words[1].lower() in SAFE_AUTO_GIT_SUBCOMMANDS:
            continue
        return False
    return True

def tool_run_shell_command(command):
    if not is_allowed_command(command):
        log_rejected("run_shell_command", f"not on allowlist: {command}")
        return (f"[BLOCKED: '{command.split()[0] if command.strip() else command}' is not on the "
                f"allowed command list. Allowed: {', '.join(ALLOWED_COMMAND_PREFIXES)}]")
    if contains_dangerous_command(command):
        log_rejected("run_shell_command", f"dangerous pattern: {command}")
        return "[BLOCKED: command contains a pattern that looks destructive, not executed]"

    risk_note = _shell_command_risk_note(command)
    if is_trusted_command(command):
        print(f"\n{C_TOOL}[Diana is running a trusted command:]{C_RESET}")
        print(C_SYSTEM + command + C_RESET)
    elif not risk_note and is_safe_auto_command(command):
        print(f"\n{C_TOOL}[Diana is running a read-only command:]{C_RESET}")
        print(C_SYSTEM + command + C_RESET)
    else:
        print(f"\n{C_TOOL}[Diana wants to run this shell command:]{C_RESET}")
        print(C_SYSTEM + "-" * 40 + C_RESET)
        if risk_note and HAS_COLOR:
            print(f"{_c(Fore.YELLOW + Style.BRIGHT)}{command}{C_RESET}")
            print(f"{_c(Fore.YELLOW)}\u26a0 {risk_note}{C_RESET}")
        else:
            print(command)
            if risk_note:
                print(f"[!] {risk_note}")
        print(C_SYSTEM + "-" * 40 + C_RESET)
        confirm = input(f"{C_CONFIRM}Run it? (y=once, a=always trust this exact command, n=no) > {C_RESET}").strip().lower()
        if confirm == "a":
            trusted = load_trusted_commands()
            trusted.append(command)
            save_trusted_commands(trusted)
            print(f"{C_SYSTEM}[Trusted - won't ask for this exact command again in this project]{C_RESET}")
        elif confirm != "y":
            log_rejected("run_shell_command", f"user declined: {command}")
            return "[SKIPPED: user declined the command]"

    try:
        has_shell_operators = bool(re.search(r"&&|\|\||[;|\n]", command))
        run_command = command if has_shell_operators else shlex.split(command, posix=(os.name != "nt"))
        result = subprocess.run(
            run_command,
            shell=has_shell_operators,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=SHELL_TIMEOUT_SECONDS,
            errors="replace",
        )
        log_execution(f"[run_shell_command] {command} (cwd={PROJECT_ROOT})")
        global SESSION_SHELL_COMMANDS
        SESSION_SHELL_COMMANDS += 1
        output = (result.stdout or "").strip()
        error = (result.stderr or "").strip()
        parts = []
        if output:
            parts.append(f"OUTPUT:\n{output[:MAX_COMMAND_OUTPUT_CHARS]}")
            if len(output) > MAX_COMMAND_OUTPUT_CHARS:
                parts.append("[stdout truncated; full output was not sent to the model]")
        if error:
            parts.append(f"STDERR:\n{error[:MAX_COMMAND_OUTPUT_CHARS]}")
            if len(error) > MAX_COMMAND_OUTPUT_CHARS:
                parts.append("[stderr truncated; full output was not sent to the model]")
        if result.returncode != 0:
            parts.append(f"EXIT_CODE: {result.returncode}")
        return "\n\n".join(parts) if parts else "[no output]"
    except subprocess.TimeoutExpired:
        return f"[Execution stopped: exceeded {SHELL_TIMEOUT_SECONDS} second time limit]"
    except Exception as e:
        return f"[ERROR running command: {e}]"

# ---------- Android device control (via ADB - reads free, writes confirm) ----------
ADB_MISSING_MSG = "[ERROR: adb not found. Install Android SDK Platform-Tools and set DIANA_ADB_PATH or PATH]"

def _adb_available():
    return find_adb() is not None

def _json_result(value):
    return json.dumps(value, ensure_ascii=False, indent=2)

def _one_authorized_serial():
    result = list_devices()
    if not result.get("ok"):
        return None, result
    authorized = [item["serial"] for item in result.get("devices", []) if item.get("state") == "device"]
    if len(authorized) != 1:
        return None, {
            "ok": False,
            "error": "select exactly one authorized Android device",
            "devices": result.get("devices", []),
        }
    return authorized[0], result

def tool_list_android_devices():
    return _json_result(list_devices()) if _adb_available() else ADB_MISSING_MSG

def tool_list_android_apps():
    if not _adb_available():
        return ADB_MISSING_MSG
    serial, result = _one_authorized_serial()
    return _json_result(list_user_apps(serial)) if serial else _json_result(result)

def tool_adb_device_info(serial):
    if not _adb_available():
        return ADB_MISSING_MSG
    return _json_result(get_device_info(serial))

def tool_adb_list_user_apps(serial):
    if not _adb_available():
        return ADB_MISSING_MSG
    return _json_result(list_user_apps(serial))

def tool_adb_read_only_check(serial):
    if not _adb_available():
        return ADB_MISSING_MSG
    return _json_result(read_only_device_check(serial))

def tool_pull_from_android(remote_path, local_path):
    """Copies FROM the phone TO the laptop; only the local path is writable."""
    if not _adb_available():
        return ADB_MISSING_MSG
    if not remote_path.strip() or "\x00" in remote_path:
        return "[ERROR: remote_path is required]"
    if not is_inside_project_root(local_path):
        log_rejected("pull_from_android", f"local path outside project root: {local_path}")
        return f"[BLOCKED: {local_path} is outside the current project folder ({PROJECT_ROOT})]"
    serial, result = _one_authorized_serial()
    if not serial:
        return _json_result(result)
    adb_result = run_adb(["pull", remote_path, _resolve_project_path(local_path)], serial=serial, timeout=60)
    log_execution(f"[pull_from_android] serial={serial} {remote_path} -> {local_path}")
    return _json_result(adb_result)

def tool_push_to_android(local_path, remote_path):
    """Writes TO the phone - always confirmed, same as write_file."""
    if not _adb_available():
        return ADB_MISSING_MSG
    if not remote_path.strip() or "\x00" in remote_path:
        return "[ERROR: remote_path is required]"
    if not is_inside_project_root(local_path):
        log_rejected("push_to_android", f"local path outside project root: {local_path}")
        return f"[BLOCKED: {local_path} is outside the current project folder ({PROJECT_ROOT})]"
    serial, result = _one_authorized_serial()
    if not serial:
        return _json_result(result)
    print(f"\n{C_TOOL}[Diana wants to push to Android {serial}: {local_path} -> {remote_path}]{C_RESET}")
    confirm = input(f"{C_CONFIRM}Push this file to the device? (y/n) > {C_RESET}").strip().lower()
    if confirm != "y":
        log_rejected("push_to_android", f"user declined: {local_path} -> {remote_path}")
        return "[SKIPPED: user declined the push]"
    adb_result = run_adb(["push", _resolve_project_path(local_path), remote_path], serial=serial, timeout=60)
    log_execution(f"[push_to_android] serial={serial} {local_path} -> {remote_path}")
    return _json_result(adb_result)

def tool_open_android_app(package_name):
    if not _adb_available():
        return ADB_MISSING_MSG
    if not validate_package_name(package_name):
        return "[ERROR: invalid Android package name]"
    serial, result = _one_authorized_serial()
    if not serial:
        return _json_result(result)
    print(f"\n{C_TOOL}[Diana wants to open this app on Android {serial}: {package_name}]{C_RESET}")
    confirm = input(f"{C_CONFIRM}Open this app on the device? (y/n) > {C_RESET}").strip().lower()
    if confirm != "y":
        log_rejected("open_android_app", f"user declined: {package_name}")
        return "[SKIPPED: user declined opening the app]"
    adb_result = run_adb(
        ["shell", "monkey", "-p", package_name, "-c", "android.intent.category.LAUNCHER", "1"],
        serial=serial,
        timeout=15,
    )
    log_execution(f"[open_android_app] serial={serial} {package_name}")
    return _json_result(adb_result)

# ---------- Laptop process control (opening/closing local applications) ----------
CRITICAL_PROCESS_NAMES = {
    "system", "csrss.exe", "winlogon.exe", "services.exe", "lsass.exe",
    "smss.exe", "wininit.exe", "explorer.exe", "svchost.exe", "registry",
    "system idle process",
}

def tool_list_running_processes():
    try:
        if os.name == "nt":
            command = ["tasklist"]
        else:
            command = ["ps", "-eo", "pid,comm,args"]
        result = subprocess.run(command, capture_output=True, text=True, timeout=10)
        return (result.stdout or result.stderr).strip() or "[no output]"
    except Exception as e:
        return f"[ERROR: {e}]"

def tool_open_application(path_or_name):
    print(f"\n{C_TOOL}[Diana wants to open: {path_or_name}]{C_RESET}")
    confirm = input(f"{C_CONFIRM}Open this application? (y/n) > {C_RESET}").strip().lower()
    if confirm != "y":
        log_rejected("open_application", f"user declined: {path_or_name}")
        return "[SKIPPED: user declined opening the application]"
    try:
        if os.name == "nt":
            os.startfile(path_or_name)
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", path_or_name])
        else:
            subprocess.Popen(["xdg-open", path_or_name])
        log_execution(f"[open_application] {path_or_name}")
        return f"[OK: launched {path_or_name}]"
    except Exception as e:
        return f"[ERROR opening application: {e}]"

def tool_close_application(name_or_pid):
    target = name_or_pid.strip().lower()
    if target in CRITICAL_PROCESS_NAMES:
        log_rejected("close_application", f"blocked critical process: {name_or_pid}")
        return f"[BLOCKED: '{name_or_pid}' is a critical system process and can't be closed through this tool]"

    print(f"\n{C_TOOL}[Diana wants to close: {name_or_pid}]{C_RESET}")
    confirm = input(f"{C_CONFIRM}Close this application? (y/n) > {C_RESET}").strip().lower()
    if confirm != "y":
        log_rejected("close_application", f"user declined: {name_or_pid}")
        return "[SKIPPED: user declined closing the application]"
    try:
        if os.name == "nt":
            flag = "/PID" if name_or_pid.strip().isdigit() else "/IM"
            command = ["taskkill", flag, name_or_pid.strip(), "/F"]
        else:
            command = ["kill", "-TERM", name_or_pid.strip()] if name_or_pid.strip().isdigit() else ["pkill", "-TERM", "-f", name_or_pid.strip()]
        result = subprocess.run(command, capture_output=True, text=True, timeout=10)
        log_execution(f"[close_application] {name_or_pid}")
        return (result.stdout + result.stderr).strip()
    except Exception as e:
        return f"[ERROR closing application: {e}]"

def run_sub_agent(role, task):
    """A bounded, isolated tool-calling loop for one delegated task. Uses the
    same confirmation prompts as the main agent for write_file/run_shell_command
    - nothing runs without the user seeing it, sub-agent or not."""
    label = f"sub-agent '{role}'"
    print(f"\n{Fore.MAGENTA + Style.BRIGHT if HAS_COLOR else ''}[Spawning {label} - task: {task}]{C_RESET}")

    sub_system = (
        f"You are a focused sub-agent with the role '{role}', spawned to complete "
        f"one specific task, then report back. Task: {task}\n\n"
        "Use your tools directly. read_file/list_dir/search_files run freely; "
        "write_file/run_shell_command ask the user to confirm. When the task is "
        "done, give a short, concrete final report - no filler, no re-explaining "
        "the task back."
    )
    sub_history = [{"role": "system", "content": sub_system}]

    for _ in range(SUB_AGENT_MAX_STEPS):
        try:
            payload = {
                "model": CODING_MODEL_DEFAULT,
                "messages": sub_history,
                "stream": False,
                "keep_alive": KEEP_ALIVE,
                "tools": SUB_AGENT_TOOLS
            }
            message = run_with_thinking_rain(ollama_chat, payload)
        except Exception as e:
            return f"[{label} error: {e}]"

        tool_calls = message.get("tool_calls")
        if not tool_calls:
            reply_text = (message.get("content") or "").strip()
            print(f"{Fore.MAGENTA if HAS_COLOR else ''}[{label} finished]{C_RESET}")
            return reply_text

        sub_history.append(message)
        for call in tool_calls:
            fn = call.get("function", {})
            fn_name = fn.get("name")
            fn_args = fn.get("arguments", {})
            if isinstance(fn_args, str):
                try:
                    fn_args = json.loads(fn_args)
                except json.JSONDecodeError:
                    fn_args = {}
            print(f"{C_TOOL}  [{label} using tool: {fn_name}]{C_RESET}")
            handler = TOOL_DISPATCH.get(fn_name)
            result = handler(fn_args) if handler else f"[ERROR: unknown tool '{fn_name}']"
            sub_history.append({"role": "tool", "content": result})

    return f"[{label} stopped after {SUB_AGENT_MAX_STEPS} steps without a final answer]"

# ---------- Plan Mode ----------
# Explores the project read-only and produces a written plan without
# touching anything - Claude Code's "Plan Mode" pattern: review the plan,
# adjust if needed, THEN implement, instead of hoping a big task goes right
# on the first attempt with no checkpoint to review against.
PLANS_DIRNAME = "plans"
READ_ONLY_TOOL_NAMES = {
    "read_file", "list_dir", "search_files", "web_search", "web_fetch",
    "list_removable_drives", "adb_device_info", "adb_list_user_apps",
    "adb_read_only_check", "network_inventory", "check_open_ports", "usb_list_directory",
    "list_android_devices", "list_android_apps", "pull_from_android",
    "list_running_processes",
}
PLAN_MODE_TOOLS = [t for t in TOOLS if t["function"]["name"] in READ_ONLY_TOOL_NAMES]
PLAN_MODE_MAX_STEPS = 10
last_plan = {"text": None, "path": None}

def _plans_dir():
    d = os.path.join(PROJECT_ROOT, PLANS_DIRNAME)
    os.makedirs(d, exist_ok=True)
    return d

def _slugify(text, max_len=40):
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return (slug[:max_len] or "plan")

def save_plan_to_disk(task, plan_text):
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = os.path.join(_plans_dir(), f"{stamp}-{_slugify(task)}.md")
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"# Plan: {task}\n\n{plan_text}\n")
        return path
    except OSError:
        return None

def run_plan_mode(task):
    global last_plan
    print(f"\n{_c(Fore.CYAN + Style.BRIGHT)}[Plan mode - exploring read-only, nothing will be written or run]{C_RESET}")
    plan_system = (
        "You are Diana Coding in PLAN MODE. You have read-only tools only - "
        "no write_file, edit_file, or run_shell_command are available, so "
        "nothing you do can change anything. Explore the project as much as "
        f"you need to understand it, then write a clear, numbered, "
        f"step-by-step implementation plan for this task: {task}\n\n"
        "End your reply with the plan itself - concrete steps, files to "
        "touch, and why - not a summary of what you're about to do."
    )
    plan_history = [{"role": "system", "content": plan_system}]

    for _ in range(PLAN_MODE_MAX_STEPS):
        try:
            payload = {
                "model": CODING_MODEL_DEFAULT,
                "messages": plan_history,
                "stream": False,
                "keep_alive": KEEP_ALIVE,
                "options": CODING_OPTIONS,
                "tools": PLAN_MODE_TOOLS,
            }
            message = run_with_thinking_rain(ollama_chat, payload)
        except Exception as e:
            print(f"{C_ERROR}[Plan mode error: {e}]{C_RESET}")
            return

        tool_calls = message.get("tool_calls")
        if not tool_calls:
            plan_text = (message.get("content") or "").strip()
            path = save_plan_to_disk(task, plan_text)
            last_plan = {"text": plan_text, "path": path}
            print_diana_reply(plan_text)
            if path:
                print(f"\n{C_SYSTEM}[Plan saved to {path}. Type /implement to execute it as-is, "
                      f"or just describe changes to revise it.]{C_RESET}")
            return

        plan_history.append(message)
        for call in tool_calls:
            fn = call.get("function", {})
            fn_name = fn.get("name")
            fn_args = fn.get("arguments", {})
            if isinstance(fn_args, str):
                try:
                    fn_args = json.loads(fn_args)
                except json.JSONDecodeError:
                    fn_args = {}
            print(f"{C_TOOL}  [plan mode using tool: {fn_name}]{C_RESET}")
            handler = TOOL_DISPATCH.get(fn_name)
            result = handler(fn_args) if handler else f"[ERROR: unknown tool '{fn_name}']"
            plan_history.append({"role": "tool", "content": result})

    print(f"{C_ERROR}[Plan mode stopped after {PLAN_MODE_MAX_STEPS} steps without a finished plan]{C_RESET}")

def handle_implement():
    if not last_plan["text"]:
        print(f"{C_ERROR}[No plan yet - use /plan <task> first]{C_RESET}")
        return
    print(f"{C_SYSTEM}[Implementing the last plan{' (' + last_plan['path'] + ')' if last_plan['path'] else ''}]{C_RESET}")
    agent_chat(f"Implement this plan exactly, step by step:\n\n{last_plan['text']}")

def tool_delegate_task(role, task):
    if not role.strip() or not task.strip():
        return "[ERROR: delegate_task needs both a role and a task]"
    return run_sub_agent(role.strip(), task.strip())

TOOL_DISPATCH = {
    "read_file": lambda args: tool_read_file(args.get("path", "")),
    "list_dir": lambda args: tool_list_dir(args.get("path", ".")),
    "search_files": lambda args: tool_search_files(args.get("query", ""), args.get("path", ".")),
    "edit_file": lambda args: tool_edit_file(
        args.get("path", ""), args.get("old_string", ""),
        args.get("new_string", ""), args.get("replace_all", False)
    ),
    "write_file": lambda args: tool_write_file(args.get("path", ""), args.get("content", "")),
    "run_shell_command": lambda args: tool_run_shell_command(args.get("command", "")),
    "list_removable_drives": lambda args: tool_list_removable_drives(),
    "adb_device_info": lambda args: tool_adb_device_info(args.get("serial", "")),
    "adb_list_user_apps": lambda args: tool_adb_list_user_apps(args.get("serial", "")),
    "adb_read_only_check": lambda args: tool_adb_read_only_check(args.get("serial", "")),
    "network_inventory": lambda args: tool_network_inventory(),
    "check_open_ports": lambda args: tool_check_open_ports(),
    "scan_local_network": lambda args: tool_scan_local_network(),
    "usb_list_directory": lambda args: tool_usb_list_directory(args.get("path", ".")),
    "list_android_devices": lambda args: tool_list_android_devices(),
    "list_android_apps": lambda args: tool_list_android_apps(),
    "pull_from_android": lambda args: tool_pull_from_android(args.get("remote_path", ""), args.get("local_path", "")),
    "push_to_android": lambda args: tool_push_to_android(args.get("local_path", ""), args.get("remote_path", "")),
    "open_android_app": lambda args: tool_open_android_app(args.get("package_name", "")),
    "list_running_processes": lambda args: tool_list_running_processes(),
    "open_application": lambda args: tool_open_application(args.get("path_or_name", "")),
    "close_application": lambda args: tool_close_application(args.get("name_or_pid", "")),
    "delegate_task": lambda args: tool_delegate_task(args.get("role", ""), args.get("task", "")),
    "web_search": lambda args: tool_web_search(args.get("query", ""), args.get("max_results", 5)),
    "web_fetch": lambda args: tool_web_fetch(args.get("url", "")),
    "update_todos": lambda args: tool_update_todos(args.get("todos", [])),
}

# ---------- Memory (persists across sessions, one file per project/folder,
# and now also one file per persona - Diana Coding and Texty never mix
# memories, even inside the exact same project folder) ----------
def memory_path_for_cwd():
    safe_name = re.sub(r'[^A-Za-z0-9]+', '_', os.path.abspath(os.getcwd())).strip('_')
    suffix = "texty" if CURRENT_PERSONA == "texty" else "coding"
    return os.path.join(MEMORY_DIR, f"{safe_name}__{suffix}.json")

def load_memory_for_cwd():
    path = memory_path_for_cwd()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                history = json.load(f)
            if not isinstance(history, list) or not history:
                raise ValueError("memory must be a non-empty list")
            if history[0].get("role") == "system":
                history[0]["content"] = build_system_prompt()  # pick up DIANA.md changes
            else:
                history.insert(0, {"role": "system", "content": build_system_prompt()})
            return history
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError, OSError):
            print(f"{C_ERROR}[Warning: memory file was corrupted, starting fresh]{C_RESET}")
    return [{"role": "system", "content": build_system_prompt()}]

def save_memory(history):
    path = memory_path_for_cwd()
    parent = os.path.dirname(path)
    os.makedirs(parent, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=".diana-memory-", dir=parent, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

def build_outgoing_messages(history):
    """Trims what actually gets sent to the model to the last
    MAX_EXCHANGES_SENT user-anchored exchanges (keeping any tool-call/tool
    pairs inside an exchange intact) - the full history on disk is untouched.
    Turns that fall out of this window aren't just dropped: they're rolled
    into a running summary (summarize_turns_with_model), which rides along
    as a system message so older context isn't fully lost, just compressed.

    The summarization call itself never blocks this reply - it used to run
    right here, synchronously, before the actual reply even started, which
    is exactly the silent multi-second freeze that showed up once a
    conversation passed MAX_EXCHANGES_SENT turns: no spinner, no visible
    reason, just a dead pause. Now the existing (slightly stale) summary is
    used immediately and a background thread quietly refreshes it for next
    turn - the reply this turn is never held up waiting on it."""
    system_msg = history[0]
    rest = history[1:]
    user_indices = [i for i, m in enumerate(rest) if m.get("role") == "user"]
    if len(user_indices) <= MAX_EXCHANGES_SENT:
        return [system_msg] + rest

    start = user_indices[-MAX_EXCHANGES_SENT]
    kept = rest[start:]
    dropped_user_count = len(user_indices) - MAX_EXCHANGES_SENT

    summary, summarized_through = load_rolling_summary()
    if dropped_user_count > summarized_through:
        delta_start = user_indices[summarized_through] if summarized_through < len(user_indices) else 0
        delta = rest[delta_start:start]
        if delta:
            _kick_off_background_summary(delta, summary, dropped_user_count)

    messages = [system_msg]
    if summary:
        messages.append({
            "role": "system",
            "content": f"Summary of earlier conversation, for context only - don't repeat it verbatim: {summary}",
        })
    return messages + kept

# ---------- Rolling summary of trimmed-out history ----------
_summary_lock = threading.Lock()
_summary_in_progress = False

def _kick_off_background_summary(delta, previous_summary, dropped_user_count):
    """Fire-and-forget: runs summarize_turns_with_model on a background
    thread so build_outgoing_messages never has to wait on it. If one is
    already running, skip - the next turn will just catch up further in
    one go once it finishes, nothing is lost."""
    global _summary_in_progress
    with _summary_lock:
        if _summary_in_progress:
            return
        _summary_in_progress = True

    def _worker():
        global _summary_in_progress
        try:
            summary = summarize_turns_with_model(delta, previous_summary=previous_summary)
            save_rolling_summary(summary, dropped_user_count)
        finally:
            with _summary_lock:
                _summary_in_progress = False

    threading.Thread(target=_worker, daemon=True).start()

def summary_path_for_cwd():
    return memory_path_for_cwd() + ".summary.json"

def load_rolling_summary():
    path = summary_path_for_cwd()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("summary", ""), data.get("summarized_through", 0)
        except (json.JSONDecodeError, OSError):
            pass
    return "", 0

def save_rolling_summary(summary, summarized_through):
    # Now written from a background thread (see _kick_off_background_summary)
    # while the main thread may read it for the next turn - atomic
    # write-then-rename avoids any chance of reading a half-written file.
    path = summary_path_for_cwd()
    parent = os.path.dirname(path) or "."
    try:
        fd, temp_path = tempfile.mkstemp(prefix=".diana-summary-", dir=parent, text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump({"summary": summary, "summarized_through": summarized_through}, f, ensure_ascii=False, indent=2)
            os.replace(temp_path, path)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
    except OSError:
        pass  # best-effort - a failed summary write just means the next call retries

def summarize_turns_with_model(turns, previous_summary=""):
    """Ask the model itself for a short factual summary of the turns that
    just fell out of the sent window, folded into whatever was already
    summarized before. Best-effort: on any failure, the previous summary is
    returned unchanged so a flaky call never breaks the conversation."""
    transcript = "\n".join(
        f"{'User' if t.get('role') == 'user' else 'Diana'}: {t.get('content', '')}"
        for t in turns if t.get("content")
    )
    if not transcript.strip():
        return previous_summary
    prompt = (
        (f"Existing summary of earlier conversation:\n{previous_summary}\n\n" if previous_summary else "")
        + f"New excerpt to fold in:\n{transcript}\n\n"
        + "Write one updated short factual summary (5-8 sentences max) covering names, "
          "decisions, ongoing tasks, and preferences mentioned so far. Plain text, no "
          "markdown, no preamble, just the summary itself."
    )
    try:
        payload = {
            "model": current_model_name(),
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "keep_alive": KEEP_ALIVE,
            # This runs in the background now (see _kick_off_background_summary),
            # but it still shares the same GPU as whatever's generating the
            # visible reply, so keeping it lean matters: a short factual
            # summary of a bounded excerpt never needs the full 8192-token
            # context, and num_predict caps worst-case generation length so
            # a rambly output can't drag this out longer than it needs to.
            "options": {"temperature": 0.2, "num_ctx": 4096, "num_predict": 300},
        }
        message = ollama_chat(payload)
        return (message.get("content") or previous_summary).strip()
    except Exception:
        return previous_summary

# ---------- Semantic memory search (/recall) ----------
# Uses Ollama's embeddings endpoint with nomic-embed-text - the model
# recommended for this VRAM tier's RAG use case. Everything here degrades
# gracefully if that model isn't pulled: /recall just falls back to the
# plain-text /search instead of failing.
EMBEDDING_MODEL = os.environ.get("DIANA_EMBEDDING_MODEL", "nomic-embed-text")

def embed_text(text):
    try:
        base = OLLAMA_URL.rsplit("/api/", 1)[0]
        response = requests.post(
            f"{base}/api/embeddings",
            json={"model": EMBEDDING_MODEL, "prompt": text},
            timeout=10,
        )
        response.raise_for_status()
        vec = response.json().get("embedding")
        return vec if isinstance(vec, list) and vec else None
    except Exception:
        return None

def _cosine_similarity(a, b):
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)

def memory_index_path():
    return memory_path_for_cwd() + ".embeddings.jsonl"

def append_to_memory_index(role, content, turn_index):
    """Best-effort: embeds one turn and appends it to this project+persona's
    index. Silently does nothing if the embedding model isn't available -
    never blocks or breaks the conversation over this."""
    if not content or not content.strip():
        return
    vec = embed_text(content)
    if vec is None:
        return
    try:
        with open(memory_index_path(), "a", encoding="utf-8") as f:
            f.write(json.dumps({"turn_index": turn_index, "role": role, "content": content, "embedding": vec},
                                ensure_ascii=False) + "\n")
    except OSError:
        pass

def semantic_search(query, top_k=5):
    """Returns None if embeddings are unavailable (caller should fall back
    to /search), [] if available but nothing is indexed yet, or a list of
    (score, entry) tuples sorted by relevance otherwise."""
    query_vec = embed_text(query)
    if query_vec is None:
        return None
    path = memory_index_path()
    if not os.path.exists(path):
        return []
    scored = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    scored.append((_cosine_similarity(query_vec, entry["embedding"]), entry))
                except (json.JSONDecodeError, KeyError):
                    continue
    except OSError:
        return []
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return scored[:top_k]

conversation_history = load_memory_for_cwd()

# ---------- Voice mode toggle ----------
voice_enabled = False  # starts OFF - text-first, voice on demand

# ---------- Instant mute / kill-switch ----------
mute_event = threading.Event()
_mute_listener_should_run = threading.Event()
_mute_listener_should_run.set()
_pending_queue = queue.Queue()

def mute_key_listener():
    if not HAS_MSVCRT:
        return
    while _mute_listener_should_run.is_set():
        if msvcrt.kbhit():
            key = msvcrt.getch()
            if key in (b'm', b'M'):
                mute_event.set()
                sd.stop()
                print("\n[MUTED - press 'm' again to resume speaking]\n")
                while not _pending_queue.empty():
                    try:
                        _pending_queue.get_nowait()
                    except queue.Empty:
                        break
        time.sleep(0.05)

if HAS_MSVCRT:
    threading.Thread(target=mute_key_listener, daemon=True).start()
else:
    print("[Note: instant mute hotkey needs Windows (msvcrt) - not available on this OS]")

# ---------- Helper functions ----------
def remove_emojis(text):
    return text.encode('ascii', 'ignore').decode('ascii')

def get_tts_model():
    global tts_model
    if tts_model is not None:
        return tts_model
    if not HAS_TTS:
        raise RuntimeError("optional TTS dependencies are not installed")
    if TTS_DEVICE == "cuda":
        try:
            import torch
            if not torch.cuda.is_available():
                raise RuntimeError("CUDA is not available; set DIANA_TTS_DEVICE=cpu or install CUDA")
        except ImportError as exc:
            raise RuntimeError("PyTorch is not installed for TTS") from exc
    print(f"Loading Diana voice model on {TTS_DEVICE}...")
    tts_model = ChatterboxTurboTTS.from_pretrained(device=TTS_DEVICE)
    return tts_model

def speak(text, filename):
    model = get_tts_model()
    wav = model.generate(
        text,
        audio_prompt_path=REFERENCE_VOICE_PATH,
        cfg_weight=0.3,
        exaggeration=0.7
    )
    ta.save(filename, wav, model.sr)

# ---------- Speaking waveform indicator ----------
def _voice_waveform(stop_event):
    bars = "\u2581\u2582\u2583\u2584\u2585\u2586\u2587"
    while not stop_event.is_set():
        line = "".join(random.choice(bars) for _ in range(20))
        print(f"\r\033[2K{C_BANNER}[speaking] {line}{C_RESET}", end="", flush=True)
        time.sleep(0.08)
    print("\r\033[2K", end="", flush=True)

def speak_final_reply(text):
    """Speaks only the final plain-text reply once the agent loop is done -
    intermediate tool-call steps are never spoken, only the conclusion."""
    if not voice_enabled or not text.strip():
        return
    clean = remove_emojis(text).strip()
    if not clean:
        return
    filename = f"reply_{int(time.time()*1000)}.wav"
    try:
        speak(clean, filename)
        if mute_event.is_set():
            return
        if not HAS_TTS or sd is None or sf is None:
            return
        data, samplerate = sf.read(filename)
        sd.play(data, samplerate)
        stop_wave = threading.Event()
        wave_thread = threading.Thread(target=_voice_waveform, args=(stop_wave,), daemon=True)
        wave_thread.start()
        try:
            sd.wait()
        finally:
            stop_wave.set()
            wave_thread.join()
    except Exception as e:
        print(f"\n[Skipped speaking the reply due to a TTS/playback error: {e}]")
    finally:
        try:
            os.remove(filename)
        except (PermissionError, FileNotFoundError):
            pass

# ---------- Copy-to-clipboard for code Diana writes ----------
# Best-effort: whichever OS clipboard tool is available. If none is found
# (e.g. a headless Linux box with neither xclip nor wl-copy installed), the
# code gets saved to a file instead so there's always some easy way to grab
# it - never just silently give up.
LAST_CODE_BLOCKS = []
_CODE_BLOCK_PATTERN = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)

def extract_code_blocks(text):
    return [block.rstrip("\n") for block in _CODE_BLOCK_PATTERN.findall(text or "")]

def copy_to_clipboard(text):
    try:
        if os.name == "nt":
            subprocess.run(["clip"], input=text, text=True, check=True, timeout=5)
            return True
        if platform.system() == "Darwin":
            subprocess.run(["pbcopy"], input=text, text=True, check=True, timeout=5)
            return True
        for cmd in (["xclip", "-selection", "clipboard"], ["wl-copy"]):
            try:
                subprocess.run(cmd, input=text, text=True, check=True, timeout=5)
                return True
            except FileNotFoundError:
                continue
        return False
    except Exception:
        return False

def _save_code_fallback(text):
    path = os.path.join(PROJECT_ROOT, ".diana_last_code.txt")
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    except OSError:
        return None
    return path

def offer_code_copy(reply_text):
    """Call once per finished assistant reply. If it contained any fenced
    code blocks, copies them (joined together) to the clipboard, or saves
    them to a file if no clipboard tool is available on this machine."""
    global LAST_CODE_BLOCKS
    blocks = extract_code_blocks(reply_text)
    if not blocks:
        return
    LAST_CODE_BLOCKS = blocks
    combined = "\n\n".join(blocks)
    if copy_to_clipboard(combined):
        print(f"{C_SYSTEM}[Code copied to clipboard - just paste it. /copy to copy it again]{C_RESET}")
    else:
        path = _save_code_fallback(combined)
        if path:
            print(f"{C_SYSTEM}[No clipboard tool found - code saved to {path} instead]{C_RESET}")

def handle_copy():
    if not LAST_CODE_BLOCKS:
        print(f"{C_SYSTEM}[No code block from the last reply to copy]{C_RESET}")
        return
    combined = "\n\n".join(LAST_CODE_BLOCKS)
    if copy_to_clipboard(combined):
        print(f"{C_SYSTEM}[Code copied to clipboard again]{C_RESET}")
    else:
        path = _save_code_fallback(combined)
        if path:
            print(f"{C_SYSTEM}[No clipboard tool found - code saved to {path} instead]{C_RESET}")

def ollama_chat(payload):
    """Call Ollama with status checking, bounded retries, and clear failures."""
    last_error = None
    for attempt in range(3):
        try:
            response = requests.post(
                OLLAMA_URL,
                json=payload,
                timeout=OLLAMA_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            data = response.json()
            message = data.get("message")
            if not isinstance(message, dict):
                raise RuntimeError("Ollama response did not contain a message object")
            return message
        except (requests.RequestException, ValueError, RuntimeError) as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Ollama request failed after 3 attempts: {last_error}")

# ---------- CJK glitch guard (terminal is English-first; local models
# occasionally drift into Chinese/Japanese/Korean mid-reply) ----------
CJK_PATTERN = re.compile(
    r"["
    r"\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff"
    r"\u3040-\u309f\u30a0-\u30ff"
    r"\uac00-\ud7af"
    r"\u3000-\u303f\uff00-\uffef"
    r"]"
)

def contains_cjk(text):
    return bool(CJK_PATTERN.search(text or ""))

def strip_cjk(text):
    cleaned = CJK_PATTERN.sub("", text or "")
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip()

class _CJKStreamAbort(Exception):
    """Raised from inside on_token the instant a CJK character shows up in a
    live-streamed reply, so the stream gets cut immediately instead of
    printing a full paragraph of the glitch to the user first."""

def _regenerate_without_cjk(payload, max_retries=2):
    """Used only after a live stream got aborted for producing CJK text.
    Retries non-streamed with an extra system nudge telling the model to
    just continue in the language it was already using; if it still can't
    manage that after a couple of tries, strips any remaining CJK characters
    so the user is never shown the raw glitch either way."""
    nudge = {
        "role": "system",
        "content": ("Your previous reply started producing Chinese/Japanese/"
                    "Korean characters, which is a mistake - that has been "
                    "discarded. Answer again from scratch, purely in the "
                    "language you were already using (never CJK script)."),
    }
    retry_payload = dict(payload)
    retry_payload["messages"] = list(payload["messages"]) + [nudge]
    retry_payload["stream"] = False
    message = None
    for _ in range(max_retries):
        message = ollama_chat(retry_payload)
        if not contains_cjk(message.get("content")):
            return message
    cleaned = strip_cjk(message.get("content")) if message else ""
    return {
        "role": "assistant",
        "content": cleaned or "[Reply kept glitching into another script - try rephrasing your message.]",
        "tool_calls": None,
    }

def ollama_chat_stream(payload, on_token=None):
    """Same contract as ollama_chat (returns a message dict with role/content/
    tool_calls) but streams content tokens to on_token as they arrive, instead
    of waiting for the whole reply. Ollama sends tool_calls as one complete
    block on the final chunk (not token-streamed), so we only know whether
    this turn is a tool call once done=true comes through."""
    stream_payload = dict(payload)
    stream_payload["stream"] = True
    last_error = None
    for attempt in range(3):
        try:
            content_parts = []
            tool_calls = None
            with requests.post(OLLAMA_URL, json=stream_payload, stream=True,
                                timeout=OLLAMA_TIMEOUT_SECONDS) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line)
                    msg = chunk.get("message") or {}
                    token = msg.get("content") or ""
                    if token:
                        content_parts.append(token)
                        if on_token:
                            on_token(token)
                    if msg.get("tool_calls"):
                        tool_calls = msg["tool_calls"]
                    if chunk.get("done"):
                        break
            return {"role": "assistant", "content": "".join(content_parts), "tool_calls": tool_calls}
        except (requests.RequestException, ValueError, RuntimeError) as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Ollama streaming request failed after 3 attempts: {last_error}")

# ---------- Spinning-logo thinking indicator + live streaming ----------
def run_with_thinking_rain(fn, *args, **kwargs):
    """Run fn(*args, **kwargs) while the DIANA logo keeps spinning in place -
    used for the sub-agent path, which still gets one blocking call and
    prints its whole report at once."""
    stop_event = threading.Event()
    spin_thread = threading.Thread(target=pick_thinking_animation(), args=(stop_event,), daemon=True)
    spin_thread.start()
    try:
        return fn(*args, **kwargs)
    finally:
        stop_event.set()
        spin_thread.join()

def run_agent_step_streamed(payload):
    """The interactive turn: spin the logo until the first token arrives,
    then print tokens live as they're generated - real streaming, not a
    fake delay. Returns (message, already_printed).

    If the finished reply turns out to contain fenced code and pygments is
    available, the block gets a quick in-place redraw with full VS Code-style
    highlighting once streaming is done (that's the trade-off for getting
    live output during generation instead of highlighted-but-delayed text).
    The redraw counts literal newlines to reposition the cursor, so on a very
    narrow terminal a long wrapped line could throw it off by a line or two -
    harmless, just cosmetic.
    """
    stop_spinner = threading.Event()
    spin_thread = threading.Thread(target=pick_thinking_animation(), args=(stop_spinner,), daemon=True)
    spin_thread.start()

    state = {"started": False, "newlines": 0}

    def on_token(token):
        if not state["started"]:
            stop_spinner.set()
            spin_thread.join()
            timestamp = time.strftime("%H:%M")
            print(f"{C_SYSTEM}[{timestamp}] {C_DIANA}{persona_label()} \u276f {C_RESET}", end="")
            state["started"] = True
        print(f"{C_DIANA}{token}{C_RESET}", end="", flush=True)
        state["newlines"] += token.count("\n")
        if contains_cjk(token):
            raise _CJKStreamAbort()

    try:
        message = ollama_chat_stream(payload, on_token=on_token)
    except _CJKStreamAbort:
        # State["started"] is always True here - a token had to be printed
        # before it could be checked - so this always has something to erase.
        _clear_block(state["newlines"] + 1)
        return _regenerate_without_cjk(payload), False
    finally:
        if not state["started"]:
            stop_spinner.set()
            spin_thread.join()

    content = (message.get("content") or "")
    if state["started"]:
        print()  # close out the streamed line
        if not message.get("tool_calls") and HAS_PYGMENTS and "```" in content:
            _clear_block(state["newlines"] + 1)
            timestamp = time.strftime("%H:%M")
            print(f"{C_SYSTEM}[{timestamp}] {C_DIANA}{persona_label()} \u276f {C_RESET}", end="")
            print_diana_reply(content.strip())
    return message, state["started"]


# ---------- Agent loop ----------
SESSION_START_TIME = time.time()
SESSION_MESSAGE_COUNT = 0
SESSION_TOOL_CALLS = 0
SESSION_SHELL_COMMANDS = 0
SESSION_TOKENS_SENT_ESTIMATE = 0

def _call_signature(fn_name, fn_args):
    try:
        return fn_name + ":" + json.dumps(fn_args, sort_keys=True)
    except TypeError:
        return fn_name + ":" + str(fn_args)

def _looks_like_failure(result):
    return isinstance(result, str) and result.startswith(("[ERROR", "[BLOCKED", "[SKIPPED"))

def agent_chat(prompt):
    global SESSION_MESSAGE_COUNT, SESSION_TOOL_CALLS, SESSION_TOKENS_SENT_ESTIMATE
    mute_event.clear()
    conversation_history.append({"role": "user", "content": prompt})
    append_to_memory_index("user", prompt, len(conversation_history) - 1)
    SESSION_MESSAGE_COUNT += 1

    # Tracks the exact same tool call failing repeatedly within THIS turn -
    # research on agent reliability found this is one of the most common
    # ways a small local model gets stuck: retrying an identical failing
    # call instead of trying something else. Reset every new user message.
    failure_counts = {}

    for step in range(MAX_AGENT_STEPS):
        try:
            outgoing = build_outgoing_messages(conversation_history)
            if CURRENT_PERSONA == "texty":
                # transient - the current time/occasion, never saved to memory
                outgoing = outgoing + [{"role": "system", "content": build_time_context_note()}]
            SESSION_TOKENS_SENT_ESTIMATE += estimate_tokens(outgoing)
            usage_note = context_usage_note(outgoing)
            if usage_note:
                print(usage_note)
            payload = {
                "model": current_model_name(),
                "messages": outgoing,
                "stream": True,
                "keep_alive": KEEP_ALIVE,
                "options": current_options(),
                "tools": TOOLS
            }
            message, already_printed = run_agent_step_streamed(payload)
        except Exception as e:
            print(f"\n[Error while getting reply: {e}]")
            return

        tool_calls = message.get("tool_calls")

        if not tool_calls:
            reply_text = (message.get("content") or "").strip()
            if not already_printed:
                # streaming produced no content at all (rare - e.g. the model
                # returned an immediate empty reply) - fall back to a normal print
                timestamp = time.strftime("%H:%M")
                print(f"{C_SYSTEM}[{timestamp}] {C_DIANA}{persona_label()} \u276f {C_RESET}", end="")
                print_diana_reply(reply_text)
            conversation_history.append({"role": "assistant", "content": reply_text})
            append_to_memory_index("assistant", reply_text, len(conversation_history) - 1)
            save_memory(conversation_history)
            offer_code_copy(reply_text)
            speak_final_reply(reply_text)
            return

        conversation_history.append(message)

        for call in tool_calls:
            fn = call.get("function", {})
            fn_name = fn.get("name")
            fn_args = fn.get("arguments", {})
            if isinstance(fn_args, str):
                try:
                    fn_args = json.loads(fn_args)
                except json.JSONDecodeError:
                    fn_args = {}

            print(f"{C_TOOL}\n[Diana is using tool: {fn_name}]{C_RESET}")
            SESSION_TOOL_CALLS += 1

            handler = TOOL_DISPATCH.get(fn_name)
            result = handler(fn_args) if handler else f"[ERROR: unknown tool '{fn_name}']"

            if _looks_like_failure(result):
                sig = _call_signature(fn_name, fn_args)
                failure_counts[sig] = failure_counts.get(sig, 0) + 1
                if failure_counts[sig] >= 2:
                    result += (
                        f"\n\n[SYSTEM NOTE: this exact call has now failed "
                        f"{failure_counts[sig]} times in a row this turn - stop repeating it. "
                        "Either try a genuinely different approach, or explain the blocker "
                        "to the user plainly instead of retrying again.]"
                    )

            conversation_history.append({"role": "tool", "content": result})

        save_memory(conversation_history)

    print(f"{C_ERROR}\n[Stopped: reached the {MAX_AGENT_STEPS}-step limit for this turn. Ask again to keep going.]{C_RESET}")
    save_memory(conversation_history)

HELP_TEXT = f"""{C_SYSTEM}
Commands:
  /help                 show this list
  /tools                show what each tool does
  /texty                switch to Texty (companion persona, no project tools)
  /coding               switch back to Diana Coding (agent persona, full tools)
  /model [name|reset]   show/override the model for the current persona
  /cwd <path>           change the working directory (each folder has its own memory)
  /clear                wipe the CURRENT persona's memory for THIS project (asks to confirm)
  /log [n]              show the last n lines of the execution log (default 40)
  /checkpoints [file]   list saved pre-write checkpoints (all files, or one)
  /undo <file> [index]  restore a file from a checkpoint (index 0 = most recent)
  /export [name]        save this conversation to a Markdown file
  /search <text>        search this project's memory for something said before
  /recall <text>        semantic search - finds things by meaning, not exact wording
                         (needs: ollama pull nomic-embed-text, falls back to /search otherwise)
  /stats                show session stats (time, tool calls, tokens sent)
  /gpu                   check whether the current model is fully on GPU or spilling to CPU
  /vram                  show a live VRAM usage bar for the whole card (nvidia-smi)
  /delegate <role> | <task>   spawn a sub-agent directly (e.g. /delegate tester | run the test suite)
  /plan <task>           explore read-only and write a plan - nothing is changed
  /implement             execute the most recent plan from /plan
  /trust [cmd or cmd*]   list, or add, a command that runs without asking again in this project
  /untrust <cmd or #>    remove a trusted command (by exact text or its list index)
  /voice on|off         toggle spoken replies
  exit                  quit

Up/Down arrows recall recent commands. Replies stream live as they're
generated, and a context-usage warning appears once you're past ~60% of the
model's context window.

Tip: drop a DIANA.md file in a project folder and Diana automatically reads
it for project context when you /cwd into that folder (Diana Coding only).
{C_RESET}"""

TOOLS_TEXT = f"""{C_SYSTEM}
read_file(path)              - reads a file, runs immediately, no confirmation
list_dir(path)                - lists a folder, runs immediately, no confirmation
search_files(query, path)     - greps for text across files, runs immediately
edit_file(path, old, new)      - targeted replacement, shows diff and asks y/n
write_file(path, content)     - creates/overwrites a file, shows a diff, backs up
                                 the old version to <path>.bak, asks y/n first
run_shell_command(cmd)         - runs a shell command, asks y/n first
delegate_task(role, task)      - spawns a sub-agent to handle one task and report back

Device control:
list_removable_drives()        - lists USB drive letters, no confirmation
list_android_devices()          - lists connected Android devices (needs adb), no confirmation
adb_device_info(serial)         - reads one authorized device, no confirmation
adb_list_user_apps(serial)      - reads third-party packages, no confirmation
adb_read_only_check(serial)     - reads state/battery/storage, no confirmation
network_inventory()             - reads local interfaces only, no scan/change
check_open_ports()               - lists what's listening on this machine, no scanning
scan_local_network()             - ping-sweeps your own LAN for devices, asks y/n first
usb_list_directory(path)        - reads a selected storage directory
list_android_apps()             - lists installed apps on the device, no confirmation
pull_from_android(remote,local) - copies a file FROM the phone, no confirmation
push_to_android(local,remote)    - copies a file TO the phone, asks y/n first
open_android_app(package)        - launches an app on the phone, asks y/n first
list_running_processes()         - lists laptop processes, no confirmation
open_application(path)           - opens a program/file on the laptop, asks y/n first
close_application(name_or_pid)    - closes a program on the laptop, asks y/n first,
                                     refuses critical system processes outright

Safety boundaries (apply to every tool above):
  - All file paths must be inside the current user-selected project folder ({os.path.basename(PROJECT_ROOT)}
    and its subfolders; /cwd may change this folder from any launch location).
  - run_shell_command only runs commands starting with: {", ".join(ALLOWED_COMMAND_PREFIXES)}
  - Every blocked or declined action is logged to {os.path.basename(EXECUTION_LOG_FILE)}
{C_RESET}"""

def handle_cwd(new_path):
    global conversation_history, PROJECT_ROOT
    if not new_path:
        print(f"{C_SYSTEM}Current directory: {os.getcwd()}{C_RESET}")
        return
    try:
        os.chdir(new_path)
        PROJECT_ROOT = os.getcwd()  # move the file/shell sandbox boundary with us
        conversation_history = load_memory_for_cwd()  # each project keeps its own memory
        note = " (DIANA.md found and loaded)" if os.path.exists("DIANA.md") else ""
        print(f"{C_SYSTEM}Working directory is now: {os.getcwd()}{note}{C_RESET}")
        print(f"{C_SYSTEM}[Tools are now sandboxed to this folder and its subfolders]{C_RESET}")
        welcome = project_welcome_note()
        if welcome:
            print(welcome)
        update_console_title()
    except Exception as e:
        print(f"{C_ERROR}[ERROR changing directory: {e}]{C_RESET}")

# ---------- Persona switch preloading ----------
# The old and new persona's models can never both be resident at once on a
# 6GB card - that's WHY keep_alive=0 exists. This doesn't fight that: it just
# starts loading the new model the instant you type /texty or /coding
# (in the background, non-blocking) instead of waiting for your first real
# message, since by the time you switch the old model has already unloaded
# anyway. Pure timing win, zero extra VRAM cost.
def _warm_up_model(model_name, options):
    """Fire-and-forget nudge to get Ollama loading model_name ahead of time.
    Never touches conversation_history, and any failure here is silently
    swallowed - this is purely an optimization, never something the user
    should see fail or block on."""
    try:
        requests.post(
            OLLAMA_URL,
            json={
                "model": model_name,
                "messages": [{"role": "user", "content": "hi"}],
                "stream": False,
                "keep_alive": KEEP_ALIVE,
                "options": {**options, "num_predict": 1},
            },
            timeout=OLLAMA_TIMEOUT_SECONDS,
        )
    except Exception:
        pass

def preload_persona_model(target_persona):
    model_name = TEXTY_MODEL if target_persona == "texty" else CODING_MODEL_DEFAULT
    options = TEXTY_OPTIONS if target_persona == "texty" else CODING_OPTIONS
    threading.Thread(target=_warm_up_model, args=(model_name, options), daemon=True).start()

_PERSONA_SWITCH_VERBS_AR = [
    "بقى", "بقي", "ابقى", "ابقي", "خليكي", "خليك", "خلي",
    "غيري", "غير", "بدلي", "بدل", "روحي", "روح",
    "كوني", "كون", "اتحولي", "اتحول", "حولي", "حول",
    "رجعي", "رجع", "ادخلي", "ادخل", "ادخلى", "شغلي", "شغل",
    "فعّلي", "فعلي", "فعّل", "فعل", "استخدمي", "استخدم",
    "عايزك تبقي", "عايزك تكون", "عاوزك تبقي", "عاوزك تكون",
    "هات", "جيبي", "جيب", "افتحي", "افتح", "وديني", "وديني على",
]
_PERSONA_SWITCH_VERBS_EN = [
    "switch to", "change to", "change into", "become", "go to", "go into",
    "turn into", "switch mode", "switch persona", "set mode to",
    "enter", "activate", "use", "load", "mode:", "persona:",
]

def detect_persona_switch(text):
    """Best-effort natural-language persona switch, Arabic or English -
    e.g. 'بقى كودينج' or 'switch to texty' - without needing '/coding' or
    '/texty'. Requires an explicit switch verb NEXT TO the persona name, so
    a message that just mentions "coding" in passing (e.g. a question about
    a coding problem) is never mistaken for a switch request.
    """
    if not text or text.startswith("/"):
        return None
    lowered = text.lower()
    target = None
    if re.search(r"\bcoding\b", lowered) or "كودينج" in text or "كودنج" in text:
        target = "coding"
    elif re.search(r"\btexty\b", lowered) or "تكستي" in text:
        target = "texty"
    if not target:
        return None
    has_verb = (any(v in lowered for v in _PERSONA_SWITCH_VERBS_EN) or
                any(v in text for v in _PERSONA_SWITCH_VERBS_AR))
    return target if has_verb else None

def handle_persona_switch(target):
    """Swap who you're talking to, live, without restarting the terminal.
    Each persona keeps its own memory file per project folder, so switching
    back and forth never mixes Diana Coding's and Texty's conversations."""
    global CURRENT_PERSONA, conversation_history, MODEL_OVERRIDE, JUST_SWITCHED_PERSONA
    target = target.strip().lower()
    if target not in ("coding", "texty"):
        print(f"{C_ERROR}[Usage: /coding or /texty]{C_RESET}")
        return
    if target == CURRENT_PERSONA:
        print(f"{C_SYSTEM}[Already talking to {'Texty' if target == 'texty' else 'Diana Coding'}]{C_RESET}")
        return
    CURRENT_PERSONA = target
    MODEL_OVERRIDE = None  # a /model override doesn't follow you across a persona switch
    conversation_history = load_memory_for_cwd()  # loads/creates this persona's own memory file
    JUST_SWITCHED_PERSONA = True  # keep the logo spin (not the purple rain) for the next reply
    label = "Texty" if target == "texty" else "Diana Coding"
    model = current_model_name()
    print(f"{C_SYSTEM}[Switched to {label} - model: {model}]{C_RESET}")
    update_console_title()
    preload_persona_model(target)  # start loading now, not on your first message

def handle_clear():
    global conversation_history
    label = "Texty" if CURRENT_PERSONA == "texty" else "Diana Coding"
    confirm = input(f"{C_CONFIRM}This wipes {label}'s memory for THIS project ({os.getcwd()}). Sure? (y/n) > {C_RESET}").strip().lower()
    if confirm != "y":
        print(f"{C_SYSTEM}[Cancelled]{C_RESET}")
        return
    conversation_history = [{"role": "system", "content": build_system_prompt()}]
    save_memory(conversation_history)
    print(f"{C_SYSTEM}[Memory cleared for this project]{C_RESET}")

def handle_log(n_str):
    n = 40
    if n_str.strip().isdigit():
        n = int(n_str.strip())
    if not os.path.exists(EXECUTION_LOG_FILE):
        print(f"{C_SYSTEM}[No execution log yet]{C_RESET}")
        return
    with open(EXECUTION_LOG_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()
    tail = lines[-n:] if len(lines) > n else lines
    print(f"{C_SYSTEM}" + "".join(tail) + f"{C_RESET}")

# ---------- Main loop ----------
# ---------- Command history (Up/Down arrows) on Windows ----------
COMMAND_HISTORY = []
_HISTORY_MAX = 200

SLASH_COMMANDS = [
    "/help", "/tools", "/texty", "/coding", "/model", "/cwd", "/clear",
    "/log", "/checkpoints", "/undo", "/export", "/delegate", "/copy",
    "/settings", "/voice on", "/voice off", "exit",
]

def correct_slash_command(text):
    """Fuzzy-corrects a typo'd slash command (e.g. '/texy' -> '/texty').

    Only touches input that already starts with '/' and doesn't exactly
    match a known command - plain chat messages (including ones that happen
    to contain a '/') are never rewritten. Cutoff of 0.6 is forgiving enough
    for a dropped/swapped letter but won't fire on an unrelated command.
    """
    if not text.startswith("/"):
        return text
    head = text.split(" ", 1)[0].lower()
    known_heads = sorted({c.split(" ", 1)[0] for c in SLASH_COMMANDS if c.startswith("/")})
    if head in known_heads:
        return text
    match = difflib.get_close_matches(head, known_heads, n=1, cutoff=0.6)
    if not match:
        return text
    corrected_head = match[0]
    corrected = corrected_head + text[len(head):]
    print(f"{C_SYSTEM}[Typo assumed: '{head}' \u2192 '{corrected_head}']{C_RESET}")
    return corrected

def get_completions(text):
    """Tab-completion candidates for the current input buffer: slash commands
    when the buffer starts with '/', otherwise file/folder names under the
    current project root matching the last path-like fragment typed."""
    if text.startswith("/") and " " not in text:
        return [c for c in SLASH_COMMANDS if c.startswith(text)]

    # complete the last whitespace-separated token as a file/dir path
    head, _, fragment = text.rpartition(" ")
    prefix = head + " " if head else ""
    directory, partial = os.path.split(fragment)
    search_root = os.path.join(PROJECT_ROOT, directory) if directory else PROJECT_ROOT
    try:
        entries = sorted(os.listdir(search_root))
    except OSError:
        return []
    matches = [e for e in entries if e.startswith(partial)]
    results = []
    for m in matches[:30]:
        full = os.path.join(directory, m) if directory else m
        full = full.replace(os.sep, "/")
        if os.path.isdir(os.path.join(search_root, m)):
            full += "/"
        results.append(prefix + full)
    return results

def _redraw_input_line(prompt, text):
    print(f"\r\033[2K{prompt}{text}", end="", flush=True)

def input_with_history(prompt):
    """input() with Up/Down arrow-key recall, Tab completion, and support for
    pasting multi-line text (a paste dumps its characters into the console's
    input buffer almost instantly, so an embedded newline immediately
    followed by more waiting input - checked via msvcrt.kbhit() - is treated
    as a literal newline in the buffer rather than submitting early; a real
    Enter keypress has nothing queued right behind it).

    On non-Windows this is a plain input() - the `readline` import above
    already gives those terminals native history for free. Editing here is
    intentionally simple: type, backspace, Up/Down, Tab; no left/right cursor
    movement mid-line, which covers the common cases without reimplementing
    a full line editor."""
    if not HAS_MSVCRT:
        return input(prompt)
    print(prompt, end="", flush=True)
    buf = []
    hist_idx = len(COMMAND_HISTORY)
    while True:
        ch = msvcrt.getwch()
        if ch in ("\r", "\n"):
            if msvcrt.kbhit():
                # more input already queued right behind this newline - this
                # is a paste with embedded line breaks, not a real Enter
                buf.append("\n")
                print()
                continue
            print()
            line = "".join(buf)
            break
        elif ch == "\x08":  # backspace
            if buf:
                if buf[-1] == "\n":
                    buf.pop()
                    print()  # can't un-print a line break cleanly - accept the visual gap
                else:
                    buf.pop()
                    _redraw_input_line(prompt, "".join(buf).rsplit("\n", 1)[-1])
        elif ch == "\x03":  # Ctrl+C
            print()
            raise KeyboardInterrupt
        elif ch == "\t":  # Tab completion
            current = "".join(buf)
            candidates = get_completions(current)
            if len(candidates) == 1:
                buf = list(candidates[0])
                _redraw_input_line(prompt, "".join(buf))
            elif len(candidates) > 1:
                print()
                print(f"{C_SYSTEM}{'    '.join(candidates[:12])}{C_RESET}")
                _redraw_input_line(prompt, "".join(buf))
        elif ch in ("\x00", "\xe0"):  # arrow/function-key prefix
            ch2 = msvcrt.getwch()
            if ch2 == "H" and hist_idx > 0:  # Up
                hist_idx -= 1
                buf = list(COMMAND_HISTORY[hist_idx])
                _redraw_input_line(prompt, "".join(buf))
            elif ch2 == "P":  # Down
                if hist_idx < len(COMMAND_HISTORY) - 1:
                    hist_idx += 1
                    buf = list(COMMAND_HISTORY[hist_idx])
                else:
                    hist_idx = len(COMMAND_HISTORY)
                    buf = []
                _redraw_input_line(prompt, "".join(buf))
            # left/right/home/end intentionally ignored - see docstring
        else:
            buf.append(ch)
            print(ch, end="", flush=True)
    if line.strip():
        COMMAND_HISTORY.append(line)
        if len(COMMAND_HISTORY) > _HISTORY_MAX:
            COMMAND_HISTORY.pop(0)
    return line

# ---------- Session export ----------
def handle_export(arg):
    """Write the current persona's user/assistant turns (no system prompt,
    no raw tool-call plumbing) to a Markdown file the user can keep or share."""
    turns = [m for m in conversation_history if m.get("role") in ("user", "assistant") and m.get("content")]
    if not turns:
        print(f"{C_SYSTEM}[Nothing to export yet]{C_RESET}")
        return
    lines = [f"# {persona_label()} conversation - {time.strftime('%Y-%m-%d %H:%M')}", ""]
    for m in turns:
        speaker = "You" if m["role"] == "user" else persona_label()
        lines.append(f"**{speaker}:**\n\n{m['content']}\n")
    filename = arg.strip() or f"diana_{CURRENT_PERSONA}_export_{time.strftime('%Y%m%d_%H%M%S')}.md"
    if not filename.lower().endswith(".md"):
        filename += ".md"
    out_path = os.path.join(PROJECT_ROOT, filename)
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        print(f"{C_SYSTEM}[Exported to {out_path}]{C_RESET}")
    except Exception as e:
        print(f"{C_ERROR}[ERROR exporting: {e}]{C_RESET}")

# ---------- Memory search ----------
def handle_search(query):
    query = query.strip()
    if not query:
        print(f"{C_ERROR}[Usage: /search <text>]{C_RESET}")
        return
    needle = query.lower()
    matches = [
        (i, m) for i, m in enumerate(conversation_history)
        if m.get("role") in ("user", "assistant") and needle in (m.get("content") or "").lower()
    ]
    if not matches:
        print(f"{C_SYSTEM}[No matches for {query!r} in {persona_label()}'s memory for this project]{C_RESET}")
        return
    print(f"{C_SYSTEM}Found {len(matches)} match(es) (showing up to 20, most recent last):{C_RESET}")
    for i, m in matches[-20:]:
        speaker = "You" if m["role"] == "user" else persona_label()
        text = (m.get("content") or "").replace("\n", " ")
        idx = text.lower().find(needle)
        if len(text) > 160:
            start = max(0, idx - 60)
            snippet = ("..." if start > 0 else "") + text[start:start + 160] + "..."
        else:
            snippet = text
        print(f"{C_SYSTEM}[{speaker}]{C_RESET} {snippet}")

def handle_recall(query):
    """Semantic version of /search - finds things phrased differently than
    the exact words used, via embedding similarity. Falls back to /search
    automatically if the embedding model isn't available."""
    query = query.strip()
    if not query:
        print(f"{C_ERROR}[Usage: /recall <text> - finds things by meaning, not exact wording]{C_RESET}")
        return
    results = semantic_search(query)
    if results is None:
        print(f"{C_SYSTEM}[Semantic search needs the embedding model pulled first: "
              f"ollama pull {EMBEDDING_MODEL} - falling back to /search for now]{C_RESET}")
        handle_search(query)
        return
    if not results:
        print(f"{C_SYSTEM}[Nothing indexed yet for {persona_label()} in this project - "
              f"the index builds up as you chat]{C_RESET}")
        return
    print(f"{C_SYSTEM}Closest matches by meaning:{C_RESET}")
    for score, entry in results:
        speaker = "You" if entry.get("role") == "user" else persona_label()
        snippet = (entry.get("content") or "").replace("\n", " ")[:160]
        print(f"{C_SYSTEM}[{speaker}, {score:.2f}]{C_RESET} {snippet}")

# ---------- Session stats ----------
def handle_stats():
    elapsed = int(time.time() - SESSION_START_TIME)
    hours, rem = divmod(elapsed, 3600)
    minutes, seconds = divmod(rem, 60)
    elapsed_str = f"{hours}h {minutes}m {seconds}s" if hours else f"{minutes}m {seconds}s"
    print(f"{C_SYSTEM}Session stats:{C_RESET}")
    print(f"{C_SYSTEM}  time elapsed:        {elapsed_str}{C_RESET}")
    print(f"{C_SYSTEM}  current persona:     {persona_label()}{C_RESET}")
    print(f"{C_SYSTEM}  messages sent:       {SESSION_MESSAGE_COUNT}{C_RESET}")
    print(f"{C_SYSTEM}  tool calls made:     {SESSION_TOOL_CALLS}{C_RESET}")
    print(f"{C_SYSTEM}  shell commands run:  {SESSION_SHELL_COMMANDS}{C_RESET}")
    print(f"{C_SYSTEM}  ~tokens sent (est.): {SESSION_TOKENS_SENT_ESTIMATE}  (rough 4-chars-per-token estimate){C_RESET}")

# ---------- Smart project-aware welcome ----------
PROJECT_MARKERS = [
    ("package.json", "Node.js project"),
    ("requirements.txt", "Python project (pip)"),
    ("pyproject.toml", "Python project (pyproject)"),
    ("Cargo.toml", "Rust project"),
    ("go.mod", "Go project"),
    ("composer.json", "PHP project"),
    ("Gemfile", "Ruby project"),
    (".git", "Git repository"),
    ("DIANA.md", "has a DIANA.md project brief"),
]

def project_welcome_note():
    found = [label for marker, label in PROJECT_MARKERS if os.path.exists(os.path.join(PROJECT_ROOT, marker))]
    if not found:
        return None
    return f"{C_SYSTEM}[{os.path.basename(PROJECT_ROOT) or PROJECT_ROOT}: {', '.join(found)}]{C_RESET}"

# ---------- Console window title ----------
def set_console_title(text):
    """Best-effort only - silently does nothing outside a real Windows console
    (e.g. this has no effect if stdout is redirected to a file/pipe)."""
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleTitleW(text)
    except Exception:
        pass

def update_console_title():
    set_console_title(f"Diana \u2014 {persona_label()} \u2014 {os.path.basename(PROJECT_ROOT) or PROJECT_ROOT}")

if __name__ == "__main__":
    banner()
    update_console_title()
    preload_persona_model(CURRENT_PERSONA)  # start loading while you read the banner/help text
    welcome = project_welcome_note()
    if welcome:
        print(welcome)
    print(f"{C_SYSTEM}read_file and list_dir run freely. write_file and run_shell_command ask for y/n first.")
    print(f"Type /help for the full command list.{C_RESET}")
    if HAS_MSVCRT:
        print(f"{C_SYSTEM}Press 'm' any time to instantly cut off whatever Diana is saying.{C_RESET}")
    print()

    try:
        while True:
            timestamp = time.strftime("%H:%M")
            user_input = input_with_history(f"{C_SYSTEM}[{timestamp}] {C_RESET}{input_prompt_label()}").strip()
            user_input = correct_slash_command(user_input)

            switch_target = detect_persona_switch(user_input)
            if switch_target:
                handle_persona_switch(switch_target)
                continue

            if user_input.strip().lower() in ("exit", "/exit", "quit", "/quit"):
                break

            if user_input.lower() == "/help":
                print(HELP_TEXT)
                continue

            if user_input.lower() == "/tools":
                print(TOOLS_TEXT)
                continue

            if user_input.lower().startswith("/cwd"):
                handle_cwd(user_input[4:].strip())
                continue

            if user_input.lower() in ("/texty", "/coding"):
                handle_persona_switch(user_input.lower().lstrip("/"))
                continue

            if user_input.lower().startswith("/model"):
                handle_model_command(user_input[len("/model"):].strip())
                continue

            if user_input.lower().startswith("/export"):
                handle_export(user_input[len("/export"):].strip())
                continue

            if user_input.lower().startswith("/checkpoints"):
                handle_checkpoints(user_input[len("/checkpoints"):].strip())
                continue

            if user_input.lower().startswith("/undo"):
                handle_undo(user_input[len("/undo"):].strip())
                continue

            if user_input.lower().startswith("/search"):
                handle_search(user_input[len("/search"):].strip())
                continue

            if user_input.lower().startswith("/recall"):
                handle_recall(user_input[len("/recall"):].strip())
                continue

            if user_input.lower() == "/stats":
                handle_stats()
                continue

            if user_input.lower() == "/gpu":
                handle_gpu()
                continue

            if user_input.lower() == "/vram":
                handle_vram()
                continue

            if user_input.lower() == "/clear":
                handle_clear()
                continue

            if user_input.lower() == "/copy":
                handle_copy()
                continue

            if user_input.lower() == "/settings":
                handle_settings_command()
                continue

            if user_input.lower().startswith("/log"):
                handle_log(user_input[4:].strip())
                continue

            if user_input.lower().startswith("/delegate"):
                remainder = user_input[len("/delegate"):].strip()
                if "|" not in remainder:
                    print(f"{C_ERROR}[Usage: /delegate <role> | <task>]{C_RESET}")
                else:
                    role_part, task_part = remainder.split("|", 1)
                    report = run_sub_agent(role_part.strip(), task_part.strip())
                    print(f"{C_DIANA}\n[Sub-agent report]\n{report}{C_RESET}")
                continue

            if user_input.lower().startswith("/plan"):
                run_plan_mode(user_input[len("/plan"):].strip())
                continue

            if user_input.lower() == "/implement":
                handle_implement()
                continue

            if user_input.lower().startswith("/untrust"):
                handle_untrust(user_input[len("/untrust"):].strip())
                continue

            if user_input.lower().startswith("/trust"):
                handle_trust(user_input[len("/trust"):].strip())
                continue

            if user_input.lower() == "/voice on":
                voice_enabled = True
                print(f"{C_SYSTEM}[Voice mode: ON]{C_RESET}\n")
                continue

            if user_input.lower() == "/voice off":
                voice_enabled = False
                print(f"{C_SYSTEM}[Voice mode: OFF]{C_RESET}\n")
                continue

            if not user_input:
                continue

            agent_chat(user_input)
            print()
    except KeyboardInterrupt:
        print(f"\n{C_SYSTEM}[Ctrl+C - exiting]{C_RESET}")
    finally:
        _mute_listener_should_run.clear()
    print(f"{C_SYSTEM}[Diana terminal closed]{C_RESET}")