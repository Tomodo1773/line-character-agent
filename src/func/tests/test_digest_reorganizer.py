import json
from pathlib import Path

from digest_reorganizer import DigestReorganizer


class DummyAgent:
    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace

    def invoke(self, _input, /, stream_mode=None) -> None:  # noqa: ANN001 - interface compatibility
        digest_path = self.workspace / "digest.json"
        data = json.loads(digest_path.read_text(encoding="utf-8"))
        data["monthly"].append(
            {
                "month": "2025-01",
                "summary": "January summary",
                "highlights": data.get("daily", []),
            }
        )
        data["daily"] = []
        digest_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


class NoOpAgent:
    def __init__(self, workspace: Path) -> None:  # noqa: ANN001 - factory compatibility
        self.workspace = workspace

    def invoke(self, _input, /, stream_mode=None) -> None:  # noqa: ANN001 - interface compatibility
        # 何もしない（ファイルは初期値のまま）
        return None


def test_reorganize_moves_daily_into_monthly_and_updates_date():
    digest = {
        "version": "2.0",
        "lastUpdated": "2024-12-01",
        "daily": [{"date": "2024-12-31", "text": "大晦日の出来事"}],
        "monthly": [],
        "yearly": [],
    }

    reorganizer = DigestReorganizer(agent_factory=lambda workspace: DummyAgent(workspace))
    result = reorganizer.reorganize(json.dumps(digest, ensure_ascii=False), today_override="2025-01-31")

    updated = json.loads(result)
    assert updated["lastUpdated"] == "2025-01-31"
    assert updated["daily"] == []
    assert updated["monthly"][0]["month"] == "2025-01"
    assert updated["monthly"][0]["highlights"][0]["text"] == "大晦日の出来事"


def test_invalid_json_is_reinitialized_with_defaults():
    reorganizer = DigestReorganizer(agent_factory=NoOpAgent)
    result = reorganizer.reorganize("not-json", today_override="2025-02-01")

    updated = json.loads(result)
    assert updated["version"] == "2.0"
    assert updated["daily"] == []
    assert updated["lastUpdated"] == "2025-02-01"
