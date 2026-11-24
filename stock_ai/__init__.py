"""stock_ai: 基于东方财富的单只股票/ETF 行情查询。"""

from .eastmoney import get_history, get_quote, get_stock_data

__all__ = ["get_quote", "get_history", "get_stock_data"]
__version__ = "0.1.0"
