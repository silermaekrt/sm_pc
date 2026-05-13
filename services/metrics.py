# -*- coding: utf-8 -*-
"""
services/metrics.py - 统一指标计算服务

提供基金风险指标的统一计算，包括：
- 日收益率计算
- 最大回撤计算
- 波动率、夏普比率、索提诺比率、卡玛比率
- 基准对齐（使用日期映射而非索引）
- 回撤序列计算
"""

# 公共 API 导出清单
__all__ = [
    "compute_drawdown_from_start",
    "compute_max_drawdown_from_prices",
    "compute_drawdown_from_returns",
    "compute_risk_metrics",
    "align_benchmark_by_date",
    "compute_benchmark_metrics",
    "compute_excess_metrics",
    "compute_excess_drawdown_from_series",
]

import numpy as np
from datetime import datetime
from typing import Optional


# ===================== 核心计算函数 =====================

def compute_drawdown_from_start(prices: list[float]) -> tuple[list[float], float]:
    """
    计算从起点开始的动态回撤序列。

    与 compute_max_drawdown_from_prices 的区别：
    - max_dd: 从任意高点到后续最低点（适合计算最大回撤）
    - drawdown_from_start: 从区间起点开始的回撤（适合绘图展示）

    算法：
    1. 起点净值 = prices[0]
    2. 对每个位置 i，记录从起点到 i 的最高点
    3. 回撤 = (prices[i] - 最高点) / 最高点

    Returns:
        (drawdown_series: list[float], max_drawdown: float)
    """
    if len(prices) < 1:
        return [], 0.0

    start = prices[0]
    if start == 0:
        start = prices[1] if len(prices) > 1 else 1.0

    peak = start
    max_dd = 0.0
    dd_series = []

    for p in prices:
        if p > peak:
            peak = p
        dd = (p - peak) / peak
        if dd < max_dd:
            max_dd = dd
        dd_series.append(dd)

    return dd_series, max_dd


def compute_max_drawdown_from_prices(prices: list[float]) -> tuple[list[float], float]:
    """
    给定价格序列，计算：
      - drawdown_series: 每日的从区间内任意高点到后续最低点的回撤（小数）
      - max_drawdown:    最大回撤（小数，负值）

    算法：O(n)，从右向左预处理 min_after，从左向右扫描峰值。

    Returns:
        (drawdown_series: list[float], max_drawdown: float)
    """
    if len(prices) < 2:
        return [0.0] * len(prices), 0.0

    n = len(prices)
    min_after = [0.0] * n
    min_so_far = prices[-1]
    for i in range(n - 1, -1, -1):
        if prices[i] < min_so_far:
            min_so_far = prices[i]
        min_after[i] = min_so_far

    peak = prices[0]
    max_dd = 0.0
    dd_series = []
    for i in range(n):
        if prices[i] > peak:
            peak = prices[i]
        dd = (min_after[i] - peak) / peak if peak != 0 else 0.0
        if dd < max_dd:
            max_dd = dd
        dd_series.append(dd)
    return dd_series, max_dd


def compute_drawdown_from_returns(returns: list[float]) -> tuple[list[float], float]:
    """
    从收益率序列计算回撤序列。
    收益率序列起点为 0%。

    原理：(1+r1)(1+r2)... -> 还原为净值，再计算回撤

    Returns:
        (drawdown_series: list[float], max_drawdown: float)
    """
    if len(returns) < 2:
        return [0.0] * len(returns), 0.0

    # 还原为净值序列
    nav_values = [1.0]
    for r in returns:
        nav_values.append(nav_values[-1] * (1 + r / 100))  # 假设 returns 是百分比

    return compute_max_drawdown_from_prices(nav_values[1:])  # 去掉初始值


def compute_risk_metrics(
    nav_values: list[float],
    rf_annual: float = 0.03,
    annualization: int = 252,
) -> dict:
    """
    计算基金风险指标。

    Args:
        nav_values: 净值序列（原始小数，如 1.0234）
        rf_annual: 年化无风险利率（默认 3%）
        annualization: 年化天数（默认 252 交易日）

    Returns:
        {
            "daily_returns": list[float],
            "total_return": float,          # 小数
            "annualized_return": float,     # 小数
            "annualized_vol": float,        # 小数
            "sharpe_ratio": float,
            "sortino_ratio": float | None,
            "max_drawdown": float,          # 小数，负值
            "drawdown_series": list[float], # 小数
            "calmar_ratio": float | None,
        }
    """
    if len(nav_values) < 2:
        return {
            "daily_returns": [],
            "total_return": 0.0,
            "annualized_return": 0.0,
            "annualized_vol": 0.0,
            "sharpe_ratio": None,
            "sortino_ratio": None,
            "max_drawdown": 0.0,
            "drawdown_series": [0.0] * len(nav_values),
            "calmar_ratio": None,
        }

    # 日收益率
    daily_returns = []
    for i in range(1, len(nav_values)):
        if nav_values[i - 1] and nav_values[i] and nav_values[i - 1] != 0:
            daily_returns.append((nav_values[i] - nav_values[i - 1]) / nav_values[i - 1])
        else:
            daily_returns.append(0.0)

    n = len(daily_returns)
    if n == 0:
        return {
            "daily_returns": [],
            "total_return": 0.0,
            "annualized_return": 0.0,
            "annualized_vol": 0.0,
            "sharpe_ratio": None,
            "sortino_ratio": None,
            "max_drawdown": 0.0,
            "drawdown_series": [0.0] * len(nav_values),
            "calmar_ratio": None,
        }

    # 区间天数
    interval_days = max(1, len(nav_values) - 1)

    # 总收益
    total_return = (nav_values[-1] - nav_values[0]) / nav_values[0] if nav_values[0] != 0 else 0.0

    # 年化收益（复利公式）
    annualized_return = (nav_values[-1] / nav_values[0]) ** (365.0 / interval_days) - 1 if nav_values[0] != 0 else 0.0

    # 波动率
    mean_ret = np.mean(daily_returns)
    variance = np.sum((np.array(daily_returns) - mean_ret) ** 2) / max(1, n - 1)
    daily_std = np.sqrt(variance)
    annualized_vol = daily_std * np.sqrt(annualization)

    # 夏普比率
    rf_daily = rf_annual / annualization
    excess_returns = np.array(daily_returns) - rf_daily
    sharpe = (np.mean(excess_returns) / daily_std * np.sqrt(annualization)) if daily_std != 0 else None

    # 索提诺比率（下行波动率）
    neg_returns = [r for r in daily_returns if r < 0]
    if len(neg_returns) > 0:
        downside_std = np.sqrt(np.sum(np.array(neg_returns) ** 2) / max(1, len(neg_returns))) * np.sqrt(annualization)
    else:
        downside_std = 0.0
    sortino = (annualized_return - rf_annual) / downside_std if downside_std != 0 else None

    # 最大回撤
    drawdown_series, max_dd = compute_max_drawdown_from_prices(nav_values)

    # 卡玛比率
    calmar = annualized_return / abs(max_dd) if max_dd != 0 else None

    return {
        "daily_returns": daily_returns,
        "total_return": total_return,
        "annualized_return": annualized_return,
        "annualized_vol": annualized_vol,
        "sharpe_ratio": sharpe,
        "sortino_ratio": sortino,
        "max_drawdown": max_dd,
        "drawdown_series": drawdown_series,
        "calmar_ratio": calmar,
    }


def align_benchmark_by_date(
    dates: list[str],
    benchmark_dates: list[str],
    benchmark_values: list[float],
) -> list[Optional[float]]:
    """
    按日期对齐基准净值序列。

    Args:
        dates: 基金净值日期列表
        benchmark_dates: 基准净值日期列表
        benchmark_values: 基准净值值列表

    Returns:
        与 dates 等长的列表，如果某日期没有基准数据则为 None
    """
    # 建立日期 -> 值的字典
    bench_dict = dict(zip(benchmark_dates, benchmark_values))

    # 按日期顺序返回
    result = []
    prev_val = None
    for d in dates:
        if d in bench_dict and bench_dict[d] is not None:
            prev_val = bench_dict[d]
        result.append(prev_val)

    return result


def compute_benchmark_metrics(
    benchmark_dates: list[str],
    benchmark_values: list[float],
    rf_annual: float = 0.03,
    annualization: int = 252,
) -> dict:
    """
    计算基准指数的风险指标。

    Returns:
        {
            "dates": list[str],
            "values": list[float],
            "nav_series": list[float],  # 归一化后的净值序列
            "returns": list[float],
            "total_return": float,
            "annualized_return": float,
            "annualized_vol": float,
            "max_drawdown": float,
            "drawdown_series": list[float],
        }
    """
    if len(benchmark_values) < 2:
        return {
            "dates": benchmark_dates,
            "values": benchmark_values,
            "nav_series": [],
            "returns": [],
            "total_return": 0.0,
            "annualized_return": 0.0,
            "annualized_vol": 0.0,
            "max_drawdown": 0.0,
            "drawdown_series": [],
        }

    # 计算净值序列（归一化到 1.0）
    start_val = benchmark_values[0]
    if start_val == 0:
        start_val = benchmark_values[1] if len(benchmark_values) > 1 else 1.0

    nav_series = [v / start_val for v in benchmark_values]

    # 计算收益率
    returns = []
    for i in range(1, len(benchmark_values)):
        if benchmark_values[i - 1] != 0:
            returns.append((benchmark_values[i] - benchmark_values[i - 1]) / benchmark_values[i - 1])
        else:
            returns.append(0.0)

    # 计算指标
    metrics = compute_risk_metrics(nav_series, rf_annual, annualization)

    # 还原总收益为百分比
    total_return = metrics["total_return"]
    annualized_return = metrics["annualized_return"]

    return {
        "dates": benchmark_dates,
        "values": benchmark_values,
        "nav_series": nav_series,
        "returns": returns,
        "total_return": total_return,
        "annualized_return": annualized_return,
        "annualized_vol": metrics["annualized_vol"],
        "max_drawdown": metrics["max_drawdown"],
        "drawdown_series": metrics["drawdown_series"],
    }


def compute_excess_metrics(
    fund_return: float,
    fund_max_dd: float,
    bench_return: float,
    bench_max_dd: float,
) -> dict:
    """
    计算超额收益指标（旧方法：简单相减）。

    Returns:
        {
            "excess_return": float,        # 小数
            "excess_max_drawdown": float,  # 小数，负值表示基金回撤优于基准
        }
    """
    return {
        "excess_return": fund_return - bench_return,
        "excess_max_drawdown": fund_max_dd - bench_max_dd,
    }


def compute_excess_drawdown_from_series(
    fund_nav: list[float],
    bench_nav: list[float],
) -> tuple[list[float], float]:
    """
    使用相对强弱法计算超额回撤（专业算法）。

    公式: ExcessDD_t = (A_t / B_t) / max_{s≤t}(A_s / B_s) - 1
    含义: 从最强相对高点，到当前相对位置的回落幅度

    Args:
        fund_nav: 基金净值序列（原始小数）
        bench_nav: 基准净值序列（原始小数）

    Returns:
        (excess_dd_series, excess_max_drawdown)
        - excess_dd_series: 每日超额回撤序列（小数）
        - excess_max_drawdown: 超额最大回撤（小数，负值）
    """
    if len(fund_nav) != len(bench_nav) or len(fund_nav) < 2:
        return [], 0.0

    # 计算相对强弱序列
    relative_strength = []
    for a, b in zip(fund_nav, bench_nav):
        if b != 0:
            relative_strength.append(a / b)
        else:
            # 如果基准为0，使用前一个值或1
            relative_strength.append(relative_strength[-1] if relative_strength else 1.0)

    # 计算滚动高点（到当前为止的最高相对强弱）
    running_high = relative_strength[0]
    excess_dd_series = []
    excess_max_dd = 0.0

    for rs in relative_strength:
        if rs > running_high:
            running_high = rs
        # 超额回撤 = (当前相对强弱 / 历史最高相对强弱) - 1
        if running_high != 0:
            excess_dd = (rs / running_high) - 1
        else:
            excess_dd = 0.0
        excess_dd_series.append(excess_dd)
        if excess_dd < excess_max_dd:
            excess_max_dd = excess_dd

    return excess_dd_series, excess_max_dd
