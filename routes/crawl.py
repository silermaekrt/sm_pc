# -*- coding: utf-8 -*-
"""
routes/crawl.py - 统一爬取接口

POST /api/crawl              - 统一爬取入口（同步/异步，单个/多个标签）
GET  /api/crawl/tags         - 获取可用标签列表
GET  /api/crawl/records      - 爬取记录列表
GET  /api/crawl/status       - 爬虫运行状态
"""

import logging
import os
import threading
from datetime import datetime
from flask import Blueprint, jsonify, request

import config
from config import ALL_TAG_KEYS
from app_state import crawl_status
from models import db, CrawlRecord

logger = logging.getLogger(__name__)
crawl_bp = Blueprint("crawl", __name__)


def _error(message: str, status_code: int = 400):
    return jsonify({"status": "error", "message": message}), status_code


# ==================== 统一爬取入口 ====================
@crawl_bp.route("/crawl", methods=["POST"])
def crawl():
    """
    统一爬取接口。

    Body 参数:
        tags (list): 标签列表，默认 ["private"]；不传则爬取全部标签
        sync (bool): true=同步阻塞返回结果，false=异步立即返回（默认）

    返回（sync=true 时完整结果，sync=false 时仅状态）:
    """
    if crawl_status["is_running"]:
        return jsonify({
            "status": "running",
            "message": "爬虫正在运行中，请稍后再试",
            "last_crawl": crawl_status["last_crawl"],
        }), 409

    # 解析参数
    body = request.json or {}
    raw_tags = body.get("tags", ["private"])
    if isinstance(raw_tags, str):
        raw_tags = [raw_tags]
    sync = body.get("sync", False)

    # 校验标签
    invalid = [t for t in raw_tags if t not in ALL_TAG_KEYS]
    if invalid:
        return _error(f"不支持的标签: {invalid}，可选: {ALL_TAG_KEYS}")

    tags_to_crawl = raw_tags if raw_tags else [t["key"] for t in config.FUND_TYPES]

    if sync:
        return _crawl_sync(tags_to_crawl)
    else:
        _crawl_async(tags_to_crawl)
        return jsonify({
            "status": "started",
            "message": "爬取已在后台启动",
            "tags": tags_to_crawl,
            "sync": False,
        })


def _crawl_async(tags: list[str]):
    """后台线程执行爬取"""
    def _run(app, tags):
        with app.app_context():
            from tasks.crawl_task import run_crawl_task
            for tag in tags:
                try:
                    run_crawl_task(use_ocr=True, app=app, tag=tag)
                except Exception as e:
                    logger.error(f"[异步爬取] 标签={tag} 失败: {e}")

    from flask import current_app
    app = current_app._get_current_object()
    thread = threading.Thread(target=_run, args=(app, tags))
    thread.daemon = True
    thread.start()


def _crawl_sync(tags: list[str]):
    """同步阻塞爬取，返回完整结果"""
    from run_ocr import crawl as run_crawl
    from exceptions import TagNotFoundError
    import pandas as pd

    results = {}
    for tag in tags:
        try:
            result = run_crawl(tag=tag)
            crawl_date = _get_latest_crawl_date(tag)
            if not crawl_date:
                crawl_date = datetime.now().strftime("%Y-%m-%d")

            csv_path = _csv_path_for_tag(tag, crawl_date)
            if os.path.exists(csv_path):
                df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
                funds = df.to_dict(orient="records")
            else:
                funds = []

            results[tag] = {
                "status": "success",
                "tag": tag,
                "crawl_date": crawl_date,
                "total": result.get("total", len(funds)),
                "funds": funds,
                "ocr_stats": {
                    "ocr_success": result.get("ocr_success", 0),
                    "ocr_failed": result.get("ocr_failed", 0),
                    "parse_errors": result.get("parse_errors", 0),
                },
            }

        except TagNotFoundError as e:
            logger.warning(f"标签 {tag} 未找到: {e.message}")
            results[tag] = {"status": "skipped", "tag": tag, "message": e.message}

        except Exception as e:
            logger.error(f"标签 {tag} 爬取失败: {e}")
            results[tag] = {"status": "failed", "tag": tag, "message": str(e)}

    overall = "success" if all(r.get("status") == "success" for r in results.values()) else "partial"
    return jsonify({"status": overall, "tags": tags, "results": results}), 200


def _csv_path_for_tag(tag: str, crawl_date: str | None = None) -> str:
    date_str = (crawl_date or datetime.now().strftime("%Y%m%d")).replace("-", "")
    return os.path.join(config.DATA_DIR, date_str, f"{tag}.csv")


def _get_latest_crawl_date(tag: str) -> str | None:
    record = CrawlRecord.query.filter(
        CrawlRecord.tag == tag,
        CrawlRecord.status == "success",
    ).order_by(CrawlRecord.end_time.desc()).first()
    if record:
        return record.crawl_date.strftime("%Y-%m-%d")
    return None


# ==================== 获取可用标签 ====================
@crawl_bp.route("/crawl/tags", methods=["GET"])
def get_tags():
    return jsonify({
        "status": "success",
        "tags": [{"key": t["key"], "name": t["name"]} for t in config.FUND_TYPES],
    })


# ==================== 爬取记录列表 ====================
@crawl_bp.route("/crawl/records", methods=["GET"])
def get_crawl_records():
    page = request.args.get("page", 1, type=int)
    per_page = min(100, max(1, request.args.get("per_page", 10, type=int)))
    tag = request.args.get("tag", "", type=str).strip()

    query = CrawlRecord.query
    if tag:
        query = query.filter(CrawlRecord.tag == tag)

    pagination = query.order_by(
        CrawlRecord.start_time.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        "status": "success",
        "items": [r.to_dict() for r in pagination.items],
        "total": pagination.total,
        "page": page,
        "per_page": per_page,
        "pages": pagination.pages,
    })


# ==================== 爬虫运行状态 ====================
@crawl_bp.route("/crawl/status", methods=["GET"])
def get_crawl_status():
    return jsonify({
        "status": "success",
        "is_running": crawl_status["is_running"],
        "last_crawl": crawl_status["last_crawl"],
        "last_error": crawl_status["last_error"],
    })
