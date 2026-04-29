# -*- coding: utf-8 -*-
"""
routes/fund.py - 基金数据 API 路由（多标签版本）
"""

import logging
from flask import Blueprint, jsonify, request
from urllib.parse import unquote
from datetime import datetime, date as date_type

import config
from config import ALL_TAG_KEYS, get_tag_model_map
from models import db, Fund, CrawlRecord

logger = logging.getLogger(__name__)
fund_bp = Blueprint("fund", __name__)


def _error(message: str, status_code: int = 400):
    """统一错误响应格式"""
    return jsonify({"status": "error", "message": message}), status_code


def _get_model_for_tag(tag: str):
    """根据 tag 返回对应的 Model，默认为 Fund（私募）"""
    return get_tag_model_map().get(tag, Fund)


@fund_bp.route("/funds", methods=["GET"])
def get_funds():
    """
    获取基金列表（分页 + 搜索）

    Query Parameters:
        tag: 基金标签（private/public/money），默认 private
        page: 页码（默认 1）
        per_page: 每页数量（默认 20）
        search: 搜索关键词（基金名称）
        crawl_date: 爬取日期筛选
        sort: 排序字段（默认 crawl_time）
        order: 排序方向（asc/desc，默认 desc）
    """
    tag = request.args.get("tag", "private", type=str)
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    search = request.args.get("search", "", type=str)
    crawl_date = request.args.get("crawl_date", "", type=str)
    sort = request.args.get("sort", "crawl_time", type=str)
    order = request.args.get("order", "desc", type=str)

    if tag not in ALL_TAG_KEYS:
        return _error(f"不支持的标签 '{tag}'，可选: {ALL_TAG_KEYS}")

    per_page = min(per_page, 100)
    FundModel = _get_model_for_tag(tag)
    query = FundModel.query

    if search:
        query = query.filter(FundModel.fund_name.contains(search))

    if crawl_date:
        try:
            filter_date = date_type.fromisoformat(crawl_date)
            query = query.filter(FundModel.crawl_date == filter_date)
        except ValueError:
            pass

    if hasattr(FundModel, sort):
        sort_column = getattr(FundModel, sort)
        if order == "asc":
            query = query.order_by(sort_column.asc())
        else:
            query = query.order_by(sort_column.desc())

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        "tag": tag,
        "items": [f.to_dict() for f in pagination.items],
        "total": pagination.total,
        "page": page,
        "per_page": per_page,
        "pages": pagination.pages,
    })


@fund_bp.route("/funds/latest", methods=["GET"])
def get_latest_funds():
    """
    获取最新一批基金数据（每个基金取最新一条记录）

    Query Parameters:
        tag: 基金标签（private/public/money），默认 private
    """
    tag = request.args.get("tag", "private", type=str)

    if tag not in ALL_TAG_KEYS:
        return _error(f"不支持的标签 '{tag}'，可选: {ALL_TAG_KEYS}")

    FundModel = _get_model_for_tag(tag)
    subquery = db.session.query(
        FundModel.fund_name,
        db.func.max(FundModel.crawl_date).label("max_date")
    ).group_by(FundModel.fund_name).subquery()

    funds = FundModel.query.join(
        subquery,
        db.and_(
            FundModel.fund_name == subquery.c.fund_name,
            FundModel.crawl_date == subquery.c.max_date
        )
    ).all()

    return jsonify({
        "tag": tag,
        "items": [f.to_dict() for f in funds],
        "total": len(funds),
    })


@fund_bp.route("/fund/<fund_name>", methods=["GET"])
def get_fund_detail(fund_name):
    """
    获取单个基金的详细历史数据

    Query Parameters:
        tag: 基金标签（private/public/money），默认 private
    """
    fund_name = unquote(fund_name)
    tag = request.args.get("tag", "private", type=str)

    if tag not in ALL_TAG_KEYS:
        return _error(f"不支持的标签 '{tag}'，可选: {ALL_TAG_KEYS}")

    FundModel = _get_model_for_tag(tag)
    records = FundModel.query.filter(
        FundModel.fund_name == fund_name
    ).order_by(FundModel.crawl_time.desc()).all()

    if not records:
        return _error("基金不存在", 404)

    return jsonify({
        "tag": tag,
        "fund_name": fund_name,
        "records": [r.to_dict() for r in records],
        "total": len(records),
    })


@fund_bp.route("/stats/summary", methods=["GET"])
def get_stats_summary():
    """
    获取统计摘要（按标签分组）

    Query Parameters:
        tag: 基金标签（可选，不传则返回所有标签汇总）
    """
    tag = request.args.get("tag", "", type=str).strip()

    def _tag_summary(t):
        FundModel = _get_model_for_tag(t)
        total = db.session.query(
            db.func.count(db.func.distinct(FundModel.fund_name))
        ).scalar() or 0
        latest = CrawlRecord.query.filter(
            CrawlRecord.tag == t,
            CrawlRecord.status == "success",
        ).order_by(CrawlRecord.end_time.desc()).first()
        return {
            "tag": t,
            "tag_name": next((x["name"] for x in config.FUND_TYPES if x["key"] == t), t),
            "total_funds": total,
            "latest_crawl": latest.to_dict() if latest else None,
        }

    if tag:
        if tag not in ALL_TAG_KEYS:
            return _error(f"不支持的标签 '{tag}'，可选: {ALL_TAG_KEYS}")
        summaries = [_tag_summary(tag)]
    else:
        summaries = [_tag_summary(t["key"]) for t in config.FUND_TYPES]

    total_crawls = CrawlRecord.query.count()

    return jsonify({
        "summaries": summaries,
        "total_crawls": total_crawls,
    })


@fund_bp.route("/health", methods=["GET"])
def health_check():
    """健康检查接口"""
    return jsonify({"status": "ok", "timestamp": datetime.now().isoformat()})
