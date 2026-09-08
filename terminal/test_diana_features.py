import tempfile
from pathlib import Path

import diana_coding as diana


assert any(t["function"]["name"] == "edit_file" for t in diana.TOOLS)
assert any(t["function"]["name"] == "adb_device_info" for t in diana.TOOLS)
assert any(t["function"]["name"] == "network_inventory" for t in diana.TOOLS)
assert diana.is_allowed_command("git status")
assert diana.is_allowed_command("pytest -q")
assert not diana.is_allowed_command("echo hi > file.txt")

with tempfile.TemporaryDirectory() as root:
    root = Path(root).resolve()
    target = root / "sample.txt"
    target.write_text("hello\nworld\n", encoding="utf-8")
    diana.PROJECT_ROOT = str(root)
    diana.input = lambda prompt: "y"
    result = diana.tool_edit_file("sample.txt", "world", "Diana")
    assert "[OK:" in result, result
    assert target.read_text(encoding="utf-8") == "hello\nDiana\n"
    assert (root / "sample.txt.bak").read_text(encoding="utf-8") == "hello\nworld\n"
    result = diana.tool_edit_file("sample.txt", "missing", "x")
    assert "was not found" in result, result
print("feature tests passed")
