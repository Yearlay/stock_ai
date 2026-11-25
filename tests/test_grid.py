import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from stock_ai import cache, grid

DAILY = [
    {"date": "2026-11-02", "open": 10.0, "high": 10.0, "low": 10.0, "close": 10.0,
     "volume": 100, "amount": 1000.0},
    {"date": "2026-11-03", "open": 11.0, "high": 11.0, "low": 11.0, "close": 11.0,
     "volume": 100, "amount": 1100.0},
    {"date": "2026-11-04", "open": 9.9, "high": 9.9, "low": 9.9, "close": 9.9,
     "volume": 100, "amount": 990.0},
]


class GridTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        patcher = patch.object(cache, "DATA_DIR", Path(tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)
        cache._write(cache.cache_path("510300"), {
            "data": {
                "code": "510300", "name": "沪深300ETF", "source": "eastmoney",
                "kline_title": list(cache.KLINE_TITLE), "kline_records": DAILY,
            },
        })

    def test_simulate_sells_until_empty(self):
        result = grid.simulate(
            "510300", "2026-11-02", base_shares=50, grid_shares=50,
            up_pct=10, down_pct=10, fee=1, base_price=10,
        )
        self.assertEqual(result["name"], "沪深300ETF")
        self.assertEqual(len(result["trades"]), 1)
        trade = result["trades"][0]
        self.assertEqual(trade["date"], "2026-11-03")
        self.assertEqual(trade["type"], "卖出")
        self.assertEqual(trade["shares"], 50)
        self.assertEqual(trade["holdings"], 0)
        self.assertEqual(trade["profit"], 49.0)
        stats = result["stats"]
        self.assertEqual(stats["initial_position"], 50)
        self.assertEqual(stats["initial_amount"], 500.0)
        self.assertEqual(stats["max_position"], 50)
        self.assertEqual(stats["fee_total"], 1.0)
        self.assertEqual(stats["final_profit"], 49.0)
        self.assertEqual(stats["period_days"], 1)
        self.assertEqual(stats["trade_count"], 1)
        self.assertEqual(stats["buy_count"], 0)
        self.assertEqual(stats["sell_count"], 1)
        self.assertEqual(stats["avg_trades_per_month"], 1.0)
        self.assertIsNone(stats["current_cost"])

    def test_trade_profit_uses_portfolio_value(self):
        result = grid.simulate(
            "510300", "2026-11-02", base_shares=100, grid_shares=50,
            up_pct=10, down_pct=10, fee=1, base_price=10,
        )
        trades = result["trades"]
        self.assertEqual([trade["type"] for trade in trades], ["卖出", "买入"])
        self.assertEqual(trades[0]["price"], 11.0)
        self.assertEqual(trades[0]["profit"], 99.0)
        self.assertEqual(trades[0]["holding_cost"], 10.0)
        self.assertEqual(trades[1]["profit"], 43.0)
        self.assertEqual(trades[1]["holding_cost"], 9.95)
        self.assertEqual(result["stats"]["final_profit"], 43.0)

    def test_current_cost_when_position_remains(self):
        result = grid.simulate(
            "510300", "2026-11-02", base_shares=50, grid_shares=50,
            up_pct=50, down_pct=50, fee=1, base_price=10,
        )
        self.assertEqual(result["trades"], [])
        self.assertEqual(result["stats"]["current_cost"], 10.0)
        self.assertEqual(result["stats"]["trade_count"], 0)
        self.assertEqual(result["stats"]["buy_count"], 0)
        self.assertEqual(result["stats"]["sell_count"], 0)
        self.assertEqual(result["stats"]["avg_trades_per_month"], 0.0)

    def test_default_base_price_from_start_date(self):
        result = grid.simulate(
            "510300", "2026-11-02", base_shares=50, grid_shares=50,
            up_pct=10, down_pct=10, fee=1,
        )
        self.assertEqual(result["settings"]["base_price"], 10.0)

    def test_save_and_load_settings(self):
        settings = {
            "code": "510300", "start": "2026-11-02", "base_shares": 50,
            "grid_shares": 50, "up_pct": 10, "down_pct": 10,
            "fee": 1, "base_price": 10,
        }
        saved = grid.save_settings(settings)
        self.assertEqual(saved, settings)
        self.assertEqual(grid.load_settings("510300"), settings)
        stored = cache._load(cache.cache_path("510300"))
        self.assertEqual(stored["grid_settings"], settings)
        self.assertEqual(len(stored["data"]["kline_records"]), 3)
        with self.assertRaises(ValueError):
            grid.save_settings({"code": "abc", "start": "2026-11-02"})

    def test_save_and_load_result(self):
        result = {
            "code": "510300",
            "trades": [{"date": "2026-11-03", "type": "卖出"}],
            "stats": {"trade_count": 1},
        }
        path = grid.save_result(result)
        self.assertEqual(path, cache.DATA_DIR / "grid" / "510300_grid.json")
        self.assertTrue(path.is_file())
        self.assertEqual(grid.load_result("510300"), result)
        self.assertIsNone(grid.load_result("999999"))
        with self.assertRaises(ValueError):
            grid.result_path("abc")

    def test_invalid_params(self):
        with self.assertRaises(ValueError):
            grid.simulate("510300", "", 50, 50, 10, 10)
        with self.assertRaises(ValueError):
            grid.simulate("510300", "2026-11-02", 0, 50, 10, 10)
        with self.assertRaises(ValueError):
            grid.simulate("510300", "2026-11-02", 50, 50, 0, 10)
        with self.assertRaises(LookupError):
            grid.simulate("999999", "2026-11-02", 50, 50, 10, 10)


if __name__ == "__main__":
    unittest.main()
