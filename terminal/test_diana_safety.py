import os
import tempfile
from pathlib import Path

import diana_coding as diana


with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as outside:
    root = os.path.realpath(root)
    outside = os.path.realpath(outside)
    Path(root, "inside.txt").write_text("ok", encoding="utf-8")
    Path(outside, "secret.txt").write_text("secret", encoding="utf-8")
    os.symlink(Path(outside, "secret.txt"), Path(root, "link.txt"))
    diana.PROJECT_ROOT = root

    assert diana.is_inside_project_root("inside.txt")
    assert not diana.is_inside_project_root("../secret.txt")
    assert not diana.is_inside_project_root("link.txt")
    assert diana.is_allowed_command("git status")
    assert diana.is_allowed_command("pytest -q")
    assert diana.is_allowed_command("cd subdir && ls")
    assert not diana.is_allowed_command("cd .. && cat secret.txt")
    assert not diana.is_allowed_command("cat /etc/passwd")
    assert not diana.is_allowed_command("echo hi > outside.txt")
    assert not diana.is_allowed_command("python -c \"open('/etc/passwd').read()\"")
    print("safety policy tests passed")

with tempfile.TemporaryDirectory() as old_root, tempfile.TemporaryDirectory() as new_root:
    diana.PROJECT_ROOT = os.path.realpath(old_root)
    diana.handle_cwd(new_root)
    assert diana.PROJECT_ROOT == os.path.realpath(new_root)
    diana.handle_cwd(old_root)
    assert diana.PROJECT_ROOT == os.path.realpath(old_root)
print("cwd freedom test passed")
