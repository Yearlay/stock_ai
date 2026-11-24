import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from stock_ai import aggregate, cache

DAILY = [
    {"date": "2025-12-31", "open": 10.0, "close": 11.0, "high": 12.0, "low": 9.5,
     "volume": 100, "amount": 1050.0, "amplitude": 25.0, "pct_change": 10.0,
     "change": 1.0, "turnover_rate": 1.0},
    {"date": "2026-01-02", "open": 11.0, "close": 12.0, "high": 13.0, "low": 10.5,
     "volume": 200, "amount": 2300.0, "amplitude": 22.7, "pct_change": 9.1,
     "change": 1.0, "turnover_rate": 2.0},
    {"date": "2026-01-05", "open": 12.0, "close": 13.0, "high": 14.0, "low": 11.5,
     "volume": 300, "amount": 3750.0, "amplitude": 20.8, "pct_change": 8.3,
     "change": 1.0, "turnover_rate": 3.0},
    {"date": "2026-01-09", "open": 13.0, "close": 14.0, "high": 15.0, "low": 12.5,
     "volume": 400, "amount": 5400.0, "amplitude": 19.2, "pct_change": 7.7,
     "change": 1.0, "turnover_rate": 4.0},
    {"date": "2026-02-03", "open": 14.0, "close": 15.0, "high": 16.0, "low": 13.5,
     "volume": 500, "amount": 7250.0, "amplitude": 17.9, "pct_change": 7.1,
     "change": 1.0, "turnover_rate": 5.0},
]


class AggregateTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        patcher = patch.object(cache, "DATA_DIR", Path(tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)
        cache._write(cache.cache_path("600519"), {
            "data": {
                "code": "600519",
                "name": "贵州茅台",
                "source": "eastmoney",
                "kline_title": list(cache.KLINE_TITLE),
                "kline_records": DAILY,
            },
        })

    def test_day_is_descending(self):
        result = aggregate.aggregate("600519", "day")
        self.assertEqual(result["period"], "day")
        self.assertEqual(result["count"], 5)
        self.assertEqual(result["records"][0]["date"], "2026-02-03")
        self.assertEqual(result["records"][-1]["date"], "2025-12-31")

    def test_week_groups_by_iso_week(self):
        result = aggregate.aggregate("600519", "week")
        self.assertEqual(result["count"], 3)
        first = result["records"][0]
        self.assertEqual(first["date"], "2026-02-03")
        self.assertEqual(first["period_label"], "2026-W06")
        self.assertEqual(first["open"], 14.0)
        self.assertEqual(first["close"], 15.0)
        self.assertEqual(first["volume"], 500)
        self.assertEqual(first["trading_days"], 1)
        second = result["records"][1]
        self.assertEqual(second["date"], "2026-01-09")
        self.assertEqual(second["period_label"], "2026-W02")
        self.assertEqual(second["open"], 12.0)
        self.assertEqual(second["close"], 14.0)
        self.assertEqual(second["volume"], 700)
        self.assertEqual(second["trading_days"], 2)

    def test_month_groups_by_month(self):
        result = aggregate.aggregate("600519", "month")
        self.assertEqual(result["count"], 3)
        first = result["records"][0]
        self.assertEqual(first["date"], "2026-02-03")
        self.assertEqual(first["period_label"], "2026-02")
        january = result["records"][1]
        self.assertEqual(january["period_label"], "2026-01")
        self.assertEqual(january["open"], 11.0)
        self.assertEqual(january["close"], 14.0)
        self.assertEqual(january["high"], 15.0)
        self.assertEqual(january["low"], 10.5)
        self.assertEqual(january["volume"], 900)
        self.assertEqual(january["trading_days"], 3)

    def test_year_groups_by_year(self):
        result = aggregate.aggregate("600519", "year")
        self.assertEqual(result["count"], 2)
        first = result["records"][0]
        self.assertEqual(first["date"], "2026-02-03")
        self.assertEqual(first["period_label"], "2026")
        self.assertEqual(first["open"], 11.0)
        self.assertEqual(first["close"], 15.0)
        self.assertEqual(first["volume"], 1400)

    def test_moving_averages_from_daily(self):
        start = date(2026, 1, 1)
        records = []
        for index in range(70):
            day = (start + timedelta(days=index)).isoformat()
            close = float(index + 1)
            records.append({
                "date": day, "open": close, "close": close,
                "high": close + 1, "low": close - 1,
                "volume": 100, "amount": 1000.0, "amplitude": 1.0,
                "pct_change": 1.0, "change": 1.0, "turnover_rate": 1.0,
            })
        cache._write(cache.cache_path("600519"), {
            "data": {
                "code": "600519", "name": "贵州茅台", "source": "eastmoney",
                "kline_title": list(cache.KLINE_TITLE), "kline_records": records,
            },
        })

        day = aggregate.aggregate("600519", "day")
        latest = day["records"][0]
        self.assertEqual(latest["date"], "2026-03-11")
        self.assertEqual(latest["ma30"], 55.5)
        self.assertEqual(latest["ma60"], 40.5)
        self.assertIsNone(day["records"][-1]["ma30"])
        self.assertEqual(day["records"][40]["ma30"], 15.5)

        week = aggregate.aggregate("600519", "week")
        self.assertEqual(week["records"][0]["ma30"], 55.5)
        self.assertEqual(week["records"][0]["ma60"], 40.5)

    def test_month_start_markers(self):
        start = date(2026, 1, 1)
        records = []
        for index in range(70):
            day = (start + timedelta(days=index)).isoformat()
            records.append({"date": day, "close": 10.0 + index})
        cache._write(cache.cache_path("600519"), {
            "data": {
                "code": "600519", "name": "贵州茅台", "source": "eastmoney",
                "kline_title": list(cache.KLINE_TITLE), "kline_records": records,
            },
        })

        day = aggregate.aggregate("600519", "day")
        marked = sorted(r["date"] for r in day["records"] if r["month_start"])
        self.assertEqual(marked, ["2026-01-01", "2026-02-01", "2026-03-01"])
        self.assertEqual(day["records"][-1]["month_label"], "2026-01")

        week = aggregate.aggregate("600519", "week")
        self.assertTrue(any(r["month_start"] for r in week["records"]))

    def test_invalid_period_and_missing_cache(self):
        with self.assertRaises(ValueError):
            aggregate.aggregate("600519", "minute")
        with self.assertRaises(LookupError):
            aggregate.aggregate("000001", "day")


if __name__ == "__main__":
    unittest.main()
