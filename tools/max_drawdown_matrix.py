# -*- coding: utf-8 -*-
"""
生成 2026-03-13 ~ 2026-05-08 区间内所有子区间的中证800 最大回撤。

用法：python tools/max_drawdown_matrix.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime, timedelta
import os

import config

# 基准指数文件根目录（从 config 读取，支持通过环境变量 BASE_INDEX_DIR 配置）
BASE_DIR = str(config.BASE_INDEX_DIR)
START = "2026-03-13"
END = "2026-05-08"


def _quote_path(yyyy: int, m: int, d: int) -> str:
    """返回指定日期的 QT_INDEXQUOTE.txt 文件路径。"""
    if os.path.isabs(BASE_DIR):
        return os.path.join(BASE_DIR, str(yyyy), str(m), str(d), "QT_INDEXQUOTE.txt")
    return os.path.join(str(config.BASE_DIR), BASE_DIR, str(yyyy), str(m), str(d), "QT_INDEXQUOTE.txt")


def _available_dates(start: str, end: str) -> list[str]:
    dates = []
    cur = datetime.strptime(start, "%Y-%m-%d")
    fin = datetime.strptime(end, "%Y-%m-%d")
    while cur <= fin:
        ds = cur.strftime("%Y-%m-%d")
        path = _quote_path(cur.year, cur.month, cur.day)
        if os.path.exists(path):
            dates.append(ds)
        cur += timedelta(days=1)
    return dates


def _read_close(path: str, code: str = "000906.SH") -> float | None:
    """
    字段顺序（pipe-separated）：
      0=SECU_CODE  1=TRADINGDAY  2=PREVCLOSEPRICE  3=OPENPRICE
      4=HIGHPRICE   5=LOWPRICE     6=CLOSEPRICE       7=TURNOVERVOLUME
      8=TURNOVERVALUE  9=XGRQ
    第一行是表头，跳过。
    """
    try:
        with open(path, encoding="utf-8-sig") as f:
            header_skipped = False
            for line in f:
                if not header_skipped:
                    header_skipped = True
                    continue
                fields = line.strip().split("|")
                if len(fields) < 10:
                    continue
                if fields[0].strip() == code:
                    raw = fields[6].strip()
                    if raw == "" or raw.upper() == "NONE":
                        return None
                    try:
                        return float(raw)
                    except ValueError:
                        return None
        return None
    except Exception:
        return None


def subinterval_max_drawdown(closes: list[float]) -> float:
    """
    给定子区间价格序列，返回该子区间的最大回撤（任意高点→后续最低点，原始小数）。
    """
    n = len(closes)
    if n < 2:
        return 0.0
    # 从右向左：每个位置之后（含自身）的最低价
    min_after = [0.0] * n
    min_so_far = closes[-1]
    for i in range(n - 1, -1, -1):
        if closes[i] < min_so_far:
            min_so_far = closes[i]
        min_after[i] = min_so_far
    # 从左向右：维护峰值，计算回撤
    peak = closes[0]
    max_dd = 0.0
    for i in range(n):
        if closes[i] > peak:
            peak = closes[i]
        dd = (min_after[i] - peak) / peak
        if dd < max_dd:
            max_dd = dd
    return max_dd


def main():
    print(f"读取有效交易日... [{START} ~ {END}]")
    dates = _available_dates(START, END)
    print(f"共 {len(dates)} 个有效交易日\n")

    closes = []
    missing = []
    for ds in dates:
        dt = datetime.strptime(ds, "%Y-%m-%d")
        path = _quote_path(dt.year, dt.month, dt.day)
        v = _read_close(path)
        if v is None:
            missing.append(ds)
        closes.append(v)

    valid_dates = [d for d, c in zip(dates, closes) if c is not None]
    valid_closes = [c for c in closes if c is not None]

    if len(valid_closes) < 2:
        print("有效数据不足，无法计算。")
        return

    print(f"有效数据点: {len(valid_closes)}，缺失日期: {missing}")
    total_subintervals = len(valid_dates) * (len(valid_dates) + 1) // 2
    print(f"子区间总数: {total_subintervals}\n")
    print("=" * 72)
    print(f"{'子区间':<36}  {'最大回撤':>10}")
    print("=" * 72)

    all_results = []
    n = len(valid_dates)
    for i in range(n):
        for j in range(i, n):
            sub = valid_closes[i:j + 1]
            max_dd_pct = subinterval_max_drawdown(sub) * 100
            all_results.append((valid_dates[i], valid_dates[j], max_dd_pct))

    for start, end, dd in all_results:
        label = f"{start} ~ {end}"
        print(f"{label:<36}  {dd:>+9.4f}%")

    print("=" * 72)
    print(f"合计 {len(all_results)} 个子区间")

    # 回撤最深的10个子区间
    worst = sorted(all_results, key=lambda x: x[2])[:10]
    print("\n回撤最深的10个子区间：")
    print(f"{'子区间':<36}  {'最大回撤':>10}")
    print("-" * 48)
    for start, end, dd in worst:
        print(f"{start} ~ {end:<12}  {dd:>+9.4f}%")


if __name__ == "__main__":
    main()
