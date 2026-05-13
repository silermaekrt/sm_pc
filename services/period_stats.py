# -*- coding: utf-8 -*-
"""
services/period_stats.py - 区间统计分析服务

提供基于基准指数日线文件的区间收益率、区间回撤计算。
基准数据源路径通过 config.app.BASE_INDEX_DIR 配置：
  - 默认: base/{yyyy}/{m}/{d}/QT_INDEXQUOTE.txt（相对路径）
  - 可配置为绝对路径如: /data/v1/raw/JY/IndexQuote/{yyyy}/{m}/{d}/QT_INDEXQUOTE.txt

与 routes/fund.py 中的 /fund/period-stats 端点配合使用。
"""

import os
from datetime import datetime

import pandas as pd

import config
from services.metrics import compute_drawdown_from_start, compute_max_drawdown_from_prices


# ---------------------------------------------------------
# 基准指数名称 → base/ QT_INDEXQUOTE.txt 中的 SECU_CODE 映射
# ---------------------------------------------------------

BENCHMARK_CODE_MAP = {
    "沪深300":  "H00300.CSI",
    "中证500":  "H00905.CSI",
    "中证1000": "H00852.CSI",
    "中证800":  "H00906.CSI",
    "上证50":   "H00016.CSI",
}


def get_benchmark_available_dates(code: str) -> tuple[str | None, str | None]:
    """
    获取指定基准指数代码在 base/ 目录中可用的日期范围。

    Returns:
        (min_date, max_date) - 最早和最晚可用日期（YYYY-MM-DD 格式），都可能是 None
    """
    base_dir = _get_base_index_root()
    if not os.path.isdir(base_dir):
        return None, None

    available_dates = []
    for year_dir in os.scandir(base_dir):
        if not year_dir.is_dir():
            continue
        if not year_dir.name.isdigit():
            continue
        year = year_dir.name
        for month_dir in os.scandir(year_dir.path):
            if not month_dir.is_dir():
                continue
            if not month_dir.name.isdigit():
                continue
            month = month_dir.name
            for day_dir in os.scandir(month_dir.path):
                if not day_dir.is_dir():
                    continue
                if not day_dir.name.isdigit():
                    continue
                day = day_dir.name
                file_path = os.path.join(day_dir.path, "QT_INDEXQUOTE.txt")
                if os.path.exists(file_path):
                    try:
                        date_str = f"{year}-{int(month):02d}-{int(day):02d}"
                        available_dates.append(date_str)
                    except ValueError:
                        continue

    if not available_dates:
        return None, None

    available_dates.sort()
    return available_dates[0], available_dates[-1]


def _find_latest_available_date(code: str, target_date: str) -> str | None:
    """
    找到基准数据中不超过 target_date 的最近可用日期。

    Returns:
        YYYY-MM-DD 格式的日期字符串，或 None（如果所有日期都晚于 target）
    """
    base_dir = _get_base_index_root()
    if not os.path.isdir(base_dir):
        return None

    available = []
    for year_dir in os.scandir(base_dir):
        if not year_dir.is_dir() or not year_dir.name.isdigit():
            continue
        year = year_dir.name
        for month_dir in os.scandir(year_dir.path):
            if not month_dir.is_dir() or not month_dir.name.isdigit():
                continue
            month = month_dir.name
            for day_dir in os.scandir(month_dir.path):
                if not day_dir.is_dir() or not day_dir.name.isdigit():
                    continue
                day = day_dir.name
                file_path = os.path.join(day_dir.path, "QT_INDEXQUOTE.txt")
                if os.path.exists(file_path):
                    try:
                        date_str = f"{year}-{int(month):02d}-{int(day):02d}"
                        target_dt = datetime.strptime(target_date, "%Y-%m-%d")
                        date_dt = datetime.strptime(date_str, "%Y-%m-%d")
                        if date_dt <= target_dt:
                            available.append(date_str)
                    except ValueError:
                        continue

    if not available:
        return None
    available.sort()
    return available[-1]


def _get_base_index_root() -> str:
    """
    获取基准指数文件的根目录。
    - 如果 BASE_INDEX_DIR 是绝对路径，直接返回
    - 否则相对于 BASE_DIR 返回
    """
    base_path = config.BASE_INDEX_DIR
    if os.path.isabs(base_path):
        return base_path
    return os.path.join(str(config.BASE_DIR), base_path)


def _base_quote_path(yyyy: int, m: int, d: int) -> str:
    """返回指定日期的 QT_INDEXQUOTE.txt 文件路径。"""
    root = _get_base_index_root()
    return os.path.join(root, str(yyyy), str(m), str(d), "QT_INDEXQUOTE.txt")


def read_base_quote(yyyy: int, m: int, d: int, secu_code: str) -> float | None:
    """
    从 base/{yyyy}/{m}/{d}/QT_INDEXQUOTE.txt 读取指定指数的收盘价。

    Args:
        yyyy, m, d: 日期（年、月、日，整数）
        secu_code:  证券代码，如 "000300.SH"

    Returns:
        收盘价（浮点），找不到或解析失败返回 None
    """
    path = _base_quote_path(yyyy, m, d)
    if not os.path.exists(path):
        return None

    try:
        df = pd.read_csv(
            path,
            sep="|",
            dtype=str,
            keep_default_na=False,
            encoding="utf-8-sig",
        )
    except Exception:
        return None

    if "SECU_CODE" not in df.columns or "CLOSEPRICE" not in df.columns:
        return None

    row = df[df["SECU_CODE"] == secu_code]
    if row.empty:
        return None

    raw = row.iloc[0]["CLOSEPRICE"]
    try:
        val = float(raw)
    except (ValueError, TypeError):
        return None
    return val


def _parse_date(date_str: str) -> tuple[int, int, int] | None:
    """
    将 YYYY-MM-DD 格式的日期字符串解析为 (yyyy, m, d) 元组。
    失败返回 None。
    """
    try:
        dt = datetime.strptime(date_str.strip(), "%Y-%m-%d")
        return dt.year, dt.month, dt.day
    except (ValueError, TypeError):
        return None


def _date_range(start_date: str, end_date: str) -> list[str]:
    """
    返回 start_date 到 end_date（inclusive）之间的所有日期字符串 YYYY-MM-DD。
    用于遍历 base/ 目录中存在的文件。
    """
    try:
        start = datetime.strptime(start_date.strip(), "%Y-%m-%d")
        end = datetime.strptime(end_date.strip(), "%Y-%m-%d")
    except (ValueError, TypeError):
        return []

    dates = []
    current = start
    while current <= end:
        dates.append(current.strftime("%Y-%m-%d"))
        current = datetime(current.year, current.month, current.day) + \
            __import__("datetime").timedelta(days=1)
    return dates


def compute_benchmark_interval_return(
    benchmark_name: str,
    start_date: str,
    end_date: str,
    auto_fallback: bool = True,
) -> dict:
    """
    计算基准指数在指定区间的收益率。

    Args:
        benchmark_name: 基准指数中文名称，如 "沪深300"
        start_date:     区间起始日期，YYYY-MM-DD
        end_date:       区间结束日期，YYYY-MM-DD
        auto_fallback:   是否自动回退到基准数据可用范围（默认 True）

    Returns:
        {
            "name":           str,
            "code":           str,
            "close_start":    float,
            "close_end":      float,
            "interval_return": float,   # 原始小数（如 0.0048）
            "interval_return_pct": float,  # 百分比（如 0.48）
            "success":        bool,
            "error":          str,
            "date_adjusted":  bool,     # 是否进行了日期修正
            "original_end":   str,      # 原始请求的结束日期
            "adjusted_end":   str,      # 实际使用的结束日期
        }
    """
    result = {
        "name": benchmark_name,
        "code": None,
        "close_start": None,
        "close_end": None,
        "interval_return": None,
        "interval_return_pct": None,
        "success": False,
        "error": "",
        "date_adjusted": False,
        "original_end": end_date,
        "adjusted_end": end_date,
    }

    code = BENCHMARK_CODE_MAP.get(benchmark_name.strip())
    if not code:
        result["error"] = f"未知基准指数名称：{benchmark_name}"
        return result
    result["code"] = code

    start_parsed = _parse_date(start_date)
    end_parsed = _parse_date(end_date)
    if not start_parsed or not end_parsed:
        result["error"] = "日期格式错误，需要 YYYY-MM-DD"
        return result

    adjusted_end = end_date

    close_start = read_base_quote(*start_parsed, code)
    if close_start is None:
        if auto_fallback:
            latest_for_start = _find_latest_available_date(code, start_date)
            if latest_for_start:
                parsed = _parse_date(latest_for_start)
                if parsed:
                    close_start = read_base_quote(*parsed, code)
                    if close_start is not None:
                        adjusted_end = latest_for_start
                        result["date_adjusted"] = True
        if close_start is None:
            result["error"] = f"找不到基准指数 {code} 在 {start_date} 的数据"
            return result

    close_end = read_base_quote(*end_parsed, code)
    if close_end is None:
        if auto_fallback:
            latest_for_end = _find_latest_available_date(code, end_date)
            if latest_for_end:
                parsed = _parse_date(latest_for_end)
                if parsed:
                    close_end = read_base_quote(*parsed, code)
                    if close_end is not None:
                        adjusted_end = latest_for_end
                        result["date_adjusted"] = True
        if close_end is None:
            result["error"] = f"找不到基准指数 {code} 在 {end_date} 的数据"
            return result

    result["adjusted_end"] = adjusted_end

    if close_start == 0:
        result["error"] = f"基准指数 {code} 在 {start_date} 的收盘价为 0"
        return result

    interval_return = (close_end - close_start) / close_start
    result["close_start"] = close_start
    result["close_end"] = close_end
    result["interval_return"] = interval_return
    result["interval_return_pct"] = interval_return * 100
    result["success"] = True
    return result

def compute_benchmark_drawdown(
    benchmark_name: str,
    start_date: str,
    end_date: str,
    auto_fallback: bool = True,
) -> dict:
    """
    计算基准指数在指定区间的动态回撤序列和最大回撤。

    回撤算法（从起点开始的动态回撤）：
        - drawdown_series: 从区间起点开始的回撤（适合绘图，第一条=0）
        - max_drawdown: 从任意高点到后续最低点的最大回撤

    Args:
        benchmark_name: 基准指数中文名称，如 "沪深300"
        start_date:     区间起始日期，YYYY-MM-DD
        end_date:       区间结束日期，YYYY-MM-DD
        auto_fallback:  是否自动回退到基准数据可用范围（默认 True）

    Returns:
        {
            "name":       str,
            "code":       str,
            "dd_series":  [{"date": "2026-05-06", "close": 4877.0932, "drawdown": 0.0}, ...],
            "max_drawdown": float,      # 原始小数（负值，如 -0.0123）
            "max_drawdown_pct": float,  # 百分比（如 -1.23）
            "success":    bool,
            "error":      str,
            "date_adjusted": bool,      # 是否进行了日期修正
            "original_end": str,         # 原始请求的结束日期
            "adjusted_end": str,         # 实际使用的结束日期
        }
    """
    result = {
        "name": benchmark_name,
        "code": None,
        "dd_series": [],
        "max_drawdown": 0.0,
        "max_drawdown_pct": 0.0,
        "success": False,
        "error": "",
        "date_adjusted": False,
        "original_end": end_date,
        "adjusted_end": end_date,
    }

    code = BENCHMARK_CODE_MAP.get(benchmark_name.strip())
    if not code:
        result["error"] = f"未知基准指数名称：{benchmark_name}"
        return result
    result["code"] = code

    # 自动回退结束日期到基准数据可用范围
    adjusted_end = end_date
    if auto_fallback:
        latest = _find_latest_available_date(code, end_date)
        if latest and latest != end_date:
            adjusted_end = latest
            result["date_adjusted"] = True

    result["adjusted_end"] = adjusted_end

    date_list = _date_range(start_date, adjusted_end)
    if not date_list:
        result["error"] = "日期范围为空"
        return result

    prices_with_dates = []
    for ds in date_list:
        parsed = _parse_date(ds)
        if not parsed:
            continue
        close = read_base_quote(*parsed, code)
        if close is not None:
            prices_with_dates.append({"date": ds, "close": close})

    if len(prices_with_dates) < 2:
        result["error"] = "区间内有效数据点不足（需要至少2个）"
        return result

    n = len(prices_with_dates)
    closes = [item["close"] for item in prices_with_dates]

    # 回撤序列：用从起点开始的动态回撤（适合绘图，第一条=0），转为百分比
    dd_series_raw, _ = compute_drawdown_from_start(closes)
    # 最大回撤：用任意高点到后续最低点的方法
    _, max_dd = compute_max_drawdown_from_prices(closes)

    # 转为百分比
    dd_series = [
        {"date": item["date"], "close": item["close"], "drawdown": dd_series_raw[i] * 100}
        for i, item in enumerate(prices_with_dates)
    ]

    result["dd_series"] = dd_series
    result["max_drawdown"] = max_dd
    result["max_drawdown_pct"] = max_dd * 100
    result["success"] = True
    return result


# ---------------------------------------------------------
# 通用最大回撤工具（任意高点 → 后续最低点）
# 已移至 services/metrics.py，由上方 import 引入
# ---------------------------------------------------------
