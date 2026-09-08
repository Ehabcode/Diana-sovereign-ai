import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT / "python"
sys.path.insert(0, str(PYTHON_DIR))

import server  # noqa: E402


class FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {"message": {"content": "local reply"}}


saved_calls = []
server.requests.post = lambda *args, **kwargs: FakeResponse()
server.save_memory = lambda persona, history: saved_calls.append((persona, history))
server.private_conversation_histories.clear()
server.app.config["TESTING"] = True
client = server.app.test_client()

private_response = client.post(
    "/chat",
    json={
        "message": "secret message",
        "persona": "texty",
        "private_chat": True,
        "private_id": "private-test-session",
        "voice": False,
    },
)
assert private_response.status_code == 200, private_response.get_data(as_text=True)
assert private_response.get_json()["private"] is True
assert saved_calls == [], "Private chat must never call save_memory"
assert len(server.private_conversation_histories["texty:private-test-session"]) == 3

public_response = client.post(
    "/chat",
    json={"message": "public message", "persona": "texty", "private_chat": False, "voice": False},
)
assert public_response.status_code == 200, public_response.get_data(as_text=True)
assert public_response.get_json()["private"] is False
assert len(saved_calls) == 1, "Public chat should still persist normally"
assert all("secret message" not in str(call) for call in saved_calls)

print("PRIVATE_ROUTE_ISOLATION_OK")
