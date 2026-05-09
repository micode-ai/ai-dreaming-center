"""Wave 1 smoke: API session lifecycle (start → finish → verify in DB)."""
import sys
import urllib.request
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> int:
    base = "http://localhost:8086"

    req = urllib.request.Request(
        f"{base}/api/session/start",
        data=json.dumps({"project_slug": "test", "agent_name": "smoke", "model": "sonnet"}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        sid = json.load(resp)["id"]
    print("started:", sid)

    req = urllib.request.Request(
        f"{base}/api/session/finish",
        data=json.dumps({
            "session_id": sid, "status": "success",
            "topic": "smoke", "confidence": 0.9,
        }).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        body = json.load(resp)
    assert body.get("ok") is True
    print("finished")

    import sqlite3
    conn = sqlite3.connect("data/dreaming.db")
    row = conn.execute(
        "SELECT id, agent_name, status, topic, confidence FROM agent_learning_sessions WHERE id=?",
        (sid,),
    ).fetchone()
    assert row is not None
    assert row[2] == "success" and row[3] == "smoke" and abs(row[4] - 0.9) < 0.001
    print("verified in DB:", row)
    return 0


if __name__ == "__main__":
    sys.exit(main())
