#!/usr/bin/env python3
"""Generate a source-backed finance digest after the TrendRadar crawl.

TrendRadar remains responsible for collection. This script performs the
finance-specific merge and optional Gemini summary, so the native TrendRadar AI
pipeline can stay disabled. Missing optional clients or API keys never create
fake data: the report falls back to a deterministic source list.
"""

from __future__ import annotations

import argparse
import datetime as dt
import email.utils
import hashlib
import html
import json
import os
import re
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:  # pragma: no cover - workflow installs PyYAML
    raise SystemExit(f"缺少 PyYAML：{exc}")


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "daily_digest.yaml"
SOURCES_PATH = ROOT / "config" / "digest_sources.json"
USER_AGENT = "finance-daily-briefing/1.0 (+https://github.com/emilyyyho/finance-daily-briefing)"
CN_TZ = dt.timezone(dt.timedelta(hours=8))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    parser.add_argument("--sources", type=Path, default=SOURCES_PATH)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    value = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", " ", str(value), flags=re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def child_text(node: ET.Element, names: set[str]) -> str:
    for child in list(node):
        if local_name(child.tag) in names:
            href = child.attrib.get("href")
            return (href or child.text or "").strip()
    return ""


def parse_datetime(value: Any) -> dt.datetime | None:
    if isinstance(value, dt.datetime):
        parsed = value
    else:
        raw = str(value or "").strip()
        if not raw:
            return None
        try:
            parsed = email.utils.parsedate_to_datetime(raw)
        except (TypeError, ValueError, IndexError):
            try:
                parsed = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def fetch_bytes(url: str, timeout: int = 25, accept: str = "*/*") -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": accept},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read(4_000_000)


def load_config(path: Path, sources_path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    config = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    sources = json.loads(sources_path.read_text(encoding="utf-8"))
    return config, sources


def read_rss(source: dict[str, Any], now: dt.datetime, max_age_hours: float) -> tuple[list[dict[str, Any]], str | None]:
    try:
        root = ET.fromstring(fetch_bytes(source["url"], accept="application/rss+xml, application/atom+xml, application/xml, text/xml"))
    except (OSError, urllib.error.URLError, ET.ParseError, KeyError) as exc:
        return [], f"{type(exc).__name__}: {exc}"

    items: list[dict[str, Any]] = []
    for node in root.iter():
        if local_name(node.tag) not in {"item", "entry"}:
            continue
        title = clean_text(child_text(node, {"title"}))
        link = child_text(node, {"link", "guid", "id"})
        if not link:
            for child in list(node):
                if local_name(child.tag) == "link" and child.attrib.get("href"):
                    link = child.attrib["href"]
                    break
        published = parse_datetime(child_text(node, {"pubdate", "published", "updated", "date", "issued"}))
        if not title or not link or not published:
            continue
        age_hours = (now - published).total_seconds() / 3600
        if age_hours < -2 or age_hours > max_age_hours:
            continue
        description = clean_text(child_text(node, {"description", "summary", "content"}))
        if len(description) > 320:
            description = description[:317].rstrip() + "..."
        items.append({
            "title": title,
            "link": link,
            "published": published,
            "description": description,
            "source": source["name"],
            "category": source.get("category", "财经资讯"),
            "tier": source.get("tier", "media"),
            "score": float(source.get("weight", 1)) + max(0.0, 1.0 - max(age_hours, 0.0) / max(max_age_hours, 1.0)),
            "kind": "rss",
        })
    return items, None


def read_trendradar_items(now: dt.datetime, max_age_hours: float) -> tuple[list[dict[str, Any]], str | None]:
    """Read the newest local SQLite snapshot written by the same Action run."""
    db_files = sorted((ROOT / "output" / "news").glob("*.db"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not db_files:
        return [], "未找到 TrendRadar output/news/*.db"
    db_path = db_files[0]
    allowed_ids: list[str] = []
    trend_config_path = ROOT / "config" / "config.yaml"
    try:
        trend_config = yaml.safe_load(trend_config_path.read_text(encoding="utf-8")) or {}
        allowed_ids = [str(item.get("id")) for item in (trend_config.get("platforms") or {}).get("sources", []) if item.get("id")]
    except (OSError, yaml.YAMLError):
        # The digest can still operate from RSS when TrendRadar's config is absent.
        allowed_ids = []

    where = "WHERE n.rank > 0"
    params: list[Any] = []
    if allowed_ids:
        placeholders = ",".join("?" for _ in allowed_ids)
        where += f" AND n.platform_id IN ({placeholders})"
        params.extend(allowed_ids)
    try:
        connection = sqlite3.connect(db_path)
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            f"""
            SELECT n.title, n.platform_id, n.rank, n.url, n.mobile_url,
                   n.last_crawl_time, p.name AS platform_name
            FROM news_items n
            LEFT JOIN platforms p ON p.id = n.platform_id
            {where}
            ORDER BY n.rank ASC
            """,
            params,
        ).fetchall()
    except sqlite3.Error as exc:
        return [], f"SQLite：{exc}"
    finally:
        try:
            connection.close()
        except UnboundLocalError:
            pass

    items: list[dict[str, Any]] = []
    for row in rows:
        crawl_time = parse_datetime(row["last_crawl_time"])
        # TrendRadar 的历史版本可能只保存 HH:MM；这种情况下保留最新快照，
        # 但不把它冒充成精确发布时间。
        published = crawl_time or now
        age_hours = (now - published).total_seconds() / 3600 if crawl_time else 0
        if crawl_time and (age_hours < -2 or age_hours > max_age_hours):
            continue
        rank = int(row["rank"] or 999)
        platform = row["platform_name"] or row["platform_id"] or "TrendRadar"
        title = clean_text(row["title"])
        link = row["url"] or row["mobile_url"] or ""
        if not title:
            continue
        items.append({
            "title": title,
            "link": link,
            "published": published,
            "description": f"TrendRadar 热榜排名 {rank}",
            "source": platform,
            "category": "中文财经热榜",
            "tier": "aggregator",
            "score": 2.0 + max(0.0, 2.0 - rank / 10),
            "kind": "hotlist",
            "rank": rank,
        })
    return items, None


def normalize_title(title: str) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", title.lower())


def dedupe(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    for item in items:
        identity = normalize_title(item["title"]) or hashlib.sha1(item["link"].encode()).hexdigest()
        previous = best.get(identity)
        if previous is None or (item["score"], item["published"]) > (previous["score"], previous["published"]):
            best[identity] = item
    return sorted(best.values(), key=lambda value: (value["score"], value["published"]), reverse=True)


FINANCE_TERMS = (
    "股", "股票", "股市", "A股", "港股", "美股", "基金", "债", "债券", "利率", "央行",
    "人民币", "美元", "黄金", "白银", "原油", "期货", "银行", "证券", "保险", "地产", "楼市",
    "上市", "财报", "利润", "营收", "分红", "并购", "融资", "IPO", "出口", "进口", "关税",
    "制造", "芯片", "新能源", "汽车", "医药", "消费", "经济", "GDP", "CPI", "PPI", "降息", "加息", "汇率",
)


def diversify(items: list[dict[str, Any]], limit: int, per_source: int = 5, min_china_news: int = 8) -> list[dict[str, Any]]:
    """Keep source diversity and reserve room for Chinese finance headlines."""
    selected: list[dict[str, Any]] = []
    counts: dict[str, int] = {}

    def add(item: dict[str, Any]) -> bool:
        source = item.get("source", "")
        if counts.get(source, 0) >= per_source:
            return False
        selected.append(item)
        counts[source] = counts.get(source, 0) + 1
        return True

    chinese = [
        item for item in items
        if item.get("kind") == "hotlist" and any(term in item.get("title", "") for term in FINANCE_TERMS)
    ]
    for item in chinese:
        if len(selected) >= min(limit, min_china_news):
            break
        add(item)
    for item in items:
        if len(selected) >= limit:
            break
        if item in selected:
            continue
        add(item)
    return selected


def collect_akshare(config: dict[str, Any], now: dt.datetime) -> tuple[list[dict[str, Any]], str | None]:
    watchlist = (config.get("watchlist") or {}).get("a_share") or []
    if not watchlist:
        return [], "未配置 A 股 watchlist，跳过 AKShare 研报"
    try:
        import akshare as ak  # type: ignore
    except ImportError:
        return [], "未安装 akshare（workflow 会尝试安装；本地 dry-run 可忽略）"

    results: list[dict[str, Any]] = []
    errors: list[str] = []
    for entry in watchlist:
        item = {"symbol": entry} if isinstance(entry, str) else entry
        symbol = str(item.get("symbol", "")).strip()
        if not symbol:
            continue
        try:
            frame = ak.stock_research_report_em(symbol=symbol)
            rows = frame.to_dict(orient="records")
            for row in rows[:8]:
                report_date = row.get("日期") or row.get("报告日期")
                published = parse_datetime(report_date) or now
                if (now - published).total_seconds() > 24 * 3600 * 45:
                    continue
                title = clean_text(row.get("报告名称")) or f"{symbol} 最新公开研报"
                link = clean_text(row.get("报告PDF链接"))
                details = "；".join(filter(None, [clean_text(row.get("机构")), clean_text(row.get("东财评级")), str(report_date or "")]))
                results.append({
                    "title": f"{item.get('name', symbol)}：{title}",
                    "link": link,
                    "published": published,
                    "description": details or "AKShare 个股研报目录",
                    "source": "AKShare / 东方财富研报目录",
                    "category": "A股研报",
                    "tier": "data",
                    "score": 3.5,
                    "kind": "akshare",
                })
        except Exception as exc:  # upstream interfaces can change
            errors.append(f"{symbol}: {type(exc).__name__}: {exc}")
    return results, "；".join(errors) if errors else None


def sec_filing_link(cik: str, accession: str, document: str) -> str:
    accession_path = accession.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_path}/{document}"


def load_sec_ticker_map() -> dict[str, str]:
    payload = json.loads(fetch_bytes("https://www.sec.gov/files/company_tickers.json", accept="application/json"))
    return {
        str(value.get("ticker", "")).upper(): str(value.get("cik_str", "")).zfill(10)
        for value in payload.values()
        if value.get("ticker") and value.get("cik_str")
    }


def collect_sec(config: dict[str, Any], now: dt.datetime) -> tuple[list[dict[str, Any]], str | None]:
    watchlist = (config.get("watchlist") or {}).get("us") or []
    if not watchlist:
        return [], "未配置美股 CIK，跳过 SEC EDGAR"
    results: list[dict[str, Any]] = []
    errors: list[str] = []
    max_items = int(config.get("max_filings_per_company", 8))
    ticker_map: dict[str, str] = {}
    if any(isinstance(entry, dict) and not entry.get("cik") and entry.get("ticker") for entry in watchlist):
        try:
            ticker_map = load_sec_ticker_map()
        except (OSError, urllib.error.URLError, json.JSONDecodeError, KeyError, ValueError) as exc:
            return [], f"无法读取 SEC ticker 目录：{type(exc).__name__}: {exc}"
    for entry in watchlist:
        item = {"cik": entry} if isinstance(entry, str) else entry
        raw_cik = item.get("cik") or ticker_map.get(str(item.get("ticker", "")).upper(), "")
        cik = re.sub(r"\D", "", str(raw_cik)).zfill(10)
        if not cik or cik == "0000000000":
            continue
        url = f"https://data.sec.gov/submissions/CIK{cik}.json"
        try:
            payload = json.loads(fetch_bytes(url, accept="application/json"))
            recent = payload.get("filings", {}).get("recent", {})
            forms = recent.get("form", [])
            dates = recent.get("filingDate", [])
            accessions = recent.get("accessionNumber", [])
            documents = recent.get("primaryDocument", [])
            accepted = recent.get("acceptanceDateTime", [])
            allowed_forms = {"8-K", "10-K", "10-Q", "20-F", "6-K", "4", "13D", "13G", "13F-HR"}
            count = 0
            for index, form in enumerate(forms):
                if form not in allowed_forms or count >= max_items:
                    continue
                published = parse_datetime(accepted[index] if index < len(accepted) else dates[index] if index < len(dates) else "")
                if not published or (now - published).total_seconds() > 24 * 3600 * 45:
                    continue
                accession = accessions[index] if index < len(accessions) else ""
                document = documents[index] if index < len(documents) else ""
                link = sec_filing_link(cik, accession, document) if accession and document else f"https://www.sec.gov/edgar/browse/?CIK={int(cik)}"
                company = item.get("name") or item.get("ticker") or f"CIK {int(cik)}"
                results.append({
                    "title": f"{company} 提交 {form}：{document or accession}",
                    "link": link,
                    "published": published,
                    "description": f"SEC EDGAR 官方申报，提交日期 {dates[index] if index < len(dates) else '未知'}",
                    "source": "SEC EDGAR",
                    "category": "美股公司披露",
                    "tier": "official",
                    "score": 5.0,
                    "kind": "sec",
                })
                count += 1
        except (OSError, urllib.error.URLError, json.JSONDecodeError, KeyError, ValueError) as exc:
            errors.append(f"{cik}: {type(exc).__name__}: {exc}")
    return results, "；".join(errors) if errors else None


def build_prompt(items: list[dict[str, Any]], ak_items: list[dict[str, Any]], sec_items: list[dict[str, Any]], now: dt.datetime) -> str:
    lines = [
        "你是财经信息编辑。请仅根据 <data> 中的材料写一份中文日报，不得补充材料外的事实、价格或日期。",
        "把事实与推断分开；没有足够证据时写‘待核实’；不要给出买入、卖出或仓位建议。",
        "请按以下结构输出 Markdown：",
        "1. 今日最重要的 3-5 个主题（每条说明发生了什么、可能影响的资产/行业、引用材料编号）",
        "2. A 股研报与美股披露（若无则写无）",
        "3. 多源一致性与待核实信息",
        "4. 明日观察清单",
        "每个事实后用 [编号] 标注来源编号。生成时间：" + now.astimezone(CN_TZ).strftime("%Y-%m-%d %H:%M"),
        "<data>",
    ]
    all_items = items + ak_items + sec_items
    for index, item in enumerate(all_items, 1):
        published = item["published"].astimezone(CN_TZ).strftime("%m-%d %H:%M")
        lines.append(f"[{index}] {item['source']} | {published} | {item['title']} | {item.get('description', '')} | {item.get('link', '')}")
    lines.append("</data>")
    return "\n".join(lines)


def generate_ai_summary(prompt: str, config: dict[str, Any]) -> tuple[str | None, str | None]:
    ai_config = config.get("ai") or {}
    if not ai_config.get("enabled", True):
        return None, "AI 摘要已在配置中关闭"
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("AI_API_KEY")
    if not api_key:
        return None, "未配置 GEMINI_API_KEY，使用规则整理"
    model = os.getenv("GEMINI_MODEL") or ai_config.get("model", "gemini-2.5-flash")
    query = urllib.parse.quote(str(model), safe="")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{query}:generateContent?key={urllib.parse.quote(api_key)}"
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": float(ai_config.get("temperature", 0.2)),
            "maxOutputTokens": int(ai_config.get("max_output_tokens", 1800)),
        },
    }
    request = urllib.request.Request(url, data=json.dumps(body, ensure_ascii=False).encode("utf-8"), headers={"Content-Type": "application/json", "User-Agent": USER_AGENT}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            payload = json.loads(response.read().decode("utf-8"))
        text = payload["candidates"][0]["content"]["parts"][0]["text"].strip()
        return (text or None), None if text else "Gemini 返回空内容"
    except (OSError, urllib.error.URLError, json.JSONDecodeError, KeyError, IndexError, TypeError, ValueError) as exc:
        return None, f"Gemini 调用失败：{type(exc).__name__}: {exc}"


def fallback_summary(items: list[dict[str, Any]], ak_items: list[dict[str, Any]], sec_items: list[dict[str, Any]]) -> str:
    lines = ["本次未配置可用的 AI API，以下为规则整理：", ""]
    if items:
        lines.append("- 重点主题按来源级别、热榜排名和新鲜度排序；请查看下方来源明细。")
    if ak_items:
        lines.append(f"- AKShare：发现 {len(ak_items)} 条配置标的研报目录。")
    if sec_items:
        lines.append(f"- SEC EDGAR：发现 {len(sec_items)} 条配置公司的官方申报。")
    if not items and not ak_items and not sec_items:
        lines.append("- 本次没有获得通过时间校验的材料。")
    return "\n".join(lines)


def format_report(items: list[dict[str, Any]], ak_items: list[dict[str, Any]], sec_items: list[dict[str, Any]], statuses: list[str], summary: str, now: dt.datetime, max_age_hours: float) -> str:
    lines = [
        "# 定制化每日财经日报",
        "",
        f"> 生成时间：{now.astimezone(CN_TZ):%Y-%m-%d %H:%M}（北京时间）",
        f"> 采集窗口：最近 {max_age_hours:g} 小时；官方披露优先，所有条目保留原文链接。",
        "> 说明：AI 只负责编辑已采集材料；内容不构成投资建议，关键数字请点击原文复核。",
        "",
        "## AI 梳理",
        "",
        summary,
        "",
        "## 结构化数据",
        "",
    ]
    if ak_items:
        lines.append(f"- A 股研报：{len(ak_items)} 条")
    else:
        lines.append("- A 股研报：本次未配置或未获取到标的研报")
    if sec_items:
        lines.append(f"- 美股 SEC 披露：{len(sec_items)} 条")
    else:
        lines.append("- 美股 SEC 披露：本次未配置或未获取到公司申报")
    lines.extend(["", "## 来源明细", ""])
    all_items = items + ak_items + sec_items
    if not all_items:
        lines.append("本次没有获得通过时间校验的资讯。")
    for index, item in enumerate(all_items, 1):
        marker = {"official": "官方", "media": "媒体", "data": "数据", "aggregator": "聚合"}.get(item.get("tier"), "来源")
        published = item["published"].astimezone(CN_TZ)
        lines.append(f"{index}. **{item['title']}**")
        lines.append(f"   - 来源：{item['source']}（{marker}）｜{item['category']}｜{published:%m-%d %H:%M}")
        if item.get("description"):
            lines.append(f"   - 说明：{item['description']}")
        if item.get("link"):
            lines.append(f"   - [阅读原文]({item['link']})")
        lines.append("")
    lines.extend(["## 采集状态", ""])
    lines.extend(f"- {status}" for status in statuses)
    lines.extend(["", "---", "由 GitHub Actions 定时运行；如需改变标的或来源，编辑 config/ 下的配置文件。"])
    return "\n".join(lines) + "\n"


def chunks(text: str, limit: int = 3800) -> list[str]:
    if len(text) <= limit:
        return [text]
    parts: list[str] = []
    current = ""
    for line in text.splitlines(keepends=True):
        if current and len(current) + len(line) > limit:
            parts.append(current)
            current = ""
        current += line
    if current:
        parts.append(current)
    return parts


def post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), headers={"Content-Type": "application/json", "User-Agent": USER_AGENT}, method="POST")
    with urllib.request.urlopen(request, timeout=20) as response:
        body = response.read().decode("utf-8", errors="replace")
        return json.loads(body) if body else {}


def deliver(report: str, dry_run: bool) -> list[str]:
    if dry_run:
        return ["dry-run"]
    delivered: list[str] = []
    failures: list[str] = []
    for name, env_name, sender in [("飞书", "FEISHU_WEBHOOK_URL", "feishu"), ("企业微信", "WECOM_WEBHOOK_URL", "wecom")]:
        url = os.getenv(env_name) or (os.getenv("WEWORK_WEBHOOK_URL") if name == "企业微信" else "")
        if not url:
            continue
        try:
            # WeCom enforces a 4096-byte limit. 1200 characters keeps a
            # Chinese-heavy Markdown part below that limit with headroom;
            # Feishu accepts the larger part size.
            part_limit = 1200 if sender == "wecom" else 3800
            for part in chunks(report, part_limit):
                if sender == "feishu":
                    payload = {"msg_type": "interactive", "card": {"config": {"wide_screen_mode": True}, "header": {"template": "blue", "title": {"tag": "plain_text", "content": "定制化每日财经日报"}}, "elements": [{"tag": "div", "text": {"tag": "lark_md", "content": part}}]}}
                else:
                    payload = {"msgtype": "markdown", "markdown": {"content": part}}
                result = post_json(url, payload)
                if (sender == "feishu" and result.get("code", 0) not in (0, None)) or (sender == "wecom" and result.get("errcode", 0) != 0):
                    raise RuntimeError(str(result))
            delivered.append(name)
        except (OSError, urllib.error.URLError, ValueError, RuntimeError) as exc:
            failures.append(f"{name}: {exc}")
    if failures:
        raise RuntimeError("；".join(failures))
    return delivered


def main() -> int:
    # GitHub Actions is UTF-8, but local Windows shells often default to GBK.
    # Keep dry-run diagnostics readable without changing the report file.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    args = parse_args()
    try:
        config, sources = load_config(args.config, args.sources)
    except (OSError, json.JSONDecodeError, yaml.YAMLError) as exc:
        print(f"配置读取失败：{exc}", file=sys.stderr)
        return 1
    now = dt.datetime.now(dt.timezone.utc)
    max_age_hours = float(config.get("lookback_hours", 36))
    statuses: list[str] = []
    rss_items: list[dict[str, Any]] = []
    for source in sources:
        if not source.get("enabled", True):
            continue
        current, error = read_rss(source, now, max_age_hours)
        rss_items.extend(current)
        statuses.append(f"{'⚠️' if error else '✅'} {source.get('name', source.get('url'))}：{error or f'{len(current)} 条'}")
    hot_items, hot_error = read_trendradar_items(now, max_age_hours)
    statuses.append(f"{'⚠️' if hot_error else '✅'} TrendRadar 热榜：{hot_error or f'{len(hot_items)} 条'}")
    ak_items, ak_error = collect_akshare(config, now)
    sec_items, sec_error = collect_sec(config, now)
    statuses.append(f"{'⚠️' if ak_error and ak_items == [] else '✅'} AKShare：{ak_error or f'{len(ak_items)} 条'}")
    statuses.append(f"{'⚠️' if sec_error and sec_items == [] else '✅'} SEC EDGAR：{sec_error or f'{len(sec_items)} 条'}")
    items = diversify(
        dedupe(rss_items + hot_items),
        max(1, int(config.get("max_news", 20))),
        min_china_news=max(0, int(config.get("min_china_news", 8))),
    )
    prompt = build_prompt(items, ak_items, sec_items, now)
    ai_summary, ai_error = generate_ai_summary(prompt, config)
    if ai_error:
        statuses.append(f"ℹ️ AI：{ai_error}")
    summary = ai_summary or fallback_summary(items, ak_items, sec_items)
    report = format_report(items, ak_items, sec_items, statuses, summary, now, max_age_hours)
    output = args.output or ROOT / "output" / f"daily-digest-{now.astimezone(CN_TZ):%Y-%m-%d-%H%M}.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8")
    print(report)
    try:
        delivered = deliver(report, args.dry_run)
    except RuntimeError as exc:
        print(f"推送失败：{exc}", file=sys.stderr)
        return 3
    print(f"已推送到：{', '.join(delivered)}" if delivered else "未配置推送 Webhook；报告已写入 output/。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
