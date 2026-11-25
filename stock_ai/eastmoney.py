"""东方财富行情数据客户端，仅使用 Python 标准库。

优先读取本地缓存，未命中时抓取东方财富并回写缓存。
"""

from __future__ import annotations

import json
import re
import time
from datetime import date, datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from . import cache
from .cache import parse_klines

QUOTE_URL = "https://push2.eastmoney.com/api/qt/stock/get"
KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"

_REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://quote.eastmoney.com/",
    "Connection": "close",
}
_REQUEST_ATTEMPTS = 3
_RETRY_BASE_DELAY = 0.5
_CODE_RE = re.compile(r"^\d{6}$")
_DATE_RE = re.compile(r"^\d{8}$")
_VALID_PERIODS = frozenset({1, 5, 15, 30, 60, 101, 102, 103})
_SH_PREFIXES = frozenset("569")
_SZ_PREFIXES = frozenset("0123")
_BJ_PREFIXES = frozenset("48")
_CST = timezone(timedelta(hours=8))


class QuoteError(RuntimeError):
    """东方财富接口返回异常或网络请求失败。"""


def validate_code(code: str) -> str:
    code = str(code).strip()
    if not _CODE_RE.fullmatch(code):
        raise ValueError(f"股票代码必须为 6 位数字: {code!r}")
    return code


def to_secid(code: str) -> str:
    code = validate_code(code)
    if code[0] in _SH_PREFIXES:
        market = "1"
    elif code[0] in _SZ_PREFIXES or code[0] in _BJ_PREFIXES:
        market = "0"
    else:
        raise ValueError(f"无法识别股票代码的市场: {code!r}")
    return f"{market}.{code}"


def _normalize_date(value, field: str) -> str:
    if value is None or value == "":
        raise ValueError(f"{field} 不能为空")
    if isinstance(value, date):
        return value.strftime("%Y%m%d")
    text = str(value).strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        text = text.replace("-", "")
    if not _DATE_RE.fullmatch(text):
        raise ValueError(f"{field} 格式应为 YYYYMMDD 或 YYYY-MM-DD: {value!r}")
    try:
        datetime.strptime(text, "%Y%m%d")
    except ValueError as exc:
        raise ValueError(f"{field} 不是有效日期: {value!r}") from exc
    return text


def _request_json(url: str, params: dict) -> dict:
    query = urlencode(params)
    last_exc = None
    for attempt in range(_REQUEST_ATTEMPTS):
        request = Request(f"{url}?{query}", headers=_REQUEST_HEADERS)
        try:
            with urlopen(request, timeout=10) as response:
                text = response.read().decode("utf-8", errors="replace")
            break
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            last_exc = exc
            if attempt + 1 < _REQUEST_ATTEMPTS:
                time.sleep(_RETRY_BASE_DELAY * (2 ** attempt))
    else:
        raise QuoteError(
            f"请求东方财富接口失败（已重试 {_REQUEST_ATTEMPTS} 次）: {last_exc}"
        ) from last_exc

    stripped = text.strip()
    if not stripped.startswith(("{", "[")):
        left = stripped.find("(")
        right = stripped.rfind(")")
        if left == -1 or right == -1 or right < left:
            raise QuoteError(f"东方财富接口返回非 JSON 内容: {stripped[:120]}")
        stripped = stripped[left + 1:right].strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise QuoteError(f"东方财富接口返回 JSON 解析失败: {exc}") from exc


def _to_number(value, cast=float):
    if value is None or value == "-" or value == "":
        return None
    try:
        return cast(value)
    except (TypeError, ValueError):
        return None


def _scaled(value, digits: int):
    number = _to_number(value)
    if number is None:
        return None
    return round(number / (10 ** digits), digits)


def _timestamp(value):
    seconds = _to_number(value, int)
    if seconds is None:
        return None
    return datetime.fromtimestamp(seconds, tz=_CST).isoformat()


def get_quote(code: str) -> dict:
    """获取当日行情：优先本地缓存，未命中时抓取东方财富并回写缓存。"""
    code = validate_code(code)
    cached = cache.read_quote(code)
    if cached is not None:
        return cached
    result = _fetch_quote(code)
    cache.write_quote(code, result)
    return result


def _fetch_quote(code: str) -> dict:
    security = to_secid(code)
    payload = _request_json(QUOTE_URL, {
        "invt": 2,
        "fltt": 1,
        "fields": "f43,f44,f45,f46,f47,f48,f57,f58,f59,f60,f86,f169,f170",
        "secid": security,
    })
    if payload.get("rc") not in (0, None):
        raise QuoteError(f"东方财富返回错误: rc={payload.get('rc')}")
    data = payload.get("data")
    if not data:
        raise QuoteError(f"未找到行情数据: {code}")

    digits = _to_number(data.get("f59"), int)
    if digits is None or not 0 <= digits <= 6:
        digits = 2
    return {
        "code": data.get("f57") or validate_code(code),
        "name": data.get("f58") or "",
        "latest": _scaled(data.get("f43"), digits),
        "high": _scaled(data.get("f44"), digits),
        "low": _scaled(data.get("f45"), digits),
        "open": _scaled(data.get("f46"), digits),
        "prev_close": _scaled(data.get("f60"), digits),
        "change": _scaled(data.get("f169"), digits),
        "pct_change": _scaled(data.get("f170"), digits),
        "volume": _to_number(data.get("f47"), int),
        "amount": _to_number(data.get("f48")),
        "timestamp": _timestamp(data.get("f86")),
        "source": "eastmoney",
    }


def _normalize_history_options(code, start, end, period, adjust):
    security = to_secid(code)
    try:
        klt = int(period)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"period 必须是整数: {period!r}") from exc
    if klt not in _VALID_PERIODS:
        raise ValueError(f"不支持的 period: {period!r}，可选 {sorted(_VALID_PERIODS)}")
    try:
        fqt = int(adjust)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"adjust 必须是 0/1/2: {adjust!r}") from exc
    if fqt not in (0, 1, 2):
        raise ValueError(f"adjust 必须是 0/1/2: {adjust!r}")

    start_text = _normalize_date(start, "start") if start not in (None, "") else "19900101"
    end_text = (_normalize_date(end, "end") if end not in (None, "")
                else datetime.now(_CST).strftime("%Y%m%d"))
    if start_text > end_text:
        raise ValueError("start 不能晚于 end")
    return security, klt, fqt, start_text, end_text


def get_history(code, start=None, end=None, period=101, adjust=1,
                force=False, save_range=False) -> dict:
    """获取时间范围内的 K 线：默认优先缓存，force=True 时强制抓取并回写。

    save_range=True 时把当前查询范围写入缓存的 data.query_begin_time/query_end_time。
    period: 1/5/15/30/60 分钟，101 日，102 周，103 月。
    adjust: 0 不复权，1 前复权（默认），2 后复权。
    """
    security, klt, fqt, start_text, end_text = _normalize_history_options(
        code, start, end, period, adjust
    )
    if save_range:
        cache.write_query_range(code, start_text, end_text)
    if not force:
        cached = cache.read_history(code, start_text, end_text, klt, fqt)
        if cached is not None:
            return cached
    result = _fetch_history(security, code, klt, fqt, start_text, end_text)
    cache.write_history(code, result)
    return result


def _fetch_history(security, code, klt, fqt, start_text, end_text) -> dict:
    payload = _request_json(KLINE_URL, {
        "secid": security,
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "klt": klt,
        "fqt": fqt,
        "beg": start_text,
        "end": end_text,
        "lmt": 1000000,
    })
    if payload.get("rc") not in (0, None):
        raise QuoteError(f"东方财富返回错误: rc={payload.get('rc')}")
    data = payload.get("data") or {}
    records = parse_klines(data.get("klines"))

    return {
        "code": data.get("code") or validate_code(code),
        "name": data.get("name") or "",
        "start": start_text,
        "end": end_text,
        "period": klt,
        "adjust": fqt,
        "count": len(records),
        "records": records,
        "source": "eastmoney",
    }


def get_stock_data(code, start=None, end=None, period=101, adjust=1) -> dict:
    """统一入口：无时间范围返回当日行情，有则返回历史 K 线。"""
    if start not in (None, "") or end not in (None, ""):
        return get_history(code, start, end, period, adjust)
    return get_quote(code)
