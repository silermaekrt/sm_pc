# -*- coding: utf-8 -*-
"""
routes/fund.py - 基金数据 API
"""

from datetime import datetime, date as date_type
from urllib.parse import unquote

from flask import Blueprint, jsonify, request
from app_logging import get_logger

from config import ALL_TAG_KEYS, FUND_TYPES
from models import db, Fund, CrawlRecord

logger = get_logger(__name__)
fund_bp = Blueprint("fund", __name__)


def _error(message: str, status_code: int = 400):
    return jsonify({"status": "error", "message": message}), status_code


def _tag_summary(t: str) -> dict:
    """构建单个标签的统计摘要"""
    total = db.session.query(db.func.count(db.func.distinct(Fund.fund_name))).filter(Fund.tag == t).scalar() or 0
    latest = CrawlRecord.query.filter(
        CrawlRecord.tag == t, CrawlRecord.status == "success"
    ).order_by(CrawlRecord.end_time.desc()).first()
    return {
        "tag": t,
        "tag_name": next((x["name"] for x in FUND_TYPES if x["key"] == t), t),
        "total_funds": total,
        "latest_crawl": latest.to_dict() if latest else None,
    }


@fund_bp.route("/funds", methods=["GET"])
def get_funds():
    """获取基金列表（分页 + 搜索 + 排序）"""
    tag = request.args.get("tag", "private", type=str)
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 20, type=int), 100)
    search = request.args.get("name", "", type=str)
    fund_code = request.args.get("code", "", type=str)
    crawl_date = request.args.get("date", "", type=str)
    sort = request.args.get("sort", "crawl_time", type=str)
    order = request.args.get("order", "desc", type=str)

    if tag not in ALL_TAG_KEYS:
        return _error(f"不支持的标签 '{tag}'，可选: {ALL_TAG_KEYS}")

    query = Fund.query.filter(Fund.tag == tag)
    if search:
        query = query.filter(Fund.fund_name.contains(search))
    if fund_code:
        query = query.filter(Fund.fund_code == fund_code)
    if crawl_date:
        try:
            query = query.filter(Fund.crawl_date == date_type.fromisoformat(crawl_date))
        except ValueError:
            pass

    if hasattr(Fund, sort):
        sort_col = getattr(Fund, sort)
        query = query.order_by(sort_col.asc() if order == "asc" else sort_col.desc())

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
    """获取每个基金的最新一条记录（支持搜索、排序、分页）"""
    tag = request.args.get("tag", "private", type=str)
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 20, type=int), 100)
    search = request.args.get("name", "", type=str)
    sort = request.args.get("sort", "crawl_time", type=str)
    order = request.args.get("order", "desc", type=str)

    if tag not in ALL_TAG_KEYS:
        return _error(f"不支持的标签 '{tag}'，可选: {ALL_TAG_KEYS}")

    # 子查询：每个基金的最大日期
    subq = db.session.query(
        Fund.fund_name, db.func.max(Fund.crawl_date).label("max_date")
    ).filter(Fund.tag == tag).group_by(Fund.fund_name).subquery()

    # 基础查询：取每个基金最新日期的记录
    query = Fund.query.join(subq, db.and_(
        Fund.fund_name == subq.c.fund_name,
        Fund.crawl_date == subq.c.max_date,
        Fund.tag == tag
    ))

    # 搜索
    if search:
        query = query.filter(Fund.fund_name.contains(search))

    # 排序
    if hasattr(Fund, sort):
        sort_col = getattr(Fund, sort)
        query = query.order_by(sort_col.asc() if order == "asc" else sort_col.desc())

    # 分页
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        "tag": tag,
        "items": [f.to_dict() for f in pagination.items],
        "total": pagination.total,
        "page": page,
        "per_page": per_page,
        "pages": pagination.pages,
    })


@fund_bp.route("/fund/<fund_name>", methods=["GET"])
def get_fund_detail(fund_name):
    """获取单个基金的完整历史数据"""
    fund_name = unquote(fund_name)
    tag = request.args.get("tag", "private", type=str)
    if tag not in ALL_TAG_KEYS:
        return _error(f"不支持的标签 '{tag}'，可选: {ALL_TAG_KEYS}")

    records = Fund.query.filter(
        Fund.tag == tag, Fund.fund_name == fund_name
    ).order_by(Fund.crawl_time.desc()).all()

    if not records:
        return _error("基金不存在", 404)

    return jsonify({
        "tag": tag, "fund_name": fund_name,
        "records": [r.to_dict() for r in records], "total": len(records),
    })


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

    total_crawls = CrawlRecord.query.count()
    return jsonify({"summaries": summaries, "total_crawls": total_crawls})


@fund_bp.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "ok", "timestamp": datetime.now().isoformat()})
