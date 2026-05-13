# -*- coding: utf-8 -*-
"""
services/crawler/storage.py - 数据存储

职责：CSV 文件保存、累计净值数据保存、截图目录管理
"""

import os
from datetime import datetime

import pandas as pd

import config
from utils.file import safe_filename


# ===================== 基金 CSV 保存 =====================
def save_funds_csv(funds: list, date_str: str = "", tag: str = "private") -> str:
    """将基金数据保存为 CSV，返回文件路径"""
    if date_str:
        tag_dir = os.path.join(config.DATA_DIR, date_str)
    else:
        date_str = datetime.now().strftime("%Y%m%d")
        tag_dir = os.path.join(config.DATA_DIR, date_str)
    os.makedirs(tag_dir, exist_ok=True)
    path = os.path.join(tag_dir, f"{tag}.csv")

    df = pd.DataFrame([{k: str(v) if v is not None else "" for k, v in f.items()} for f in funds])
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return path


# ===================== 累计净值数据验证 =====================
def _validate_nav_value(new_nav: float, old_nav: float) -> bool:
    """
    验证新净值是否合理。
    如果旧净值大于0且新旧值差异超过50%，认为是异常数据，返回 False。
    """
    if old_nav <= 0:
        return True
    return abs(new_nav - old_nav) / old_nav <= 0.5


# ===================== 累计净值 CSV 保存 =====================
def save_cumulative_csv(data: list, tag: str, fund_name: str, merge: bool = True, benchmark: str = "") -> str:
    """
    将累计净值数据保存为 CSV。
    列：净值日期, 累计净值(分红再投资), 组合基准指数
    保存路径: cumulative/{tag}/{fund_name}/{fund_name}.csv

    Args:
        data: OCR 提取的净值数据列表
        tag: 标签（如 private/exp）
        fund_name: 基金名称
        merge: 是否追加合并已有 CSV（默认 True）。True 时保留已有数据，
               仅用新数据更新/新增日期；False 时直接覆盖。
        benchmark: 基准指数名称（如"沪深300"），merge 模式下不覆盖已有值。
    """
    if not data:
        # 无净值数据时，不写入任何内容，保护已有数据
        return ""

    safe_name = safe_filename(fund_name)
    fund_dir = os.path.join(config.CUMULATIVE_BASE_DIR, tag, safe_name)
    os.makedirs(fund_dir, exist_ok=True)
    csv_path = os.path.join(fund_dir, f"{safe_name}.csv")

    if merge and os.path.exists(csv_path):
        try:
            existing_df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
            existing = dict(zip(
                existing_df["净值日期"].tolist(),
                existing_df["累计净值(分红再投资)"].tolist(),
            ))
            # 保留已有基准指数，不覆盖
            if "组合基准指数" in existing_df.columns:
                _saved_benchmark = existing_df["组合基准指数"].iloc[0]
                if _saved_benchmark:
                    benchmark = _saved_benchmark
        except Exception:
            existing = {}
    else:
        existing = {}

    for row in data:
        date = row["净值日期"]
        new_nav_str = row["累计净值(分红再投资)"]

        if date in existing:
            try:
                new_nav = float(new_nav_str) if new_nav_str else 0
            except (ValueError, TypeError):
                new_nav = 0

            try:
                old_nav = float(existing[date]) if existing[date] else 0
            except (ValueError, TypeError):
                old_nav = 0

            if not _validate_nav_value(new_nav, old_nav):
                continue

        existing[date] = new_nav_str

    sorted_dates = sorted(existing.keys(), reverse=True)
    result_df = pd.DataFrame([
        {"净值日期": d, "累计净值(分红再投资)": existing[d]}
        for d in sorted_dates
    ])
    if benchmark:
        result_df["组合基准指数"] = benchmark
    elif "组合基准指数" not in result_df.columns:
        result_df["组合基准指数"] = ""
    result_df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    return csv_path


# ===================== 辅助函数 =====================
def _get_cumulative_csv_path(tag: str, fund_name: str) -> str:
    """返回累计净值 CSV 的文件路径（不检查是否存在）"""
    safe_name = safe_filename(fund_name)
    fund_dir = os.path.join(config.CUMULATIVE_BASE_DIR, tag, safe_name)
    return os.path.join(fund_dir, f"{safe_name}.csv")


def cumulative_csv_exists(tag: str, fund_name: str) -> bool:
    """检查某个基金的累计净值 CSV 是否已存在"""
    return os.path.exists(_get_cumulative_csv_path(tag, fund_name))
