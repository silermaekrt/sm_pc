# -*- coding: utf-8 -*-
"""
routes/fund.py - 基金数据 API

全部改用 DataService 统一数据访问层。
"""

import os
from datetime import datetime
from urllib.parse import unquote

from flask import Blueprint, jsonify, request

import config
from config import ALL_TAG_KEYS, FUND_TYPES
from services import DataService
from services.period_stats import BENCHMARK_CODE_MAP
from utils.http import json_error as _error
from routes._shared import tag_summary as _tag_summary

from app_logging import get_logger
logger = get_logger(__name__)

fund_bp = Blueprint("fund", __name__)


# ===================== 基金列表 API =====================

@fund_bp.route("/funds", methods=["GET"])
def get_funds():
    """获取基金列表（分页 + 搜索 + 排序）"""
    tag = request.args.get("tag", "private", type=str)
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 20, type=int), 100)
    search = request.args.get("fund_name", "", type=str)
    sort = request.args.get("sort", "crawl_time", type=str)
    order = request.args.get("order", "desc", type=str)

    if tag not in ALL_TAG_KEYS:
        return _error(f"不支持的标签 '{tag}'，可选: {ALL_TAG_KEYS}")

    result = DataService.get_all_funds(
        tag=tag, page=page, per_page=per_page,
        search=search, sort=sort, order=order,
        crawl_date=request.args.get("crawl_date", "", type=str),
    )
    return jsonify(result)


@fund_bp.route("/funds/latest", methods=["GET"])
def get_latest_funds():
    """获取每个基金的最新一条记录（支持搜索、排序、分页）"""
    tag = request.args.get("tag", "private", type=str)
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 20, type=int), 100)
    search = request.args.get("fund_name", "", type=str)
    sort = request.args.get("sort", "crawl_time", type=str)
    order = request.args.get("order", "desc", type=str)

    if tag not in ALL_TAG_KEYS:
        return _error(f"不支持的标签 '{tag}'，可选: {ALL_TAG_KEYS}")

    result = DataService.get_latest_funds(
        tag=tag, page=page, per_page=per_page,
        search=search, sort=sort, order=order,
    )
    return jsonify(result)


@fund_bp.route("/funds/global-min-date", methods=["GET"])
def get_global_min_date():
    """返回所有 cumulative 基金中最早的净值日期"""
    earliest = DataService.get_global_min_date()
    return jsonify({"global_min_date": earliest})


@fund_bp.route("/funds/cumulative-list", methods=["GET"])
def get_cumulative_funds():
    """返回 cumulative/ 目录下所有基金列表"""
    items = DataService.get_cumulative_fund_list()
    return jsonify({"items": items})


@fund_bp.route("/funds/benchmarks", methods=["GET"])
def get_benchmarks():
    """返回支持的基准指数列表"""
    return jsonify({
        "benchmarks": [{"name": name, "code": code} for name, code in BENCHMARK_CODE_MAP.items()]
    })


@fund_bp.route("/funds/dates", methods=["GET"])
def get_fund_dates():
    """返回指定 tag 或基金在 data/ 中可用的日期范围"""
    tag = request.args.get("tag", "private", type=str)
    fund_name = request.args.get("fund_name", "", type=str).strip()

    if tag not in ALL_TAG_KEYS:
        return _error(f"不支持的标签 '{tag}'，可选: {ALL_TAG_KEYS}")

    if fund_name:
        result = DataService.get_fund_dates(tag, fund_name)
    else:
        result = DataService.get_data_date_range(tag)

    return jsonify(result)


@fund_bp.route("/fund/<fund_name>", methods=["GET"])
def get_fund_detail(fund_name):
    """获取单个基金的完整历史快照（支持分页）"""
    fund_name = unquote(fund_name)
    tag = request.args.get("tag", "private", type=str)
    page = request.args.get("page", 1, type=int)
    per_page = min(100, max(1, request.args.get("per_page", 20, type=int)))

    if tag not in ALL_TAG_KEYS:
        return _error(f"不支持的标签 '{tag}'，可选: {ALL_TAG_KEYS}")

    result = DataService.get_fund_history(tag=tag, fund_name=fund_name, page=page, per_page=per_page)
    if result["total"] == 0:
        return _error("基金不存在", 404)
    return jsonify(result)


@fund_bp.route("/stats/summary", methods=["GET"])
def get_stats_summary():
    """获取统计摘要"""
    tag = request.args.get("tag", "", type=str).strip()
    if tag:
        if tag not in ALL_TAG_KEYS:
            return _error(f"不支持的标签 '{tag}'，可选: {ALL_TAG_KEYS}")
        summaries = [_tag_summary(tag)]
    else:
        summaries = [_tag_summary(t["key"]) for t in FUND_TYPES]

    return jsonify({"summaries": summaries})


# ===================== 时序数据 API =====================

@fund_bp.route("/funds/timeseries", methods=["GET"])
def get_fund_timeseries():
    """获取指定基金在时间范围内的历史净值数据"""
    tag = request.args.get("tag", "private", type=str)
    fund_name = unquote(request.args.get("fund_name", "", type=str))
    start_date = request.args.get("start", "", type=str).strip()
    end_date = request.args.get("end", "", type=str).strip()
    benchmark_override = request.args.get("benchmark", "", type=str).strip()

    if tag not in ALL_TAG_KEYS:
        return _error(f"不支持的标签 '{tag}'，可选: {ALL_TAG_KEYS}")
    if not fund_name:
        return _error("缺少参数 fund_name")

    # 日期校验
    if start_date and end_date:
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
            diff_days = (end_dt - start_dt).days
            if diff_days < 0:
                return _error("开始日期不能晚于结束日期")
            if diff_days > 62:
                return _error("时间区间最长为两个月（约62天）")
        except ValueError:
            return _error("日期格式错误，请使用 YYYY-MM-DD 格式")

    result = DataService.get_fund_timeseries(
        tag=tag,
        fund_name=fund_name,
        start_date=start_date,
        end_date=end_date,
        benchmark_override=benchmark_override,
    )

    if "error" in result:
        return _error(result["error"])

    return jsonify(result)


# ===================== 风险指标 API =====================

@fund_bp.route("/funds/risk-metrics", methods=["GET"])
def get_fund_risk_metrics():
    """计算指定基金在区间内的风险指标"""
    tag = request.args.get("tag", "private", type=str)
    fund_name = unquote(request.args.get("fund_name", "", type=str))
    start_date = request.args.get("start", "", type=str).strip()
    end_date = request.args.get("end", "", type=str).strip()
    rf = request.args.get("rf", 0.03, type=float)
    benchmark_override = request.args.get("benchmark", "", type=str).strip()

    if tag not in ALL_TAG_KEYS:
        return _error(f"不支持的标签 '{tag}'，可选: {ALL_TAG_KEYS}")
    if not fund_name:
        return _error("缺少参数 fund_name")

    result = DataService.compute_risk_metrics(
        tag=tag,
        fund_name=fund_name,
        start_date=start_date,
        end_date=end_date,
        rf=rf,
        benchmark_override=benchmark_override,
    )

    if "error" in result:
        return _error(result["error"])

    return jsonify(result)


# ===================== 健康检查 =====================

@fund_bp.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "ok", "timestamp": datetime.now().isoformat()})
