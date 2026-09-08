import tempfile
from pathlib import Path

import diana_coding as diana


with tempfile.TemporaryDirectory() as root:
    root = Path(root).resolve()
    diana.PROJECT_ROOT = str(root)
    diana.input = lambda prompt: "y"
    result = diana.tool_run_shell_command("pwd")
    assert str(root) in result, result
    result = diana.tool_run_shell_command("python3 -m py_compile diana_coding.py")
    assert "EXIT_CODE:" in result or result == "[no output]", result
    blocked = diana.tool_run_shell_command("cat /etc/passwd")
    assert blocked.startswith("[BLOCKED:"), blocked
print("shell execution tests passed")
