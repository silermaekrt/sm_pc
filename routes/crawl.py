# -*- coding: utf-8 -*-
"""
routes/crawl.py - 爬虫任务 API 路由
"""

import logging
import threading
from flask import Blueprint, jsonify, request

from app_state import crawl_status
from models import CrawlRecord

logger = logging.getLogger(__name__)
crawl_bp = Blueprint("crawl", __name__)


@crawl_bp.route("/crawl/trigger", methods=["POST"])
def trigger_crawl():
    """
    触发爬虫抓取任务。
    在后台线程中运行，不阻塞 HTTP 请求。
    """
    if crawl_status["is_running"]:
        return jsonify({
            "status": "running",
            "message": "爬虫正在运行中，请稍后再试",
            "last_crawl": crawl_status["last_crawl"]
        }), 409

    use_ocr = request.json.get("use_ocr", True) if request.json else True

    def _run(app, use_ocr):
        from tasks.crawl_task import run_crawl_task
        run_crawl_task(use_ocr=use_ocr, app=app)

    from flask import current_app
    app = current_app._get_current_object()
    thread = threading.Thread(target=_run, args=(app, use_ocr))
    thread.daemon = True
    thread.start()

    return jsonify({
        "status": "started",
        "message": "爬虫已在后台启动",
        "use_ocr": use_ocr,
    })


@crawl_bp.route("/crawl/status", methods=["GET"])
def get_crawl_status():
    """获取爬虫运行状态"""
    return jsonify({
        "is_running": crawl_status["is_running"],
        "last_crawl": crawl_status["last_crawl"],
        "last_error": crawl_status["last_error"],
    })


@crawl_bp.route("/crawl/records", methods=["GET"])
def get_crawl_records():
    """获取爬取记录列表"""
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 10, type=int)

    pagination = CrawlRecord.query.order_by(
        CrawlRecord.start_time.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        "items": [r.to_dict() for r in pagination.items],
        "total": pagination.total,
        "page": page,
        "pages": pagination.pages,
    })
