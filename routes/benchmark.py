# -*- coding: utf-8 -*-
"""
routes/benchmark.py - 基准指数数据 API
"""

import os
from datetime import datetime

from flask import Blueprint, jsonify, request

from config import INDICES_BASE_DIR
from services.benchmark import scan_indices, load_index_csv, get_index_info
from utils.http import json_error as _error

benchmark_bp = Blueprint("benchmark", __name__)


@benchmark_bp.route("/benchmark/list", methods=["GET"])
def list_benchmarks():
    """返回所有已配置的基准指数列表"""
    indices = scan_indices()
    detailed = []
    for idx in indices:
        info = get_index_info(idx["code"]) or {}
        detailed.append({
            "code": idx["code"],
            "name": info.get("name", idx["name"]),
            "start_date": info.get("start_date"),
            "end_date": info.get("end_date"),
            "record_count": info.get("record_count", 0),
        })
    return jsonify({
        "indices": detailed,
        "total": len(detailed),
    })


@benchmark_bp.route("/benchmark/timeseries", methods=["GET"])
def get_benchmark_timeseries():
    """
    获取指定基准指数的时间序列数据。

    Query params:
        code:    指数代码（URL 编码）
        start:   开始日期（YYYY-MM-DD），可选
        end:     结束日期（YYYY-MM-DD），可选
    """
    index_code = request.args.get("code", "", type=str).strip()
    if not index_code:
        return _error("缺少参数 code")

    index_csv = os.path.join(str(INDICES_BASE_DIR), index_code, f"{index_code}.csv")
    if not os.path.exists(index_csv):
        return _error(f"指数 '{index_code}' 数据文件不存在，请先准备数据")

    df = load_index_csv(index_code)
    if df is None or df.empty:
        return _error(f"指数 '{index_code}' 数据读取失败")

    nav_col = "累计净值(分红再投资)"
    if nav_col not in df.columns:
        return _error("指数 CSV 文件格式异常，缺少'累计净值(分红再投资)'列")

    start_date = request.args.get("start", "", type=str).strip()
    end_date = request.args.get("end", "", type=str).strip()

    if start_date:
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            df = df[df["_sort_date"] >= start_dt]
        except ValueError:
            pass

    if end_date:
        try:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
            df = df[df["_sort_date"] <= end_dt]
        except ValueError:
            pass

    if df.empty:
        return _error("指定时间范围内无数据")

    # 日期过滤后才读取数据列
    dates = df["净值日期"].tolist()
    values = df[nav_col].tolist()

    # 尝试读指数名称（放在 CSV 第3列，或直接从路径推断）
    index_name = index_code
    if "组合基准指数" in df.columns:
        first_val = df["组合基准指数"].iloc[0]
        if first_val and str(first_val).strip():
            index_name = str(first_val).strip()

    return jsonify({
        "code": index_code,
        "name": index_name,
        "dates": df["净值日期"].tolist(),
        "values": df[nav_col].tolist(),
    })
