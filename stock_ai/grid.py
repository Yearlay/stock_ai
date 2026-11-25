"""网格交易模拟：基于本地日线缓存，按 开盘->最高->最低->收盘 触发。"""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path

from . import cache

SETTINGS_KEY = "grid_settings"


def _number(value, default=0.0):
    if value is None or value == "-" or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _date_text(value) -> str:
    text = str(value or "").strip()
    if len(text) == 8 and text.isdigit():
        return text[:4] + "-" + text[4:6] + "-" + text[6:]
    return text


def _day(date_text: str):
    try:
        return datetime.strptime(date_text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _default_base_price(records: list, start_text: str) -> float:
    for record in records:
        if str(record.get("date") or "") >= start_text:
            return _number(record.get("open"))
    return 0.0


def normalize_settings(settings: dict) -> dict:
    if not isinstance(settings, dict):
        raise ValueError("网格设置必须是 JSON 对象")
    code = str(settings.get("code") or "").strip()
    if not re.fullmatch(r"\d{6}", code):
        raise ValueError("网格标的必须为 6 位代码")
    start = _date_text(settings.get("start") or settings.get("start_date") or "")
    if not start:
        raise ValueError("开始网格日期不能为空")

    result = {
        "code": code,
        "start": start,
        "base_shares": int(settings.get("base_shares")),
        "grid_shares": int(settings.get("grid_shares")),
        "up_pct": _number(settings.get("up_pct")),
        "down_pct": _number(settings.get("down_pct")),
        "fee": max(0.0, _number(settings.get("fee"), 5.0)),
        "base_price": _number(settings.get("base_price")),
    }
    if result["base_shares"] <= 0 or result["grid_shares"] <= 0:
        raise ValueError("底仓份数和网格份额必须为正整数")
    if result["up_pct"] <= 0 or result["down_pct"] <= 0:
        raise ValueError("涨跌百分比必须为正数")
    if result["base_price"] <= 0:
        raise ValueError("基准价必须大于 0")
    return result


def save_settings(settings: dict) -> dict:
    payload = normalize_settings(settings)
    cache.set_value(payload["code"], SETTINGS_KEY, payload)
    return payload


def load_settings(code: str):
    value = cache.get_value(str(code or "").strip(), SETTINGS_KEY)
    return value if isinstance(value, dict) and value else None


def result_path(code: str) -> Path:
    code = str(code or "").strip()
    if not re.fullmatch(r"\d{6}", code):
        raise ValueError("网格标的必须为 6 位代码")
    return cache.DATA_DIR / "grid" / f"{code}_grid.json"


def save_result(result: dict) -> Path:
    path = result_path(result.get("code") if isinstance(result, dict) else None)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return path


def load_result(code: str):
    path = result_path(code)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def simulate(code: str, start_date: str, base_shares: int, grid_shares: int,
             up_pct: float, down_pct: float, fee: float = 5.0,
             base_price: float = None) -> dict:
    """模拟网格交易，直到持仓归零或日线数据遍历结束。"""
    payload = cache.read_records(code)
    if payload is None:
        raise LookupError(f"本地无缓存数据: {code}")
    records = sorted(payload["records"], key=lambda r: str(r.get("date") or ""))
    start_text = _date_text(start_date)
    if not start_text:
        raise ValueError("开始网格日期不能为空")

    base_shares = int(base_shares)
    grid_shares = int(grid_shares)
    if base_shares <= 0 or grid_shares <= 0:
        raise ValueError("底仓份数和网格份额必须为正整数")
    up_pct = _number(up_pct)
    down_pct = _number(down_pct)
    if up_pct <= 0 or down_pct <= 0:
        raise ValueError("涨跌百分比必须为正数")
    fee = max(0.0, _number(fee))
    baseline = _number(base_price) if base_price not in (None, "") else _default_base_price(records, start_text)
    if baseline <= 0:
        raise ValueError("基准价必须大于 0，或开始日期无对应开盘价")
    initial_base_price = baseline

    holdings = base_shares
    avg_cost = baseline
    initial_amount = base_shares * baseline
    cash = 0.0
    fee_total = 0.0
    max_holdings = base_shares
    max_holding_amount = base_shares * baseline
    last_price = baseline
    last_date = start_text
    trades = []

    for record in records:
        day = str(record.get("date") or "")
        if day < start_text:
            continue
        last_date = day
        prices = [
            _number(record.get("open"), None),
            _number(record.get("high"), None),
            _number(record.get("low"), None),
            _number(record.get("close"), None),
        ]
        for price in prices:
            if price is None or price <= 0:
                continue
            last_price = price
            if holdings <= 0:
                break
            sell_at = baseline * (1 + up_pct / 100)
            buy_at = baseline * (1 - down_pct / 100)
            if price >= sell_at:
                shares = min(grid_shares, holdings)
                cash += shares * price - fee
                fee_total += fee
                holdings -= shares
                baseline = price
                trades.append({
                    "date": day, "type": "卖出", "shares": shares,
                    "holdings": holdings,
                    "holding_cost": round(avg_cost, 4),
                    "profit": round(cash + holdings * price - initial_amount, 2),
                    "price": round(price, 4),
                })
            elif price <= buy_at:
                shares = grid_shares
                old_holdings = holdings
                avg_cost = (avg_cost * old_holdings + price * shares) / (old_holdings + shares)
                cash -= shares * price + fee
                fee_total += fee
                holdings += shares
                baseline = price
                trades.append({
                    "date": day, "type": "买入", "shares": shares,
                    "holdings": holdings,
                    "holding_cost": round(avg_cost, 4),
                    "profit": round(cash + holdings * price - initial_amount, 2),
                    "price": round(price, 4),
                })
            if holdings > max_holdings:
                max_holdings = holdings
                max_holding_amount = round(max_holdings * baseline, 2)
            if holdings <= 0:
                break
        if holdings <= 0:
            break

    start_day = _day(start_text)
    end_day = _day(last_date)
    period_days = (end_day - start_day).days if start_day and end_day and end_day >= start_day else 0
    final_profit = cash + holdings * last_price - initial_amount
    buy_count = sum(1 for trade in trades if trade["type"] == "买入")
    sell_count = sum(1 for trade in trades if trade["type"] == "卖出")
    if start_day and end_day and end_day >= start_day:
        month_span = ((end_day.year - start_day.year) * 12 +
                      (end_day.month - start_day.month) + 1)
    else:
        month_span = 1
    avg_trades_per_month = round(len(trades) / month_span, 2)

    return {
        "code": code,
        "name": payload["name"],
        "settings": {
            "start_date": start_text,
            "base_shares": base_shares,
            "grid_shares": grid_shares,
            "fee": fee,
            "base_price": round(initial_base_price, 4),
            "up_pct": up_pct,
            "down_pct": down_pct,
        },
        "trades": trades,
        "stats": {
            "initial_position": base_shares,
            "initial_amount": round(base_shares * initial_base_price, 2),
            "max_position": max_holdings,
            "max_position_amount": round(max_holding_amount, 2),
            "period_days": period_days,
            "fee_total": round(fee_total, 2),
            "final_profit": round(final_profit, 2),
            "current_cost": round(avg_cost, 4) if holdings > 0 else None,
            "end_date": last_date,
            "trade_count": len(trades),
            "buy_count": buy_count,
            "sell_count": sell_count,
            "avg_trades_per_month": avg_trades_per_month,
        },
    }
