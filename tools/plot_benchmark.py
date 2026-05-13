# -*- coding: utf-8 -*-
"""
tools/plot_benchmark.py - 收集指定时间段的基准指数收盘价

用法：
    python tools/plot_benchmark.py 中证500 --start 2026-02-01 --end 2026-05-10
    python tools/plot_benchmark.py 沪深300 --start 2026-01-01 --end 2026-04-30
"""

import sys
import os
import csv

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

import argparse

from services.period_stats import (
    BENCHMARK_CODE_MAP,
    read_base_quote,
    _parse_date,
    _date_range,
)


def main():
    parser = argparse.ArgumentParser(description="收集基准指数收盘价")
    parser.add_argument(
        "index", nargs="?", default=None,
        help="指数名称，如 沪深300、中证500、中证1000、中证800、上证50"
    )
    parser.add_argument(
        "--start", default="2026-01-01",
        help="起始日期 YYYY-MM-DD"
    )
    parser.add_argument(
        "--end", default="2026-05-10",
        help="结束日期 YYYY-MM-DD"
    )
    parser.add_argument(
        "--output",
        help="输出 CSV 路径（默认 benchmark_{指数}_{start}_{end}.csv）"
    )
    args = parser.parse_args()

    if args.index and args.index not in BENCHMARK_CODE_MAP:
        print(f"错误：不支持的指数 '{args.index}'")
        print(f"支持的指数：{list(BENCHMARK_CODE_MAP.keys())}")
        sys.exit(1)
    benchmark_name = args.index

    if not benchmark_name:
        print("可用指数：", list(BENCHMARK_CODE_MAP.keys()))
        sys.exit(1)

    code = BENCHMARK_CODE_MAP[benchmark_name]
    date_list = _date_range(args.start, args.end)
    rows = []
    for ds in date_list:
        parsed = _parse_date(ds)
        if not parsed:
            continue
        close = read_base_quote(*parsed, code)
        if close is not None:
            rows.append({"date": ds, "close": close})

    if not rows:
        print("错误：无有效数据。")
        sys.exit(1)

    out_path = args.output or f"benchmark_{benchmark_name}_{args.start}_{args.end}.csv"
    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["date", "close"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"{benchmark_name} [{args.start} ~ {args.end}]")
    print(f"  共 {len(rows)} 条数据")
    print(f"  已保存：{os.path.abspath(out_path)}")


if __name__ == "__main__":
    main()
