"""基于本地日线缓存生成周线/月线/年线。"""

from __future__ import annotations

from datetime import datetime

from . import cache

PERIODS = frozenset({"day", "week", "month", "year"})


def _number(value, cast=float):
    if value is None or value == "-" or value == "":
        return None
    try:
        return cast(value)
    except (TypeError, ValueError):
        return None


def _period_key(date_text: str, period: str) -> str:
    day = date_text[:10]
    dt = datetime.strptime(day, "%Y-%m-%d")
    if period == "week":
        iso = dt.isocalendar()
        return f"{iso.year}-W{iso.week:02d}"
    if period == "month":
        return day[:7]
    return day[:4]


def _first_trading_days(records: list) -> set:
    first = {}
    for record in records:
        day = str(record.get("date") or "")
        if len(day) < 10:
            continue
        month = day[:7]
        if month not in first or day < first[month]:
            first[month] = day
    return set(first.values())


def _moving_averages(records: list, windows=(30, 60)) -> dict:
    """基于日线收盘价计算均线，返回 {窗口: {日期: 均线值}}。"""
    ordered = sorted(records, key=lambda r: str(r.get("date") or ""))
    closes = []
    for record in ordered:
        close = _number(record.get("close"))
        if close is not None:
            closes.append((record.get("date"), close))

    result = {}
    for window in windows:
        values = {}
        total = 0.0
        for index, (day, close) in enumerate(closes):
            total += close
            if index >= window:
                total -= closes[index - window][1]
            if index >= window - 1:
                values[day] = round(total / window, 4)
        result[window] = values
    return result


def _aggregate_group(key: str, items: list) -> dict:
    ordered = sorted(items, key=lambda r: str(r.get("date") or ""))
    first, last = ordered[0], ordered[-1]
    open_price = _number(first.get("open"))
    close_price = _number(last.get("close"))
    highs = [_number(r.get("high")) for r in ordered]
    lows = [_number(r.get("low")) for r in ordered]
    high = max((v for v in highs if v is not None), default=None)
    low = min((v for v in lows if v is not None), default=None)

    change = (close_price - open_price
              if open_price is not None and close_price is not None else None)
    pct_change = (round(change / open_price * 100, 4)
                  if change is not None and open_price else None)
    amplitude = (round((high - low) / open_price * 100, 4)
                 if high is not None and low is not None and open_price else None)
    turnover = sum(_number(r.get("turnover_rate")) or 0 for r in ordered)

    return {
        "date": last.get("date"),
        "period_label": key,
        "open": open_price,
        "close": close_price,
        "high": high,
        "low": low,
        "volume": sum(_number(r.get("volume"), int) or 0 for r in ordered),
        "amount": round(sum(_number(r.get("amount")) or 0 for r in ordered), 2),
        "amplitude": amplitude,
        "pct_change": pct_change,
        "change": round(change, 4) if change is not None else None,
        "turnover_rate": round(turnover, 4),
        "trading_days": len(ordered),
    }


def aggregate(code: str, period: str = "day") -> dict:
    if period not in PERIODS:
        raise ValueError(f"不支持的周期: {period!r}，可选 {sorted(PERIODS)}")
    payload = cache.read_records(code)
    if payload is None:
        raise LookupError(f"本地无缓存数据: {code}")

    records = payload["records"]
    month_starts = _first_trading_days(records)
    if period == "day":
        rows = [dict(r) for r in records]
    else:
        groups = {}
        for record in records:
            date_text = str(record.get("date") or "")
            if len(date_text) < 10:
                continue
            try:
                key = _period_key(date_text, period)
            except ValueError:
                continue
            groups.setdefault(key, []).append(record)
        rows = []
        for key in sorted(groups):
            row = _aggregate_group(key, groups[key])
            row["month_start"] = any(
                item.get("date") in month_starts for item in groups[key]
            )
            rows.append(row)

    moving_averages = _moving_averages(records)
    for row in rows:
        day = row.get("date")
        row.setdefault("month_start", day in month_starts)
        row["month_label"] = str(day or "")[:7]
        row["ma30"] = moving_averages[30].get(day)
        row["ma60"] = moving_averages[60].get(day)

    rows.sort(key=lambda r: str(r.get("date") or ""), reverse=True)
    return {
        "code": payload["code"],
        "name": payload["name"],
        "source": payload["source"],
        "period": period,
        "kline_title": payload["kline_title"],
        "count": len(rows),
        "records": rows,
    }
