# -*- coding: utf-8 -*-
"""
services/data_service.py - 统一数据服务层

整合所有 CSV 数据访问逻辑，提供一致的 API 接口。
消除 routes/ 层中的重复 CSV 解析代码。

存储结构：
  data/YYYYMMDD/{tag}.csv           ← 爬取归档快照
  data/.{tag}.index.json              ← 持久化索引文件
  cumulative/crawl_records.csv        ← 爬取记录
  cumulative/{tag}/{fund}/xxx.csv    ← 累计净值数据
"""

import os
import csv
import json
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd

import config
from utils.file import safe_filename, normalize_for_comparison

from app_logging import get_logger
logger = get_logger(__name__)


# ===================== 列名映射（导出用）=====================

COLUMN_NAME_MAP = {
    "基金名称": ("基金名称", "Fund Name"),
    "基金代码": ("基金代码", "Fund Code"),
    "策略": ("策略", "Strategy"),
    "净值日期": ("净值日期", "Net Value Date"),
    "最新净值": ("最新净值", "Latest Net Value"),
    "净值变动": ("净值变动", "Net Change"),
    "净值对比日期": ("净值对比日期", "Net Change Compare Date"),
    "成立来年化": ("成立来年化", "Annualized Return"),
    "今年来": ("今年来", "YTD Return"),
    "上周": ("上周", "Last Week"),
    "上周区间": ("上周区间", "Last Week Range"),
    "近一月": ("近一月", "1 Month"),
    "近三月": ("近三月", "3 Month"),
    "近半年": ("近半年", "6 Month"),
    "近一年": ("近一年", "1 Year"),
    "近两年": ("近两年", "2 Year"),
    "近三年": ("近三年", "3 Year"),
    "近五年": ("近五年", "5 Year"),
    "成立来": ("成立来", "Since Inception"),
    "本周": ("本周", "This Week"),
    "本周区间": ("本周区间", "This Week Range"),
    "回撤": ("回撤", "Max Drawdown"),
    "爬取时间": ("爬取时间", "Crawl Time"),
    "爬取日期": ("爬取日期", "Crawl Date"),
}


# ===================== 路径常量 =====================

CUMULATIVE_BASE = str(config.CUMULATIVE_BASE_DIR)
CRAWL_RECORDS_CSV = os.path.join(CUMULATIVE_BASE, "crawl_records.csv")
RECORD_COLUMNS = [
    "id", "tag", "crawl_date", "start_time", "end_time",
    "status", "total_funds", "ocr_success", "error_message",
]


# ===================== DataService 主类 =====================

class DataService:
    """统一数据服务层"""

    # ==================== 基金数据（最新/历史） ====================

    @staticmethod
    def get_latest_funds(
        tag: str,
        page: int = 1,
        per_page: int = 20,
        search: str = "",
        sort: str = "crawl_time",
        order: str = "desc",
    ) -> dict:
        """
        从 data/ 目录扫描所有日期的 {tag}.csv，对每个基金只保留最新爬取日期的记录。
        优先使用持久化索引文件加速查询。
        """
        index = _ensure_index(tag)
        funds_index = index.get("funds", {})

        latest_map: dict[str, dict] = {}
        date_dirs = _list_date_dirs(str(config.DATA_DIR))

        # 建立 path -> 日期 的映射
        path_dates: dict[str, str] = {}
        for _, date_compact in date_dirs:
            csv_path = os.path.join(str(config.DATA_DIR), date_compact, f"{tag}.csv")
            path_dates[csv_path] = f"{date_compact[:4]}-{date_compact[4:6]}-{date_compact[6:8]}"

        # 按 csv_path 分组，避免重复读取
        csv_to_funds: dict[str, list[str]] = {}
        for fund_name, info in funds_index.items():
            csv_path = info.get("csv_path", "")
            if not csv_path:
                continue
            if csv_path not in csv_to_funds:
                csv_to_funds[csv_path] = []
            csv_to_funds[csv_path].append(fund_name)

        for csv_path, fund_names in csv_to_funds.items():
            if not os.path.exists(csv_path):
                continue
            try:
                df = pd.read_csv(csv_path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
                name_col = _find_name_col(df)
                if not name_col:
                    continue
                crawl_date_fmt = path_dates.get(csv_path, "")

                for fund_name in fund_names:
                    matched = df[df[name_col].astype(str).str.strip() == fund_name]
                    if matched.empty:
                        continue
                    record = matched.iloc[0].to_dict()
                    record["基金名称"] = fund_name
                    record["爬取日期"] = crawl_date_fmt
                    latest_map[fund_name] = record
            except Exception:
                continue

        all_meta = list(latest_map.values())

        # 搜索
        if search:
            s = search.lower()
            all_meta = [m for m in all_meta if s in m.get("基金名称", "").lower()]

        # 排序
        sort_col_map = {
            "crawl_time": "爬取日期",
            "fund_name": "基金名称",
            "crawl_date": "爬取日期",
        }
        sort_col = sort_col_map.get(sort, "爬取日期")
        reverse = order == "desc"
        all_meta.sort(key=lambda m: m.get(sort_col, ""), reverse=reverse)

        # 分页
        total = len(all_meta)
        pages = max(1, (total + per_page - 1) // per_page)
        start = (page - 1) * per_page
        end = start + per_page
        items = all_meta[start:end]

        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": pages,
            "tag": tag,
        }

    @staticmethod
    def get_all_funds(
        tag: str,
        page: int = 1,
        per_page: int = 20,
        search: str = "",
        sort: str = "crawl_time",
        order: str = "desc",
        crawl_date: str = "",
    ) -> dict:
        """
        从 data/ 读取指定日期的 {tag}.csv（未指定 crawl_date 时取最新日期）。
        """
        data_dir = str(config.DATA_DIR)
        date_dirs = _list_date_dirs(data_dir)

        # 确定读取哪个 CSV
        target_csv = None
        if crawl_date:
            compact = crawl_date.replace("-", "")
            csv_path = os.path.join(data_dir, compact, f"{tag}.csv")
            if os.path.exists(csv_path):
                target_csv = csv_path
        else:
            for _, date_compact in date_dirs:
                csv_path = os.path.join(data_dir, date_compact, f"{tag}.csv")
                if os.path.exists(csv_path):
                    target_csv = csv_path
                    break

        all_meta = []
        if target_csv:
            try:
                df = pd.read_csv(target_csv, dtype=str, keep_default_na=False, encoding="utf-8-sig")
                name_col = _find_name_col(df)
                if name_col:
                    crawl_date_fmt = target_csv.split(os.sep)[-2]
                    crawl_date_fmt = f"{crawl_date_fmt[:4]}-{crawl_date_fmt[4:6]}-{crawl_date_fmt[6:8]}"
                    for _, row in df.iterrows():
                        fund_name = str(row.get(name_col, "")).strip()
                        if not fund_name:
                            continue
                        record = row.to_dict()
                        record["基金名称"] = fund_name
                        record["爬取日期"] = crawl_date_fmt
                        all_meta.append(record)
            except Exception:
                pass

        # 搜索
        if search:
            s = search.lower()
            all_meta = [m for m in all_meta if s in m.get("基金名称", "").lower()]

        # 排序
        sort_col_map = {
            "crawl_time": "爬取日期",
            "fund_name": "基金名称",
            "crawl_date": "爬取日期",
        }
        sort_col = sort_col_map.get(sort, "爬取日期")
        reverse = order == "desc"
        all_meta.sort(key=lambda m: m.get(sort_col, ""), reverse=reverse)

        # 分页
        total = len(all_meta)
        pages = max(1, (total + per_page - 1) // per_page)
        start = (page - 1) * per_page
        end = start + per_page
        items = all_meta[start:end]

        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": pages,
            "tag": tag,
            "crawl_date": crawl_date,
        }

    @staticmethod
    def get_fund_history(tag: str, fund_name: str, page: int = 1, per_page: int = 20) -> dict:
        """从所有 data/YYYYMMDD/{tag}.csv 扫描该基金的历史记录"""
        data_dir = str(config.DATA_DIR)
        date_dirs = _list_date_dirs(data_dir)

        all_rows = []
        for _, date_compact in date_dirs:
            csv_path = os.path.join(data_dir, date_compact, f"{tag}.csv")
            if not os.path.exists(csv_path):
                continue
            try:
                df = pd.read_csv(csv_path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
            except Exception:
                continue
            if df.empty:
                continue

            name_col = _find_name_col(df)
            if name_col is None:
                continue

            matched = df[df[name_col].astype(str).str.strip() == fund_name]
            if matched.empty:
                matched = df[df[name_col].astype(str).str.contains(
                    fund_name.replace("\\", "\\\\"), regex=True, na=False
                )]
            if matched.empty:
                continue

            crawl_date = f"{date_compact[:4]}-{date_compact[4:6]}-{date_compact[6:8]}"
            for _, row in matched.iterrows():
                record = row.to_dict()
                record["爬取日期"] = crawl_date
                record["爬取时间"] = crawl_date + " 00:00:00"
                all_rows.append(record)

        all_rows.sort(key=lambda r: r.get("爬取日期", ""), reverse=True)

        total = len(all_rows)
        pages = max(1, (total + per_page - 1) // per_page)
        start = (page - 1) * per_page
        end = start + per_page
        records = all_rows[start:end]

        return {
            "records": records,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": pages,
            "tag": tag,
            "fund_name": fund_name,
        }

    # ==================== 日期范围 ====================

    @staticmethod
    def get_data_date_range(tag: str) -> dict:
        """扫描 data/ 目录，返回指定 tag 的可用日期范围"""
        data_dir = str(config.DATA_DIR)
        if not os.path.isdir(data_dir):
            return {"min_date": None, "max_date": None, "available_dates": []}

        date_dirs = _list_date_dirs(data_dir)
        available_dates = []

        for _, date_compact in date_dirs:
            csv_path = os.path.join(data_dir, date_compact, f"{tag}.csv")
            if os.path.exists(csv_path):
                try:
                    df = pd.read_csv(csv_path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
                    if not df.empty:
                        available_dates.append(
                            f"{date_compact[:4]}-{date_compact[4:6]}-{date_compact[6:8]}"
                        )
                except Exception:
                    pass

        if not available_dates:
            return {"min_date": None, "max_date": None, "available_dates": []}

        available_dates.sort()
        return {
            "min_date": available_dates[0],
            "max_date": available_dates[-1],
            "available_dates": available_dates,
        }

    @staticmethod
    def get_fund_dates(tag: str, fund_name: str) -> dict:
        """获取指定基金在 data/ 中的可用日期范围"""
        if not fund_name:
            return DataService.get_data_date_range(tag)

        csv_path, _ = DataService.find_fund_csv_path(tag, fund_name)
        if not os.path.exists(csv_path):
            return {"min_date": None, "max_date": None, "available_dates": []}

        try:
            df = pd.read_csv(csv_path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
            if "净值日期" not in df.columns:
                return {"min_date": None, "max_date": None, "available_dates": []}
            df["_sort_date"] = pd.to_datetime(df["净值日期"], errors="coerce")
            df = df.dropna(subset=["_sort_date"]).sort_values("_sort_date")
            dates = df["净值日期"].tolist()
            if not dates:
                return {"min_date": None, "max_date": None, "available_dates": []}
            return {"min_date": dates[0], "max_date": dates[-1], "available_dates": dates}
        except Exception:
            return {"min_date": None, "max_date": None, "available_dates": []}

    @staticmethod
    def get_global_min_date() -> Optional[str]:
        """扫描 cumulative/ 下所有 CSV，返回最早的净值日期"""
        base = str(config.CUMULATIVE_BASE_DIR)
        if not os.path.isdir(base):
            return None

        earliest = None
        try:
            for tag_subdir in os.listdir(base):
                tag_path = os.path.join(base, tag_subdir)
                if not os.path.isdir(tag_path):
                    continue
                for fund_subdir in os.listdir(tag_path):
                    fund_path = os.path.join(tag_path, fund_subdir)
                    if not os.path.isdir(fund_path):
                        continue
                    csv_files = [f for f in os.listdir(fund_path) if f.endswith(".csv")]
                    for csv_file in csv_files:
                        csv_path = os.path.join(fund_path, csv_file)
                        try:
                            df = pd.read_csv(csv_path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
                            if "净值日期" not in df.columns:
                                continue
                            dates = pd.to_datetime(df["净值日期"], errors="coerce").dropna()
                            if not dates.empty:
                                first = dates.min()
                                if earliest is None or first < earliest:
                                    earliest = first
                        except Exception:
                            continue
        except Exception:
            return None

        return earliest.strftime("%Y-%m-%d") if earliest else None

    # ==================== 累计净值基金列表 ====================

    @staticmethod
    def get_cumulative_fund_list() -> list:
        """返回 cumulative/ 目录下所有基金列表"""
        items = []
        base = str(config.CUMULATIVE_BASE_DIR)
        if not os.path.isdir(base):
            return items

        try:
            for tag_subdir in os.listdir(base):
                tag_path = os.path.join(base, tag_subdir)
                if not os.path.isdir(tag_path):
                    continue
                for fund_subdir in os.listdir(tag_path):
                    fund_path = os.path.join(tag_path, fund_subdir)
                    if os.path.isdir(fund_path):
                        items.append({"tag": tag_subdir, "fund_name": fund_subdir})
        except Exception:
            pass

        return items

    # ==================== 基金CSV路径解析 ====================

    @staticmethod
    def find_fund_csv_path(tag: str, fund_name: str) -> tuple:
        """
        返回 (csv_path, safe_name)。

        支持：
        1. 精确匹配：直接使用 safe_filename 转换后的名称
        2. 模糊匹配：扫描目录比较标准化后的名称
        """
        _safe_name = safe_filename(fund_name)
        normalized_fund_name = normalize_for_comparison(fund_name)

        # 1. 精确匹配
        expected = os.path.join(str(config.CUMULATIVE_BASE_DIR), tag, _safe_name, f"{_safe_name}.csv")
        if os.path.exists(expected):
            return expected, _safe_name

        # 2. 模糊匹配
        tag_dir = os.path.join(str(config.CUMULATIVE_BASE_DIR), tag)
        if os.path.isdir(tag_dir):
            for entry in os.listdir(tag_dir):
                entry_dir = os.path.join(tag_dir, entry)
                if not os.path.isdir(entry_dir):
                    continue
                if normalize_for_comparison(entry) == normalized_fund_name:
                    csv_file = os.path.join(entry_dir, f"{entry}.csv")
                    if os.path.exists(csv_file):
                        return csv_file, entry
                # 检查 CSV 文件内容
                for fname in os.listdir(entry_dir):
                    if not fname.lower().endswith('.csv'):
                        continue
                    csv_path = os.path.join(entry_dir, fname)
                    try:
                        df = pd.read_csv(csv_path, dtype=str, keep_default_na=False, encoding='utf-8-sig', nrows=2)
                        if '净值日期' in df.columns and normalize_for_comparison(entry) == normalized_fund_name:
                            return csv_path, entry
                    except Exception:
                        continue

        return expected, _safe_name

    # ==================== 时序数据 ====================

    @staticmethod
    def get_fund_timeseries(
        tag: str,
        fund_name: str,
        start_date: str = "",
        end_date: str = "",
        benchmark_override: str = "",
    ) -> dict:
        """
        获取指定基金在时间范围内的历史净值数据。
        返回净值序列和基准指数数据。
        """
        from services.period_stats import (
            compute_benchmark_interval_return,
            _parse_date,
            read_base_quote,
            compute_benchmark_drawdown,
        )
        from services.metrics import (
            align_benchmark_by_date,
            compute_max_drawdown_from_prices,
            compute_excess_drawdown_from_series,
        )

        csv_path, _ = DataService.find_fund_csv_path(tag, fund_name)
        if not os.path.exists(csv_path):
            return {"error": f"基金 '{fund_name}' 暂无历史净值数据"}

        df_all = pd.read_csv(csv_path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
        if df_all.empty or "净值日期" not in df_all.columns:
            return {"error": f"基金 '{fund_name}' 暂无历史净值数据"}

        df_all["_sort_date"] = pd.to_datetime(df_all["净值日期"], errors="coerce")
        df_all = df_all.dropna(subset=["_sort_date"]).sort_values("_sort_date").reset_index(drop=True)

        nav_col = "累计净值(分红再投资)"
        if nav_col not in df_all.columns:
            return {"error": "CSV 文件缺少'累计净值(分红再投资)'列"}

        # 日期修正
        if df_all.empty:
            return {"error": f"基金 '{fund_name}' 累计净值数据为空"}
        fund_min_date = df_all["净值日期"].iloc[0]
        fund_max_date = df_all["净值日期"].iloc[-1]
        corrected_start = _correct_fund_date_boundary(df_all, start_date) or fund_min_date
        corrected_end = _correct_fund_date_boundary(df_all, end_date) or fund_max_date

        df = df_all.copy()
        if corrected_start:
            df = df[df["_sort_date"] >= datetime.strptime(corrected_start, "%Y-%m-%d")]
        if corrected_end:
            df = df[df["_sort_date"] <= datetime.strptime(corrected_end, "%Y-%m-%d")]

        if df.empty:
            return {"error": f"基金 '{fund_name}' 在 [{corrected_start} ~ {corrected_end}] 区间内无净值数据"}

        dates = df["净值日期"].tolist()
        nav_values = df[nav_col].tolist()

        # 确定基准指数
        benchmark_name = ""
        if benchmark_override:
            benchmark_name = benchmark_override
        elif "组合基准指数" in df_all.columns:
            raw_bench = df_all["组合基准指数"].iloc[0]
            if raw_bench:
                benchmark_name = str(raw_bench).strip()

        # 获取基准数据
        benchmark_values = None
        benchmark_start_value = None
        benchmark_adjusted = False
        if benchmark_name:
            bench_ret = compute_benchmark_interval_return(benchmark_name, corrected_start, corrected_end)
            logger.info(f"[timeseries] 基准 '{benchmark_name}' 查表结果: {bench_ret}")
            if bench_ret["success"]:
                secu_code = bench_ret["code"]
                benchmark_adjusted = bench_ret.get("date_adjusted", False)
                adjusted_end = bench_ret.get("adjusted_end", corrected_end)

                # 使用修正后的结束日期来确定基准数据读取范围
                bench_dates = []
                bench_values = []
                for ds in dates:
                    # 跳过超过基准数据可用范围的日期
                    if ds > adjusted_end:
                        continue
                    parsed = _parse_date(ds)
                    if parsed:
                        v = read_base_quote(*parsed, secu_code)
                        if v is not None:
                            bench_dates.append(ds)
                            bench_values.append(v)
                logger.info(f"[timeseries] 基准 '{benchmark_name}' ({secu_code}) 命中 {len(bench_values)}/{len(dates)} 个日期"
                            f"{' (日期已自动回退)' if benchmark_adjusted else ''}")
                benchmark_values = align_benchmark_by_date(dates, bench_dates, bench_values)
                benchmark_start_value = bench_ret["close_start"]
            else:
                logger.warning(f"[timeseries] 基准 '{benchmark_name}' 查表失败: {bench_ret.get('error', 'unknown')}")

        benchmark_has_data = benchmark_values and any(v is not None for v in benchmark_values)
        logger.info(f"[timeseries] benchmark_has_data={benchmark_has_data}, benchmark_values={benchmark_values[:5] if benchmark_values else None}")

        # 计算基金回撤
        fund_max_drawdown = None
        nav_floats = [float(v) if v else None for v in nav_values]
        valid_navs = [v for v in nav_floats if v is not None]
        if len(valid_navs) >= 2:
            _, max_dd = compute_max_drawdown_from_prices(valid_navs)
            fund_max_drawdown = max_dd * 100

        # 计算基准回撤
        bench_drawdown_series = None
        bench_max_drawdown = None
        if benchmark_has_data:
            bench_dd_result = compute_benchmark_drawdown(benchmark_name, corrected_start, corrected_end)
            if bench_dd_result["success"]:
                bench_dates_list = [d["date"] for d in bench_dd_result["dd_series"]]
                bench_dd_values = [d["drawdown"] for d in bench_dd_result["dd_series"]]
                aligned = align_benchmark_by_date(dates, bench_dates_list, bench_dd_values)
                bench_drawdown_series = _normalize_drawdown_series(aligned)
                bench_max_drawdown = bench_dd_result["max_drawdown_pct"]

        # 计算超额回撤
        excess_drawdown_series = None
        if benchmark_has_data and benchmark_values and nav_floats:
            fund_nav_valid = [v for v in nav_floats if v is not None]
            bench_nav_for_excess = []
            valid_idx = 0
            for v in nav_floats:
                if v is not None and valid_idx < len(benchmark_values) and benchmark_values[valid_idx] is not None:
                    bench_nav_for_excess.append(benchmark_values[valid_idx])
                    valid_idx += 1
                else:
                    bench_nav_for_excess.append(None)

            aligned_fund_nav = []
            aligned_bench_nav = []
            for f, b in zip(fund_nav_valid, bench_nav_for_excess):
                if f is not None and b is not None:
                    aligned_fund_nav.append(f)
                    aligned_bench_nav.append(b)

            if len(aligned_fund_nav) >= 2 and len(aligned_fund_nav) == len(aligned_bench_nav):
                excess_dd_series, _ = compute_excess_drawdown_from_series(aligned_fund_nav, aligned_bench_nav)
                if excess_dd_series:
                    excess_drawdown_series = []
                    seq_idx = 0
                    for v in nav_floats:
                        if v is not None and seq_idx < len(excess_dd_series):
                            excess_drawdown_series.append(excess_dd_series[seq_idx] * 100)
                            seq_idx += 1
                        else:
                            excess_drawdown_series.append(None)

        # 计算基金动态回撤序列
        fund_drawdown_series = []
        fund_peak = None
        for v in nav_floats:
            if v is not None:
                if fund_peak is None or v > fund_peak:
                    fund_peak = v
                fund_drawdown_series.append(((v - fund_peak) / fund_peak * 100) if fund_peak != 0 else 0.0)
            else:
                fund_drawdown_series.append(None)

        return {
            "fund_name": fund_name,
            "benchmark_name": benchmark_name if benchmark_has_data else "",
            "benchmark_available": benchmark_has_data,
            "benchmark_is_default": not benchmark_override and "组合基准指数" in df_all.columns,
            "benchmark_date_adjusted": benchmark_adjusted,
            "dates": dates,
            "nav_values": nav_values,
            "benchmark_values": benchmark_values if benchmark_has_data else [],
            "benchmark_start_value": benchmark_start_value if benchmark_has_data else None,
            "benchmark_drawdown": bench_drawdown_series if benchmark_has_data else [],
            "benchmark_max_drawdown": bench_max_drawdown,
            "excess_drawdown": excess_drawdown_series if excess_drawdown_series else [],
            "fund_drawdown": fund_drawdown_series,
            "fund_max_drawdown": fund_max_drawdown,
            "date_corrected": corrected_start != start_date or corrected_end != end_date,
            "original_start": start_date or "",
            "original_end": end_date or "",
            "corrected_start": corrected_start,
            "corrected_end": corrected_end,
            "warning": None if benchmark_has_data else "基准数据缺失，仅展示基金走势",
        }

    # ==================== 风险指标 ====================

    @staticmethod
    def compute_risk_metrics(
        tag: str,
        fund_name: str,
        start_date: str = "",
        end_date: str = "",
        rf: float = 0.03,
        benchmark_override: str = "",
    ) -> dict:
        """
        计算指定基金在区间内的风险指标。
        """
        from services.period_stats import (
            compute_benchmark_interval_return,
            _parse_date,
            read_base_quote,
        )
        from services.metrics import (
            compute_max_drawdown_from_prices,
            compute_excess_drawdown_from_series,
        )

        csv_path, _ = DataService.find_fund_csv_path(tag, fund_name)
        if not os.path.exists(csv_path):
            return {"error": f"基金 '{fund_name}' 暂无历史净值数据"}

        df = pd.read_csv(csv_path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
        if df.empty or "净值日期" not in df.columns:
            return {"error": "CSV 文件格式异常"}

        nav_col = "累计净值(分红再投资)"
        if nav_col not in df.columns:
            return {"error": "CSV 文件缺少'累计净值(分红再投资)'列"}

        df["_sort_date"] = pd.to_datetime(df["净值日期"], errors="coerce")
        df = df.dropna(subset=["_sort_date"]).sort_values("_sort_date").reset_index(drop=True)

        # 日期修正
        if df.empty:
            return {"error": f"基金 '{fund_name}' 累计净值数据为空"}
        fund_min_date = df["净值日期"].iloc[0]
        fund_max_date = df["净值日期"].iloc[-1]
        corrected_start = _correct_fund_date_boundary(df, start_date) or fund_min_date
        corrected_end = _correct_fund_date_boundary(df, end_date) or fund_max_date

        df = df[df["_sort_date"] >= datetime.strptime(corrected_start, "%Y-%m-%d")]
        df = df[df["_sort_date"] <= datetime.strptime(corrected_end, "%Y-%m-%d")]

        if len(df) < 2:
            return {"error": f"区间数据不足，至少需要2个数据点（修正后: {corrected_start} ~ {corrected_end}）"}

        nav = df[nav_col].apply(lambda x: float(x) if x else None).dropna().tolist()
        if len(nav) < 2:
            return {"error": "净值数据无效"}

        # 计算指标
        daily_returns = compute_daily_returns(nav)
        if not daily_returns:
            return {"error": "无法计算收益率序列"}

        n = len(daily_returns)
        interval_days = max(1, (df["_sort_date"].iloc[-1] - df["_sort_date"].iloc[0]).days)
        annualization = 252
        MIN_DAYS_FOR_ANNUALIZED = 30

        total_return = (nav[-1] - nav[0]) / nav[0]
        if interval_days >= MIN_DAYS_FOR_ANNUALIZED:
            annualized_return = (nav[-1] / nav[0]) ** (365.0 / interval_days) - 1
        else:
            annualized_return = None

        mean_ret = np.mean(daily_returns)
        variance = np.sum((np.array(daily_returns) - mean_ret) ** 2) / max(1, n - 1)
        daily_std = np.sqrt(variance)
        annualized_vol = daily_std * np.sqrt(annualization) if interval_days >= MIN_DAYS_FOR_ANNUALIZED else None

        neg_returns = [r for r in daily_returns if r < 0]
        downside_std = np.sqrt(np.sum(np.array(neg_returns) ** 2) / max(1, n - 1)) * np.sqrt(annualization) if neg_returns else 0.0

        sharpe = (annualized_return - rf) / annualized_vol if annualized_vol and annualized_vol != 0 else None
        sortino = (annualized_return - rf) / downside_std if annualized_return is not None and downside_std != 0 else None

        _, max_dd = compute_max_drawdown_from_prices(nav)
        calmar = annualized_return / abs(max_dd) if annualized_return is not None and max_dd != 0 else None

        # 基准数据
        raw_bench = df["组合基准指数"].iloc[0] if "组合基准指数" in df.columns else None
        benchmark_name = benchmark_override or (str(raw_bench).strip() if raw_bench else "沪深300")
        bench_ret = compute_benchmark_interval_return(benchmark_name, corrected_start, corrected_end)

        if bench_ret["success"]:
            b0 = bench_ret["close_start"]
            bench_daily_nav = [b0]
            for ds in df["净值日期"].tolist()[1:]:
                parsed = _parse_date(ds)
                if parsed:
                    v = read_base_quote(*parsed, bench_ret["code"])
                    if v is not None:
                        bench_daily_nav.append(v)

            bench_daily = [
                (bench_daily_nav[i] - bench_daily_nav[i - 1]) / bench_daily_nav[i - 1]
                for i in range(1, len(bench_daily_nav))
                if bench_daily_nav[i - 1] != 0
            ]
            b_vol = np.std(bench_daily, ddof=1) * np.sqrt(annualization) if bench_daily else 0
            _, bench_max_dd = compute_max_drawdown_from_prices(bench_daily_nav)

            tracking_error = np.std(
                [daily_returns[i] - bench_daily[i]
                 for i in range(min(len(daily_returns), len(bench_daily)))], ddof=1
            ) * np.sqrt(annualization) if bench_daily else None

            information_ratio = (total_return - bench_ret["interval_return"]) / tracking_error if tracking_error else None

            _, excess_max_drawdown = compute_excess_drawdown_from_series(nav, bench_daily_nav)

            benchmark_metrics = {
                "name": benchmark_name,
                "code": bench_ret["code"],
                "interval_return": bench_ret["interval_return"] * 100,
                "interval_return_pct": bench_ret["interval_return_pct"],
                "annualized_return": bench_ret["interval_return_pct"] * (365.0 / max(1, interval_days)),
                "annualized_vol": b_vol * 100,
                "max_drawdown": bench_max_dd * 100,
                "max_drawdown_pct": bench_max_dd,
                "excess_return": (total_return - bench_ret["interval_return"]) * 100,
                "excess_max_drawdown": excess_max_drawdown * 100 if excess_max_drawdown is not None else None,
                "tracking_error": tracking_error * 100 if tracking_error else None,
                "information_ratio": information_ratio,
            }
        else:
            benchmark_metrics = {
                "name": benchmark_name,
                "code": bench_ret.get("code"),
                "interval_return": None,
                "interval_return_pct": None,
                "annualized_return": None,
                "annualized_vol": None,
                "max_drawdown": None,
                "max_drawdown_pct": None,
                "excess_return": None,
                "excess_max_drawdown": None,
                "tracking_error": None,
                "information_ratio": None,
            }

        return {
            "fund_name": fund_name,
            "start_date": df["净值日期"].iloc[0],
            "end_date": df["净值日期"].iloc[-1],
            "interval_days": interval_days,
            "interval_return": round(total_return * 100, 4),
            "annualized_return": round(annualized_return * 100, 4) if annualized_return is not None else None,
            "annualized_vol": round(annualized_vol * 100, 4) if annualized_vol is not None else None,
            "max_drawdown": round(max_dd * 100, 4),
            "sharpe_ratio": round(sharpe, 4) if sharpe is not None else None,
            "sortino_ratio": round(sortino, 4) if sortino is not None else None,
            "calmar_ratio": round(calmar, 4) if calmar is not None else None,
            "rf_annual": rf * 100,
            "benchmark": benchmark_metrics,
        }


# ===================== 辅助函数（内部使用） =====================

def compute_daily_returns(nav_list: list) -> list:
    """从净值序列计算日收益率"""
    daily_returns = []
    for i in range(1, len(nav_list)):
        prev = nav_list[i - 1]
        curr = nav_list[i]
        if prev and curr and prev != 0:
            daily_returns.append((curr - prev) / prev)
        else:
            daily_returns.append(0.0)
    return daily_returns


def _normalize_drawdown_series(dd_series: list) -> list:
    """标准化回撤序列"""
    if not dd_series:
        return []
    return [0.0 if v is None else v for v in dd_series]


def _correct_fund_date_boundary(df, date_str: str) -> Optional[str]:
    """将外部日期映射到基金净值数据中存在的最近日期"""
    if not date_str:
        return None
    try:
        target = datetime.strptime(date_str, "%Y-%m-%d")
    except (ValueError, TypeError):
        return None

    mask_eq = df["_sort_date"] == target
    if mask_eq.any():
        return date_str

    mask_lt = df["_sort_date"] < target
    pos = np.where(mask_lt.values)[0]
    if len(pos) > 0:
        return df["净值日期"].iloc[pos[-1]]
    return None


def _list_date_dirs(data_dir: str) -> list:
    """返回按日期降序排列的日期目录列表 [(datetime, name), ...]"""
    dirs = []
    try:
        for entry in os.scandir(data_dir):
            if not entry.is_dir():
                continue
            name = entry.name
            if len(name) == 8 and name.isdigit():
                try:
                    dt = datetime.strptime(name, "%Y%m%d")
                    dirs.append((dt, name))
                except ValueError:
                    pass
    except OSError:
        pass
    dirs.sort(key=lambda x: x[0], reverse=True)
    return dirs


def _find_name_col(df: pd.DataFrame) -> Optional[str]:
    """查找基金名称列"""
    for col in ["基金名称", "fund_name", "名称"]:
        if col in df.columns:
            return col
    return None


# ===================== 索引文件机制 =====================

def _get_index_path(tag: str) -> str:
    return os.path.join(str(config.DATA_DIR), f".{tag}.index.json")


def _ensure_index(tag: str) -> dict:
    """确保索引存在，返回索引数据"""
    index_path = _get_index_path(tag)
    if os.path.exists(index_path):
        try:
            with open(index_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"索引文件损坏，将重新构建: {index_path}, 错误: {e}")
    return _build_index(tag)


def _build_index(tag: str) -> dict:
    """构建并保存索引"""
    index_path = _get_index_path(tag)
    data_dir = str(config.DATA_DIR)
    date_dirs = _list_date_dirs(data_dir)

    funds_map = {}
    for _, date_compact in date_dirs:
        csv_path = os.path.join(data_dir, date_compact, f"{tag}.csv")
        if not os.path.exists(csv_path):
            continue
        try:
            df = pd.read_csv(csv_path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
            name_col = _find_name_col(df)
            if not name_col:
                continue
            crawl_date_fmt = f"{date_compact[:4]}-{date_compact[4:6]}-{date_compact[6:8]}"
            for _, row in df.iterrows():
                fund_name = str(row.get(name_col, "")).strip()
                if not fund_name:
                    continue
                existing = funds_map.get(fund_name)
                if existing is None or crawl_date_fmt > existing.get("latest_date", ""):
                    funds_map[fund_name] = {
                        "latest_date": crawl_date_fmt,
                        "csv_path": csv_path,
                    }
        except Exception:
            continue

    index = {
        "version": 1,
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "funds": funds_map,
    }

    try:
        os.makedirs(os.path.dirname(index_path), exist_ok=True)
        with open(index_path, 'w', encoding='utf-8') as f:
            json.dump(index, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"写入索引文件失败: {index_path}, 错误: {e}")

    return index


def invalidate_index(tag: str) -> None:
    """使索引失效，爬取完成后调用"""
    index_path = _get_index_path(tag)
    if os.path.exists(index_path):
        try:
            os.remove(index_path)
        except Exception:
            pass


# ===================== 爬取记录 =====================

def _init_crawl_records_csv():
    if not os.path.exists(CRAWL_RECORDS_CSV):
        os.makedirs(os.path.dirname(CRAWL_RECORDS_CSV), exist_ok=True)
        with open(CRAWL_RECORDS_CSV, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=RECORD_COLUMNS)
            writer.writeheader()


def save_crawl_record(record: dict) -> str:
    """追加或更新 crawl_records.csv"""
    _init_crawl_records_csv()

    records = []
    if os.path.exists(CRAWL_RECORDS_CSV):
        try:
            records = pd.read_csv(CRAWL_RECORDS_CSV, dtype=str, keep_default_na=False, encoding="utf-8-sig").to_dict("records")
        except Exception:
            records = []

    record_id = record.get("id")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if record_id and str(record_id).strip():
        record_id = str(record_id).strip()
        found = False
        for r in records:
            if str(r.get("id", "")) == record_id:
                for k, v in record.items():
                    if k != "id":
                        r[k] = v if v is not None else ""
                found = True
                break
        if not found:
            new_record = {c: record.get(c, "") for c in RECORD_COLUMNS}
            new_record["id"] = record_id
            records.append(new_record)
    else:
        max_id = max((int(r.get("id", 0)) for r in records if r.get("id", "").isdigit()), default=0)
        new_id = max_id + 1
        new_record = {c: record.get(c, "") for c in RECORD_COLUMNS}
        new_record["id"] = str(new_id)
        new_record["start_time"] = now_str
        records.append(new_record)
        record_id = str(new_id)

    with open(CRAWL_RECORDS_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=RECORD_COLUMNS)
        writer.writeheader()
        writer.writerows(records)

    return record_id


def get_crawl_records(tag: str = "", page: int = 1, per_page: int = 10) -> dict:
    """分页读取 crawl_records.csv，按 start_time 降序"""
    _init_crawl_records_csv()
    if not os.path.exists(CRAWL_RECORDS_CSV):
        return {"items": [], "total": 0, "page": page, "per_page": per_page, "pages": 0}

    try:
        df = pd.read_csv(CRAWL_RECORDS_CSV, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    except Exception:
        return {"items": [], "total": 0, "page": page, "per_page": per_page, "pages": 0}

    if tag and "tag" in df.columns:
        df = df[df["tag"] == tag]

    df["_sort"] = pd.to_datetime(df["start_time"], errors="coerce")
    df = df.dropna(subset=["_sort"]).sort_values("_sort", ascending=False)

    total = len(df)
    pages = max(1, (total + per_page - 1) // per_page)
    start = (page - 1) * per_page
    end = start + per_page

    page_df = df.iloc[start:end]
    items = page_df[RECORD_COLUMNS].to_dict("records")
    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
    }


def delete_crawl_records(ids: list) -> int:
    """从 crawl_records.csv 中删除指定 id 的记录"""
    _init_crawl_records_csv()
    if not os.path.exists(CRAWL_RECORDS_CSV):
        return 0
    try:
        records = pd.read_csv(CRAWL_RECORDS_CSV, dtype=str, keep_default_na=False, encoding="utf-8-sig").to_dict("records")
    except Exception:
        return 0

    id_set = set(str(i).strip() for i in ids)
    original_count = len(records)
    records = [r for r in records if str(r.get("id", "")).strip() not in id_set]
    deleted = original_count - len(records)

    if deleted > 0:
        with open(CRAWL_RECORDS_CSV, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=RECORD_COLUMNS)
            writer.writeheader()
            writer.writerows(records)

    return deleted


def get_tag_summary(tag: str) -> dict:
    """统计：基金数量、最后成功爬取时间"""
    data_dir = str(config.DATA_DIR)
    if not os.path.isdir(data_dir):
        tag_name = next((t["name"] for t in config.FUND_TYPES if t["key"] == tag), tag)
        return {
            "tag": tag,
            "tag_name": tag_name,
            "total_funds": 0,
            "latest_crawl": None,
        }

    date_dirs = _list_date_dirs(data_dir)
    latest_csv_path = None
    latest_crawl_date = None

    for _, date_compact in date_dirs:
        csv_path = os.path.join(data_dir, date_compact, f"{tag}.csv")
        if os.path.exists(csv_path):
            latest_csv_path = csv_path
            latest_crawl_date = f"{date_compact[:4]}-{date_compact[4:6]}-{date_compact[6:8]}"
            break

    fund_count = 0
    if latest_csv_path:
        try:
            df = pd.read_csv(latest_csv_path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
            if not df.empty:
                fund_count = len(df)
        except Exception:
            pass

    latest_crawl = None
    if latest_crawl_date:
        latest_crawl = {
            "id": "",
            "tag": tag,
            "crawl_date": latest_crawl_date,
            "start_time": latest_crawl_date + " 00:00:00",
            "end_time": latest_crawl_date + " 00:00:00",
            "status": "success",
            "total_funds": str(fund_count),
            "ocr_success": "0",
            "error_message": "",
        }

    tag_name = next((t["name"] for t in config.FUND_TYPES if t["key"] == tag), tag)
    return {
        "tag": tag,
        "tag_name": tag_name,
        "total_funds": fund_count,
        "latest_crawl": latest_crawl,
    }


# ===================== CrawlRecordContext 上下文管理器 =====================

class CrawlRecordContext:
    """
    上下文管理器：创建爬取记录 → 执行任务 → 更新状态。
    """

    def __init__(self, tag: str, label: str = ""):
        self.tag = tag
        self.label = label or tag
        self.record_id: str = ""
        self.crawl_date: str = ""
        self.start_time: str = ""

    def __enter__(self):
        now = datetime.now()
        self.crawl_date = now.strftime("%Y-%m-%d")
        self.start_time = now.strftime("%Y-%m-%d %H:%M:%S")
        self.record_id = save_crawl_record({
            "id": None,
            "tag": self.tag,
            "crawl_date": self.crawl_date,
            "start_time": self.start_time,
            "end_time": "",
            "status": "running",
            "total_funds": 0,
            "ocr_success": 0,
            "error_message": "",
        })
        return self

    def update(self, **fields):
        fields["id"] = self.record_id
        fields["tag"] = self.tag
        fields["crawl_date"] = self.crawl_date
        fields["start_time"] = self.start_time
        fields["end_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        save_crawl_record(fields)

    def update_success(self, total: int = 0, ocr: int = 0, error: str = ""):
        self.update(status="success", total_funds=total, ocr_success=ocr, error_message=error)

    def update_failed(self, error: str):
        self.update(status="failed", total_funds=0, ocr_success=0, error_message=error)

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False
