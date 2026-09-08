"""Run this from the DianaProject root before your FIRST public git push,
and again before any push after that. It never modifies anything - it only
flags things you should look at by hand.

Usage:
    python pre_publish_check.py
"""
import os
import re
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# Patterns that suggest something personal or secret slipped into a file
# that's about to be committed. Deliberately broad - false positives here
# just mean a quick manual look, a missed real one means a permanent leak.
SUSPECT_PATTERNS = [
    (r"[A-Za-z]:\\Users\\[A-Za-z0-9_.\-]+", "a real Windows user path"),
    (r"/home/(?!ubuntu\b|root\b|user\b)[a-z0-9_\-]+/", "a real Linux home path"),
    (r"\b\d{5,}:[A-Za-z0-9_\-]{30,}\b", "something that looks like a bot/API token"),
    # Matches a REAL assignment of a short quoted number to a pass-key-like
    # name (upper/lower/camelCase, with underscore or hyphen). Deliberately
    # requires the assignment shape (an "=" or ":" right after the name),
    # which ordinary CSS/JS identifiers never have, so it won't fire on
    # something like a "profile-v1" class name while still catching the
    # actual leak shape regardless of naming style.
    (r"(?i)pass[_\s-]?key[a-zA-Z_]*\s*[:=]\s*['\"]\d{1,4}['\"]", "a plaintext short pass key assigned in code"),
    (r"(?i)api[_-]?key\s*=\s*['\"][^'\"]{10,}", "a hardcoded API key"),
    (r"(?i)(secret|password|token)\s*=\s*['\"][^'\"]{6,}", "a hardcoded secret/password"),
]

# Files/extensions that should never be committed in the first place -
# if any of these exist and are tracked by git, .gitignore has a gap.
SENSITIVE_PATH_HINTS = (
    "memory", "_memory.json", ".diana_checkpoints", ".diana_trusted_commands.json",
    "plans", "logs", ".env", "secrets",
)

SCAN_EXTENSIONS = {".py", ".md", ".txt", ".json", ".bat", ".sh", ".cjs", ".js", ".html", ".css"}
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "venv_fast",
             "venv_quality", "models", "wheels", "legacy", "vendor", "out", "dist",
             "build", "backend", "DianaProject_Icons_VRAM_Fixed", "diana-terminal"}
SKIP_FILE_PREFIXES = {".aider"}


def scan_file(path):
    findings = []
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except OSError:
        return findings
    for pattern, label in SUSPECT_PATTERNS:
        if re.search(pattern, content):
            findings.append(label)
    return findings


def main():
    print("Scanning for things that shouldn't go public...\n")
    text_hits = []
    sensitive_paths = []

    for root, dirs, files in os.walk(PROJECT_ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".git")]
        for name in files:
            if any(name.startswith(pfx) for pfx in SKIP_FILE_PREFIXES):
                continue
            full_path = os.path.join(root, name)
            rel_path = os.path.relpath(full_path, PROJECT_ROOT)

            if any(hint in rel_path.lower() for hint in SENSITIVE_PATH_HINTS):
                sensitive_paths.append(rel_path)

            if os.path.splitext(name)[1].lower() in SCAN_EXTENSIONS:
                findings = scan_file(full_path)
                for label in findings:
                    text_hits.append((rel_path, label))

    if sensitive_paths:
        print("These paths look like personal data / secrets - make sure .gitignore covers them:")
        for p in sorted(set(sensitive_paths)):
            print(f"  - {p}")
        print()

    if text_hits:
        print("These files contain something worth a manual look:")
        for path, label in text_hits:
            print(f"  - {path}: possible {label}")
        print()

    if not sensitive_paths and not text_hits:
        print("Nothing flagged. Still worth a manual skim of README/CHANGELOG files by eye -")
        print("this script catches patterns, not judgment.")
        return 0

    print("Nothing here was changed automatically - review each one, then re-run this")
    print("script until it comes back clean before your first public push.")
    return 1


if __name__ == "__main__":
    sys.exit(main())