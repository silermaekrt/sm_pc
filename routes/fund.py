# -*- coding: utf-8 -*-
"""
routes/fund.py - 基金数据 API 路由
"""

import logging
from flask import Blueprint, jsonify, request
from urllib.parse import unquote
from datetime import datetime

from models import db, Fund, CrawlRecord

logger = logging.getLogger(__name__)
fund_bp = Blueprint("fund", __name__)


@fund_bp.route("/funds", methods=["GET"])
def get_funds():
    """
    获取基金列表（分页 + 搜索）

    Query Parameters:
        page: 页码（默认 1）
        per_page: 每页数量（默认 20）
        search: 搜索关键词（基金名称）
        crawl_date: 爬取日期筛选
        sort: 排序字段（默认 crawl_time）
        order: 排序方向（asc/desc，默认 desc）
    """
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    search = request.args.get("search", "", type=str)
    crawl_date = request.args.get("crawl_date", "", type=str)
    sort = request.args.get("sort", "crawl_time", type=str)
    order = request.args.get("order", "desc", type=str)

    per_page = min(per_page, 100)

    query = Fund.query

    if search:
        query = query.filter(Fund.fund_name.contains(search))

    if crawl_date:
        query = query.filter(Fund.crawl_date == crawl_date)

    if hasattr(Fund, sort):
        sort_column = getattr(Fund, sort)
        if order == "asc":
            query = query.order_by(sort_column.asc())
        else:
            query = query.order_by(sort_column.desc())

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        "items": [f.to_dict() for f in pagination.items],
        "total": pagination.total,
        "page": page,
        "per_page": per_page,
        "pages": pagination.pages,
    })


@fund_bp.route("/funds/latest", methods=["GET"])
def get_latest_funds():
    """获取最新一批基金数据（用于大屏展示）"""
    subquery = db.session.query(
        Fund.fund_name,
        db.func.max(Fund.crawl_date).label("max_date")
    ).group_by(Fund.fund_name).subquery()

    funds = Fund.query.join(
        subquery,
        db.and_(
            Fund.fund_name == subquery.c.fund_name,
            Fund.crawl_date == subquery.c.max_date
        )
    ).all()

    return jsonify({
        "items": [f.to_dict() for f in funds],
        "total": len(funds),
    })


@fund_bp.route("/fund/<fund_name>", methods=["GET"])
def get_fund_detail(fund_name):
    """获取单个基金的详细历史数据"""
    fund_name = unquote(fund_name)

    records = Fund.query.filter(
        Fund.fund_name == fund_name
    ).order_by(Fund.crawl_time.desc()).all()

    if not records:
        return jsonify({"error": "基金不存在"}), 404

    return jsonify({
        "fund_name": fund_name,
        "records": [r.to_dict() for r in records],
        "total": len(records),
    })


@fund_bp.route("/stats/summary", methods=["GET"])
def get_stats_summary():
    """获取统计摘要"""
    total_funds = db.session.query(
        db.func.count(db.func.distinct(Fund.fund_name))
    ).scalar()

    total_crawls = CrawlRecord.query.count()

    latest_crawl = CrawlRecord.query.order_by(
        CrawlRecord.start_time.desc()
    ).first()

    today = datetime.now().strftime("%Y%m%d")
    today_crawl = CrawlRecord.query.filter(
        CrawlRecord.crawl_date == today
    ).first()

    return jsonify({
        "total_funds": total_funds or 0,
        "total_crawls": total_crawls or 0,
        "latest_crawl": latest_crawl.to_dict() if latest_crawl else None,
        "today_crawl": today_crawl.to_dict() if today_crawl else None,
    })


@fund_bp.route("/health", methods=["GET"])
def health_check():
    """健康检查接口"""
    return jsonify({"status": "ok", "timestamp": datetime.now().isoformat()})
