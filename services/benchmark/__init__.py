# -*- coding: utf-8 -*-
"""
services/benchmark/__init__.py - 基准指数服务层

职责：
  - 扫描 indices/ 文件夹，发现所有可用的指数
  - 读取指定指数的 CSV 历史数据
  - 与基金净值按日期对齐
"""

import os
from datetime import datetime

import pandas as pd

import config


def scan_indices() -> list[dict]:
    """
    扫描 indices/ 目录，返回所有可用指数列表。

    Returns:
        [{"code": "sh000300", "name": "沪深300", "path": "..."}, ...]
    """
    indices_base = str(config.INDICES_BASE_DIR)
    if not os.path.isdir(indices_base):
        return []

    results = []
    for entry in os.scandir(indices_base):
        if not entry.is_dir():
            continue
        index_code = entry.name
        csv_path = os.path.join(entry.path, f"{index_code}.csv")
        if os.path.exists(csv_path):
            # 尝试从 CSV 第一行读取中文名称（如果有的话）
            display_name = index_code
            try:
                header = pd.read_csv(csv_path, nrows=0, dtype=str, encoding="utf-8-sig")
                cols = header.columns.tolist()
                if len(cols) >= 3:
                    display_name = cols[2]
                elif len(cols) == 1:
                    display_name = cols[0]
            except Exception:
                pass
            results.append({
                "code": index_code,
                "name": display_name,
                "path": csv_path,
            })
    return results


def load_index_csv(index_code: str) -> pd.DataFrame | None:
    """
    加载指定指数的 CSV 数据，按日期升序排列。

    Args:
        index_code: 指数代码，如 "sh000300"

    Returns:
        DataFrame，包含 净值日期 / 累计净值(分红再投资) 列；失败返回 None
    """
    index_csv = os.path.join(str(config.INDICES_BASE_DIR), index_code, f"{index_code}.csv")
    if not os.path.exists(index_csv):
        return None

    try:
        df = pd.read_csv(index_csv, dtype=str, keep_default_na=False)
    except Exception:
        return None

    if df.empty or "净值日期" not in df.columns:
        return None

    df["_sort_date"] = pd.to_datetime(df["净值日期"], errors="coerce")
    df = df.dropna(subset=["_sort_date"])
    df = df.sort_values("_sort_date")
    return df


def align_index_to_fund_dates(
    index_df: pd.DataFrame, fund_dates: list[str]
) -> list[str | None]:
    """
    将指数净值按基金日期轴对齐，返回对齐后的指数值列表。

    对齐策略：
      - 基金日期在指数中有对应日期 → 直接取值
      - 基金日期早于指数最早日期 → 用指数首日值填充
      - 基金日期晚于指数最新日期 → 用指数末日值填充
      - 基金日期在指数两个日期之间 → 用最近的前一日指数值填充（forward fill）

    Args:
        index_df: load_index_csv() 返回的 DataFrame，按日期升序
        fund_dates: 基金净值日期列表（字符串，YYYY-MM-DD）

    Returns:
        对齐后的指数净值列表，长度与 fund_dates 一致
    """
    if index_df is None or index_df.empty:
        return [None] * len(fund_dates)

    nav_col = "累计净值(分红再投资)"
    if nav_col not in index_df.columns:
        return [None] * len(fund_dates)

    index_dates = index_df["净值日期"].tolist()
    index_values = index_df[nav_col].tolist()

    result = []
    for fund_date in fund_dates:
        try:
            fd = datetime.strptime(fund_date, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            result.append(None)
            continue

        # 找 <= fund_date 的最近指数日期
        matched_val = None
        for id_, iv_ in zip(reversed(index_dates), reversed(index_values)):
            try:
                if datetime.strptime(id_, "%Y-%m-%d").date() <= fd:
                    matched_val = iv_
                    break
            except (ValueError, TypeError):
                continue

        result.append(matched_val)

    return result


def get_index_info(index_code: str) -> dict | None:
    """
    获取指定指数的基本信息（名称、数据范围）。
    """
    index_df = load_index_csv(index_code)
    if index_df is None:
        return None

    dates = index_df["净值日期"].tolist()
    name = index_code
    if len(dates) >= 3:
        # 尝试从第3列读名称
        try:
            name = str(index_df.iloc[0]["组合基准指数"]) if "组合基准指数" in index_df.columns else index_code
        except Exception:
            name = index_code

    return {
        "code": index_code,
        "name": name,
        "start_date": dates[0] if dates else None,
        "end_date": dates[-1] if dates else None,
        "record_count": len(dates),
    }
