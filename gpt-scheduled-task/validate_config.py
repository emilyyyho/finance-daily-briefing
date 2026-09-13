"""Validate the no-secret configuration used by the ChatGPT task."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "newsnow_task.json"

def main() -> None:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    assert config["timezone"] == "Asia/Shanghai"
    assert config["schedule"]["local_time"] == "20:30"
    assert config["schedule"]["cron_utc"] == "30 12 * * *"
    assert config["newsnow"]["base_url"] == "https://newsnow.busiyi.world/api/s"
    assert len(config["newsnow"]["source_ids"]) == 16
    assert len(config["newsnow"]["endpoints"]) == 16
    assert config["newsnow"]["max_age_hours"] == 24
    assert 1 <= config["newsnow"]["min_china_items"] <= config["newsnow"]["max_items"]
    assert config["ai"]["external_api"] is False
    assert config["delivery"]["feishu"]["enabled"] is True

    for endpoint in config["newsnow"]["endpoints"]:
        parsed = urlparse(endpoint["url"])
        assert parsed.scheme == "https", endpoint["url"]
        assert parsed.netloc == "newsnow.busiyi.world", endpoint["url"]
        assert "key=" not in endpoint["url"].lower(), "API keys must not be committed"

    print("GPT scheduled task configuration: OK")

if __name__ == "__main__":
    main()
