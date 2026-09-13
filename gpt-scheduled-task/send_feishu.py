#!/usr/bin/env python3
"""Send a Markdown report to a Feishu group bot webhook.

The webhook URL is read from the FEISHU_WEBHOOK_URL environment variable.
It is intentionally never stored in the repository or printed to logs.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

MAX_CHARS = 28000


def split_text(text: str, limit: int = MAX_CHARS) -> list[str]:
    """Split a report into bounded chunks without dropping any characters."""
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + limit, len(text))
        if end < len(text):
            boundary = text.rfind("\n", start, end)
            if boundary > start + limit // 2:
                end = boundary
        chunks.append(text[start:end])
        start = end
    return chunks


def send_chunk(webhook: str, text: str) -> None:
    payload = {"msg_type": "text", "content": {"text": text}}
    request = urllib.request.Request(
        webhook,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            status = response.status
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Feishu webhook HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Feishu webhook network error: {exc.reason}") from exc

    if status >= 300:
        raise RuntimeError(f"Feishu webhook HTTP {status}")

    try:
        result = json.loads(body)
    except json.JSONDecodeError:
        result = {}

    # Feishu bot responses use either code or StatusCode depending on endpoint.
    code = result.get("code", result.get("StatusCode"))
    if code not in (None, 0, "0"):
        message = result.get("msg", result.get("StatusMessage", "unknown error"))
        raise RuntimeError(f"Feishu webhook rejected the message: {message}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path, help="Markdown report file")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate and report chunk sizes without sending",
    )
    args = parser.parse_args()

    if not args.report.is_file():
        print(f"Report file not found: {args.report}", file=sys.stderr)
        return 2

    report = args.report.read_text(encoding="utf-8").strip()
    if not report:
        print("Report file is empty", file=sys.stderr)
        return 2

    chunks = split_text(report)
    if args.dry_run:
        print(f"Feishu delivery dry-run OK: {len(chunks)} chunk(s), {len(report)} characters")
        return 0

    webhook = os.environ.get("FEISHU_WEBHOOK_URL", "").strip()
    if not webhook.startswith("https://"):
        print("FEISHU_WEBHOOK_URL is missing or is not an HTTPS URL", file=sys.stderr)
        return 2

    total = len(chunks)
    for index, chunk in enumerate(chunks, start=1):
        prefix = f"【每日财经日报 {index}/{total}】\n\n" if total > 1 else "【每日财经日报】\n\n"
        send_chunk(webhook, prefix + chunk)
    print(f"Feishu delivery OK: {total} message(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
