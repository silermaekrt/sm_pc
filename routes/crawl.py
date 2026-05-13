# -*- coding: utf-8 -*-
"""
routes/crawl.py - 爬取 API

POST /api/crawl       - 统一爬取入口
GET  /api/crawl/tags  - 获取可用标签
GET  /api/crawl/records - 爬取记录列表
GET  /api/crawl/status  - 爬虫运行状态
"""

import threading
from flask import Blueprint, jsonify, request
from app_logging import get_logger

from config import ALL_TAG_KEYS, FUND_TYPES
from config.crawler import BATCH_WAIT_BETWEEN
from app_state import get_crawl_status as _get_crawl_status, set_crawl_status as _set_crawl_status
from services.csv_store import get_crawl_records, delete_crawl_records as _delete_crawl_records
from utils.http import json_error as _error

logger = get_logger(__name__)
crawl_bp = Blueprint("crawl", __name__)


# ==================== 统一爬取入口 ====================
@crawl_bp.route("/crawl", methods=["POST"])
def crawl():
    """POST /api/crawl"""
    if _get_crawl_status()["is_running"]:
        status = _get_crawl_status()
        return jsonify({
            "status": "running",
            "message": "爬虫正在运行中，请稍后再试",
            "last_crawl": status["last_crawl"],
        }), 409

    body = request.json or {}
    raw_tags = body.get("tags", ["private"])
    if isinstance(raw_tags, str):
        raw_tags = [raw_tags]

    invalid = [t for t in raw_tags if t not in ALL_TAG_KEYS]
    if invalid:
        return _error(f"不支持的标签: {invalid}，可选: {ALL_TAG_KEYS}")

    tags_to_crawl = raw_tags or [t["key"] for t in FUND_TYPES]

    _crawl_async(tags_to_crawl)
    return jsonify({
        "status": "started",
        "message": "爬取已在后台启动",
        "tags": tags_to_crawl, "sync": False,
    })


def _crawl_async(tags: list[str]):
    def _run(app, tags):
        with app.app_context():
            from tasks.crawl_task import run_crawl_task
            from app_state import set_crawl_status as _set, get_crawl_status as _get

            current = _get()
            if current["is_running"]:
                logger.info("[异步爬取] 爬虫已在运行中，跳过此次请求")
                return

            _set(is_running=True)
            try:
                for tag in tags:
                    try:
                        run_crawl_task(use_ocr=True, app=app, tag=tag)
                    except Exception as e:
                        logger.error(f"[异步爬取] 标签={tag} 失败: {e}")
            finally:
                _set(is_running=False)

    from flask import current_app
    thread = threading.Thread(target=_run, args=(current_app._get_current_object(), tags))
    thread.daemon = True
    thread.start()


# ==================== 标签列表 ====================
@crawl_bp.route("/crawl/tags", methods=["GET"])
def get_tags():
    return jsonify({"status": "success", "tags": [{"key": t["key"], "name": t["name"]} for t in FUND_TYPES]})


# ==================== 爬取记录列表 ====================
@crawl_bp.route("/crawl/records", methods=["GET"])
def get_crawl_records_page():
    page = request.args.get("page", 1, type=int)
    per_page = min(100, max(1, request.args.get("per_page", 10, type=int)))
    tag = request.args.get("tag", "", type=str).strip()

    result = get_crawl_records(tag=tag, page=page, per_page=per_page)
    return jsonify({"status": "success", **result})


@crawl_bp.route("/crawl/records", methods=["DELETE"])
def delete_crawl_records_api():
    """DELETE /api/crawl/records  Body: {"ids": [1, 2, 3]}"""
    body = request.json or {}
    ids = body.get("ids", [])
    if not ids:
        return _error("缺少 ids 参数")
    deleted = _delete_crawl_records([str(i) for i in ids])
    return jsonify({"status": "success", "deleted": deleted})


# ==================== 爬虫状态 ====================
@crawl_bp.route("/crawl/status", methods=["GET"])
def get_crawl_status():
    status = _get_crawl_status()
    return jsonify({
        "status": "success",
        "is_running": status["is_running"],
        "last_crawl": status["last_crawl"],
        "last_error": status["last_error"],
    })


# ==================== 累计净值批量爬取 ====================
@crawl_bp.route("/crawl/cumulative", methods=["POST"])
def crawl_cumulative_api():
    """
    POST /api/crawl/cumulative
    对指定标签下的所有基金爬取历史累计净值。

    Body: {
        "tags": ["private", "exp"],
        "batch_size": 5,              # 每批几个基金
        "wait_between_batches": 300  # 批次间等待秒数（默认从配置读取）
    }
    """
    if _get_crawl_status()["is_running"]:
        status = _get_crawl_status()
        return jsonify({
            "status": "running",
            "message": "爬虫正在运行中，请稍后再试",
            "last_crawl": status["last_crawl"],
        }), 409

    body = request.json or {}
    raw_tags = body.get("tags", ["private"])
    if isinstance(raw_tags, str):
        raw_tags = [raw_tags]

    invalid = [t for t in raw_tags if t not in ALL_TAG_KEYS]
    if invalid:
        return _error(f"不支持的标签: {invalid}，可选: {ALL_TAG_KEYS}")

    batch_size = body.get("batch_size", 5)
    wait_between = body.get("wait_between_batches", BATCH_WAIT_BETWEEN)

    _crawl_cumulative_async(raw_tags, batch_size=batch_size, wait_between=wait_between)
    return jsonify({
        "status": "started",
        "message": f"累计净值爬取已在后台启动（每批 {batch_size} 个，批次间等待 {wait_between}s）",
        "tags": raw_tags,
        "batch_size": batch_size,
        "wait_between_batches": wait_between,
    })


def _crawl_cumulative_async(tags: list[str], batch_size: int = 5, wait_between: int = BATCH_WAIT_BETWEEN):
    def _run(app, tags, batch_size, wait_between):
        with app.app_context():
            from tasks.crawl_task import run_cumulative_task
            from app_state import set_crawl_status as _set, get_crawl_status as _get
            import time

            current = _get()
            if current["is_running"]:
                logger.info("[异步累计净值] 爬虫已在运行中，跳过此次请求")
                return

            _set(is_running=True)
            try:
                for tag in tags:
                    try:
                        # 顺序执行该标签下所有批次
                        run_cumulative_task(
                            app=app,
                            tag=tag,
                            batch_size=batch_size,
                            wait_between=wait_between,
                            # 不在这里传 batch_index，由 run_cumulative_task 内部自动递进
                        )
                    except Exception as e:
                        logger.error(f"[异步累计净值] 标签={tag} 失败: {e}")
            finally:
                _set(is_running=False)

    from flask import current_app
    thread = threading.Thread(
        target=_run,
        args=(current_app._get_current_object(), tags, batch_size, wait_between),
    )
    thread.daemon = True
    thread.start()


# ==================== 单基金累计净值爬取 ====================
@crawl_bp.route("/crawl/fund", methods=["POST"])
def crawl_single_fund_api():
    """
    POST /api/crawl/fund
    对单个基金爬取其历史累计净值。
    Body: {"tag": "private", "fund_name": "xxx"}
    """
    if _get_crawl_status()["is_running"]:
        status = _get_crawl_status()
        return jsonify({
            "status": "running",
            "message": "爬虫正在运行中，请稍后再试",
            "last_crawl": status["last_crawl"],
        }), 409

    try:
        body = request.get_json(silent=True) or {}
    except Exception:
        body = {}

    # 优先从查询参数获取，body 仅作备用
    tag = request.args.get("tag", body.get("tag", "private"))
    fund_name = request.args.get("fund_name", body.get("fund_name", ""))

    if tag not in ALL_TAG_KEYS:
        return _error(f"不支持的标签 '{tag}'，可选: {ALL_TAG_KEYS}")
    if not fund_name:
        return _error("缺少参数 fund_name")

    _crawl_single_fund_async(tag, fund_name)
    return jsonify({
        "status": "started",
        "message": f"正在后台爬取 {fund_name} 的累计净值...",
        "fund_name": fund_name,
        "tag": tag,
    })


def _crawl_single_fund_async(tag: str, fund_name: str):
    from services.csv_store import _CrawlRecordContext as _RecordCtx

    def _run(app, tag, fund_name):
        with app.app_context():
            from services.crawler.runner import crawl_single_fund
            from app_logging import get_logger as _get_logger

            ctx = _RecordCtx(tag, f"单基金爬取 {fund_name}")
            try:
                with ctx:
                    logger.info(f"[单基金爬取 {ctx.record_id}] 开始，标签={tag}，基金={fund_name}")
                    r = crawl_single_fund(tag, fund_name)
                    if r["success"]:
                        ctx.update_success(total=1, ocr=r["ocr_count"])
                        logger.info(f"[单基金爬取 {ctx.record_id}] 成功，基金={fund_name}，OCR {r['ocr_count']} 条")
                    else:
                        ctx.update_failed(r["error"] or "未知错误")
                        logger.warning(f"[单基金爬取 {ctx.record_id}] 失败: {r['error']}")
            except Exception as e:
                logger.error(f"[单基金爬取 {ctx.record_id}] 异常: {e}")
                ctx.update_failed(str(e))

    from flask import current_app
    thread = threading.Thread(target=_run, args=(current_app._get_current_object(), tag, fund_name))
    thread.daemon = True
    thread.start()
