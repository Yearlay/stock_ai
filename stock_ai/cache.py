"""本地行情缓存：data/{etf,stock}/{code}.json。

命中缓存时直接返回；未命中时由 eastmoney 客户端抓取并回写。
默认日线（前复权）数据统一累积在 ``data.kline_records``，按日期追加/覆盖；
同时兼容东财风格 ``{"data": {"klines": [...]}}`` 文件。
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path

_DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR = Path(os.environ.get("STOCK_AI_DATA_DIR", _DEFAULT_DATA_DIR))
KLINE_TITLE = [
    "日期", "开盘价", "收盘价", "最高价", "最低价", "成交量",
    "成交额", "振幅", "涨跌幅", "涨跌额", "换手率",
]

_log = logging.getLogger(__name__)


def cache_path(code: str) -> Path:
    code = str(code).strip()
    kind = "etf" if code and code[0] in "15" else "stock"
    return DATA_DIR / kind / f"{code}.json"


def history_key(period, adjust, start, end) -> str:
    return f"{period}:{adjust}:{start}:{end}"


def _number(value, cast=float):
    if value is None or value == "-" or value == "":
        return None
    try:
        return cast(value)
    except (TypeError, ValueError):
        return None


def parse_klines(lines) -> list:
    records = []
    for line in lines or []:
        parts = str(line).split(",")
        if len(parts) < 8:
            continue
        records.append({
            "date": parts[0],
            "open": _number(parts[1]),
            "close": _number(parts[2]),
            "high": _number(parts[3]),
            "low": _number(parts[4]),
            "volume": _number(parts[5], int),
            "amount": _number(parts[6]),
            "amplitude": _number(parts[7]),
            "pct_change": _number(parts[8]) if len(parts) > 8 else None,
            "change": _number(parts[9]) if len(parts) > 9 else None,
            "turnover_rate": _number(parts[10]) if len(parts) > 10 else None,
        })
    return records


def _normalize_records(value) -> list:
    records = []
    for item in value or []:
        if isinstance(item, dict):
            records.append(dict(item))
        else:
            records.extend(parse_klines([item]))
    return records


def _read_records(obj: dict) -> list:
    data = obj.get("data")
    if isinstance(data, dict) and isinstance(data.get("kline_records"), list):
        return _normalize_records(data["kline_records"])
    if isinstance(obj.get("kline_records"), list):
        return _normalize_records(obj["kline_records"])
    if isinstance(data, dict) and isinstance(data.get("klines"), list):
        return _normalize_records(data["klines"])
    return []


def _records_container(obj: dict):
    data = obj.get("data")
    if not isinstance(data, dict):
        data = {}
        obj["data"] = data
    if isinstance(data.get("kline_records"), list):
        return data, "kline_records"
    if isinstance(obj.get("kline_records"), list):
        return obj, "kline_records"
    if isinstance(data.get("klines"), list):
        data["kline_records"] = _normalize_records(data["klines"])
        return data, "kline_records"
    data["kline_records"] = []
    return data, "kline_records"


def _merge_records(obj: dict, new_records) -> None:
    container, key = _records_container(obj)
    by_date = {}
    for record in _normalize_records(container.get(key)) + _normalize_records(new_records):
        date = str(record.get("date") or "").strip()
        if not date:
            continue
        record["date"] = date
        by_date[date] = record
    container[key] = [by_date[date] for date in sorted(by_date)]


def _load(path: Path):
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not text:
        return None
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        try:
            obj = json.loads(re.sub(r",\s*([}\]])", r"\1", text))
        except json.JSONDecodeError:
            return None
    return obj if isinstance(obj, dict) else None


def _write(path: Path, obj: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:
        _log.warning("写入行情缓存失败 %s: %s", path, exc)


def _quote_from_records(records: list, code: str, name: str = ""):
    if not records:
        return None
    last = records[-1]
    return {
        "code": last.get("code") or code,
        "name": name or last.get("name") or "",
        "latest": last.get("close"),
        "high": last.get("high"),
        "low": last.get("low"),
        "open": last.get("open"),
        "prev_close": None,
        "change": last.get("change"),
        "pct_change": last.get("pct_change"),
        "volume": last.get("volume"),
        "amount": last.get("amount"),
        "date": last.get("date"),
        "timestamp": last.get("date"),
        "source": "cache",
    }


def read_quote(code: str):
    obj = _load(cache_path(code))
    if not obj:
        return None
    quote = obj.get("quote")
    if isinstance(quote, dict) and quote:
        return dict(quote, source="cache")
    data = obj.get("data")
    name = data.get("name") if isinstance(data, dict) else ""
    return _quote_from_records(_read_records(obj), code, name)


def read_history(code, start, end, period, adjust):
    obj = _load(cache_path(code))
    if not obj:
        return None

    history = obj.get("history")
    if isinstance(history, dict):
        entry = history.get(history_key(period, adjust, start, end))
        if isinstance(entry, dict) and entry:
            return dict(entry, source="cache")

    if int(period) == 101 and int(adjust) == 1:
        records = [r for r in _read_records(obj)
                   if start <= str(r.get("date") or "").replace("-", "") <= end]
        if records:
            data = obj.get("data")
            return {
                "code": (data.get("code") if isinstance(data, dict) else None) or code,
                "name": (data.get("name") if isinstance(data, dict) else None) or "",
                "start": start,
                "end": end,
                "period": int(period),
                "adjust": int(adjust),
                "count": len(records),
                "records": records,
                "source": "cache",
            }
    return None


def load_file(path) -> dict:
    obj = _load(Path(path))
    return obj if isinstance(obj, dict) else {}


def read_records(code: str):
    obj = _load(cache_path(code))
    if not obj:
        return None
    data = obj.get("data")
    if not isinstance(data, dict):
        return None
    return {
        "code": data.get("code") or code,
        "name": data.get("name") or "",
        "source": data.get("source") or "",
        "kline_title": data.get("kline_title") or list(KLINE_TITLE),
        "records": _read_records(obj),
    }


def _dash_date(value) -> str:
    text = str(value or "").strip()
    if len(text) == 8 and text.isdigit():
        return text[:4] + "-" + text[4:6] + "-" + text[6:]
    return text


def write_query_range(code: str, start, end) -> None:
    path = cache_path(code)
    obj = _load(path) or {}
    data = obj.get("data")
    if not isinstance(data, dict):
        data = {}
        obj["data"] = data
    data["query_begin_time"] = _dash_date(start)
    data["query_end_time"] = _dash_date(end)
    _write(path, obj)


def get_value(code: str, key: str):
    obj = _load(cache_path(code))
    return obj.get(key) if obj else None


def set_value(code: str, key: str, value) -> None:
    path = cache_path(code)
    obj = _load(path) or {}
    obj[key] = value
    _write(path, obj)


def write_quote(code: str, quote: dict) -> None:
    path = cache_path(code)
    obj = _load(path) or {}
    obj["quote"] = quote
    _write(path, obj)


def write_history(code: str, result: dict) -> None:
    path = cache_path(code)
    obj = _load(path) or {}
    if int(result["period"]) == 101 and int(result["adjust"]) == 1:
        _merge_records(obj, result.get("records"))
        data = obj.get("data")
        if isinstance(data, dict):
            data.setdefault("code", result.get("code") or code)
            data.setdefault("name", result.get("name") or "")
            data.setdefault("kline_title", list(KLINE_TITLE))
            data.setdefault("query_begin_time", _dash_date(result.get("start")))
            data.setdefault("query_end_time", _dash_date(result.get("end")))
            data["source"] = result.get("source") or "eastmoney"
    else:
        history = obj.get("history")
        if not isinstance(history, dict):
            history = {}
        history[history_key(result["period"], result["adjust"],
                            result["start"], result["end"])] = result
        obj["history"] = history
    _write(path, obj)
