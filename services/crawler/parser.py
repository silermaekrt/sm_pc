# -*- coding: utf-8 -*-
"""
services/crawler/parser.py - 页面数据解析

职责：单元格解析（名称、净值变动、本周/上周）、表格行解析
"""

import re

import config
from config import COL, MIN_COLUMNS, CODE_PATTERN


# ===================== 单元格解析 =====================
def parse_name_cell(text: str) -> tuple:
    """解析基金名称单元格，返回 (基金名称, 基金代码, 策略)"""
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    fund_name = lines[0] if lines else ""
    fund_code = ""
    strategy = ""
    for line in lines[1:]:
        if CODE_PATTERN.match(line):
            fund_code = line
        elif line and len(line) < 20:
            strategy = line
    return fund_name, fund_code, strategy


def parse_change_cell(text: str) -> tuple:
    """解析净值变动单元格，返回 (变动值, 对比日期)"""
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    return (lines[0] if lines else "", lines[1] if len(lines) > 1 else "")


def parse_week_cell(text: str) -> tuple:
    """解析本周/上周单元格，返回 (值, 日期区间)"""
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    return (lines[0] if lines else "", lines[1] if len(lines) > 1 else "")


# ===================== 基金数据解析 =====================
def parse_funds(rows_data: list, ocr_results: dict) -> tuple:
    """
    解析基金行数据，合并 OCR 净值结果。
    返回 (funds list, parse_errors list)
    """
    if not rows_data:
        raise ValueError("未找到任何基金行数据")

    funds = []
    parse_errors = []

    for idx, row in enumerate(rows_data):
        if len(row) < MIN_COLUMNS:
            parse_errors.append(f"行 {idx + 1}: 字段数不足 {len(row)} < {MIN_COLUMNS}")
            continue

        fund_name, fund_code, strategy = parse_name_cell(row[COL.FUND_NAME])
        net_value_date = row[COL.NET_VALUE_DATE].strip()
        net_change, net_change_cmp = parse_change_cell(row[COL.NET_CHANGE])
        annual_return = row[COL.ANNUAL_RETURN].strip()
        this_year = row[COL.THIS_YEAR].strip()
        last_week, last_week_range = parse_week_cell(row[COL.LAST_WEEK])
        one_month = row[COL.ONE_MONTH].strip()
        three_month = row[COL.THREE_MONTH].strip()
        six_month = row[COL.SIX_MONTH].strip()
        one_year = row[COL.ONE_YEAR].strip()
        two_year = row[COL.TWO_YEAR].strip()
        three_year = row[COL.THREE_YEAR].strip()
        five_year = row[COL.FIVE_YEAR].strip()
        since_inception = row[COL.SINCE_INCEPTION].strip()
        this_week, this_week_range = parse_week_cell(row[COL.THIS_WEEK])
        drawdown = row[COL.DRAWDOWN].strip()

        if not fund_name:
            continue

        funds.append({
            "基金名称": fund_name,
            "基金代码": fund_code,
            "策略": strategy,
            "净值日期": net_value_date,
            "最新净值": ocr_results.get(fund_name, ""),
            "净值变动": net_change,
            "净值对比日期": net_change_cmp,
            "成立来年化": annual_return,
            "今年来": this_year,
            "上周": last_week,
            "上周区间": last_week_range,
            "近一月": one_month,
            "近三月": three_month,
            "近半年": six_month,
            "近一年": one_year,
            "近两年": two_year,
            "近三年": three_year,
            "近五年": five_year,
            "成立来": since_inception,
            "本周": this_week,
            "本周区间": this_week_range,
            "回撤": drawdown,
        })

    return funds, parse_errors


# ===================== 数据预览 =====================
def print_preview(df):
    """打印数据预览（前5条）"""
    print("\n=== 数据预览（前5条）===")
    preview_cols = [
        "基金名称", "基金代码", "策略", "净值日期", "最新净值",
        "净值变动", "今年来", "近一年", "近三年", "成立来", "回撤",
    ]
    available = [c for c in preview_cols if c in df.columns]
    preview_df = df[available].head()

    col_widths = {col: len(col) for col in preview_df.columns}
    for col in preview_df.columns:
        for val in preview_df[col].astype(object).fillna("").astype(str).values:
            display_len = sum(2 if ("\u4e00" <= c <= "\u9fff") else 1 for c in val)
            col_widths[col] = max(col_widths[col], display_len)

    header = "  ".join(col.ljust(col_widths[col]) for col in preview_df.columns)
    sep = "  ".join("-" * col_widths[col] for col in preview_df.columns)
    print(header)
    print(sep)

    for _, row in preview_df.iterrows():
        parts = []
        for col in preview_df.columns:
            val = str(row[col])
            display_len = sum(2 if ("\u4e00" <= c <= "\u9fff") else 1 for c in val)
            parts.append(val.ljust(col_widths[col]))
        print("  ".join(parts))


def print_ocr_stats(df):
    """打印 OCR 成功率统计"""
    nv_col = "最新净值"
    if nv_col not in df.columns:
        return
    total = len(df)
    success = sum(1 for v in df[nv_col] if v)
    fail = total - success
    msg = f"\n[OCR 统计] 总行数={total}，成功={success}，失败={fail}，成功率={success/total*100:.1f}%"
    print(msg)
