# -*- coding: utf-8 -*-
"""
routes/funds_api.py - run_ocr.py 数据 API 路由（多标签版本）

提供直接调用 run_ocr.py 爬取逻辑并以 JSON 格式返回结果的接口，
支持多标签（私募/公募/货币）爬取与查询。
"""

import logging
import os
from datetime import datetime
from flask import Blueprint, jsonify, request

import config
from config import ALL_TAG_KEYS
from app_state import crawl_status
from models import CrawlRecord

logger = logging.getLogger(__name__)
funds_api_bp = Blueprint("funds_api", __name__)


# ==================== 辅助函数 ====================
def _get_latest_crawl_date(tag: str = "private") -> str | None:
    """从数据库获取指定标签最新成功爬取的日期"""
    record = CrawlRecord.query.filter(
        CrawlRecord.tag == tag,
        CrawlRecord.status == "success",
    ).order_by(CrawlRecord.end_time.desc()).first()
    if record:
        return record.crawl_date.strftime("%Y-%m-%d")
    return None


def _csv_path_for_tag(tag: str, crawl_date: str | None = None) -> str:
    """获取指定标签的 CSV 文件路径（data/YYYYMMDD/{tag}.csv）"""
    date_str = (crawl_date or datetime.now().strftime("%Y%m%d")).replace("-", "")
    return os.path.join(config.DATA_DIR, date_str, f"{tag}.csv")


# ==================== 获取可用标签列表 ====================
@funds_api_bp.route("/crawl/tags", methods=["GET"])
def get_tags():
    """
    获取所有可用标签列表。

    返回示例:
    {
        "status": "success",
        "tags": [
            {"key": "private", "name": "私募", "url": "..."},
            {"key": "public",  "name": "公募", "url": "..."},
            {"key": "money",   "name": "货币", "url": "..."},
        ]
    }
    """
    return jsonify({
        "status": "success",
        "tags": [{"key": t["key"], "name": t["name"]} for t in config.FUND_TYPES],
    })


# ==================== 触发异步爬取 ====================
@funds_api_bp.route("/crawl", methods=["POST"])
def trigger_ocr_crawl():
    """
    触发 run_ocr.py 爬取流程（后台异步）。

    请求体（可选）:
        use_ocr (bool): 是否启用 OCR，默认 True
        tag (str): 基金标签，默认 "private"

    返回示例:
    {
        "status": "started",
        "message": "爬取已在后台启动",
        "tag": "private",
        "use_ocr": true
    }
    """
    if crawl_status["is_running"]:
        return jsonify({
            "status": "running",
            "message": "爬虫正在运行中，请稍后再试",
            "last_crawl": crawl_status["last_crawl"],
        }), 409

    use_ocr = request.args.get("use_ocr", "true").lower() != "false"
    tag = request.args.get("tag", "private", type=str)
    save_screenshot = request.args.get("save_screenshot", "true").lower() != "false"
    save_debug_crop = request.args.get("save_debug_crop", "true").lower() != "false"

    if request.json:
        use_ocr = request.json.get("use_ocr", use_ocr)
        tag = request.json.get("tag", tag)
        save_screenshot = request.json.get("save_screenshot", save_screenshot)
        save_debug_crop = request.json.get("save_debug_crop", save_debug_crop)

    if tag not in ALL_TAG_KEYS:
        return jsonify({
            "status": "error",
            "message": f"不支持的标签 '{tag}'，可选: {ALL_TAG_KEYS}",
        }), 400

    result_container = {}

    def _run():
        try:
            from run_ocr import crawl
            result = crawl(use_ocr=use_ocr, tag=tag, save_screenshot=save_screenshot, save_debug_crop=save_debug_crop)

            # 读取 CSV 获取完整数据
            import pandas as pd
            csv_path = _csv_path_for_tag(tag)
            if os.path.exists(csv_path):
                df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
                funds = df.to_dict(orient="records")
            else:
                funds = []

            crawl_date = _get_latest_crawl_date(tag)
            if not crawl_date:
                crawl_date = datetime.now().strftime("%Y-%m-%d")

            result_container["status"] = "success"
            result_container["data"] = {
                "total": result.get("total", 0),
                "funds": funds,
                "crawl_date": crawl_date,
                "tag": tag,
                "ocr_stats": {
                    "ocr_success": result.get("ocr_success", 0),
                    "ocr_failed": result.get("ocr_failed", 0),
                    "parse_errors": result.get("parse_errors", 0),
                },
            }
        except Exception as e:
            logger.error(f"OCR 爬取失败: {e}")
            result_container["status"] = "failed"
            result_container["error"] = str(e)

    from flask import current_app
    import threading

    app = current_app._get_current_object()
    thread = threading.Thread(target=_run)
    thread.daemon = True
    thread.start()

    return jsonify({
        "status": "started",
        "message": "爬取已在后台启动，请稍后通过 GET /api/crawl/result 获取结果",
        "tag": tag,
        "use_ocr": use_ocr,
    })


# ==================== 同步爬取（阻塞返回完整 JSON） ====================
@funds_api_bp.route("/crawl/sync", methods=["GET", "POST"])
def crawl_sync():
    """
    同步爬取：阻塞等待爬取完成，直接返回完整 JSON 结果。

    查询参数 / 请求体:
        use_ocr (bool): 是否启用 OCR，默认 True
        tag (str): 基金标签，默认 "private"

    返回示例:
    {
        "status": "success",
        "tag": "private",
        "crawl_date": "2026-04-28",
        "total": 22,
        "funds": [...],
        "ocr_stats": {...}
    }
    """
    if crawl_status["is_running"]:
        return jsonify({
            "status": "running",
            "message": "爬虫正在运行中，请稍后再试",
            "last_crawl": crawl_status["last_crawl"],
        }), 409

    use_ocr = request.args.get("use_ocr", "true").lower() != "false"
    tag = request.args.get("tag", "private", type=str)
    save_screenshot = request.args.get("save_screenshot", "true").lower() != "false"
    save_debug_crop = request.args.get("save_debug_crop", "true").lower() != "false"

    if request.json:
        use_ocr = request.json.get("use_ocr", use_ocr)
        tag = request.json.get("tag", tag)
        save_screenshot = request.json.get("save_screenshot", save_screenshot)
        save_debug_crop = request.json.get("save_debug_crop", save_debug_crop)

    if tag not in ALL_TAG_KEYS:
        return jsonify({
            "status": "error",
            "message": f"不支持的标签 '{tag}'，可选: {ALL_TAG_KEYS}",
        }), 400

    try:
        from run_ocr import crawl

        result = crawl(use_ocr=use_ocr, tag=tag, save_screenshot=save_screenshot, save_debug_crop=save_debug_crop)

        import pandas as pd
        csv_path = _csv_path_for_tag(tag)
        if os.path.exists(csv_path):
            df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
            funds = df.to_dict(orient="records")
        else:
            funds = []

        crawl_date = _get_latest_crawl_date(tag)
        if not crawl_date:
            crawl_date = datetime.now().strftime("%Y-%m-%d")

        return jsonify({
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
        })

    except Exception as e:
        logger.error(f"同步爬取失败: {e}")
        return jsonify({
            "status": "failed",
            "tag": tag,
            "message": str(e),
        }), 500


# ==================== 批量爬取所有标签 ====================
@funds_api_bp.route("/crawl/all", methods=["GET", "POST"])
def crawl_all_tags():
    """
    按配置顺序爬取所有标签（同步，顺序执行）。

    查询参数 / 请求体:
        tags (list): 指定要爬取的标签列表，默认 config.FUND_TYPES 中的全部
        use_ocr (bool): 是否启用 OCR，默认 True

    返回示例:
    {
        "status": "success",
        "results": {
            "private": {"status": "success", "total": 22, "crawl_date": "..."},
            "public":  {"status": "success", "total": 10, "crawl_date": "..."},
            "money":   {"status": "success", "total": 5,  "crawl_date": "..."},
        }
    }
    """
    if crawl_status["is_running"]:
        return jsonify({
            "status": "running",
            "message": "爬虫正在运行中，请稍后再试",
            "last_crawl": crawl_status["last_crawl"],
        }), 409

    use_ocr = request.args.get("use_ocr", "true").lower() != "false"
    save_screenshot = request.args.get("save_screenshot", "true").lower() != "false"
    save_debug_crop = request.args.get("save_debug_crop", "true").lower() != "false"
    tags_to_crawl = [t["key"] for t in config.FUND_TYPES]

    if request.json:
        if request.json.get("tags"):
            tags_to_crawl = request.json["tags"]
        use_ocr = request.json.get("use_ocr", use_ocr)
        save_screenshot = request.json.get("save_screenshot", save_screenshot)
        save_debug_crop = request.json.get("save_debug_crop", save_debug_crop)

    # 校验标签合法性
    invalid = [t for t in tags_to_crawl if t not in ALL_TAG_KEYS]
    if invalid:
        return jsonify({
            "status": "error",
            "message": f"不支持的标签: {invalid}，可选: {ALL_TAG_KEYS}",
        }), 400

    import pandas as pd
    from run_ocr import crawl
    from exceptions import TagNotFoundError

    results = {}
    for tag in tags_to_crawl:
        try:
            result = crawl(
                use_ocr=use_ocr,
                tag=tag,
                save_screenshot=save_screenshot,
                save_debug_crop=save_debug_crop,
            )

            csv_path = _csv_path_for_tag(tag)
            if os.path.exists(csv_path):
                df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
                funds = df.to_dict(orient="records")
            else:
                funds = []

            crawl_date = _get_latest_crawl_date(tag)
            if not crawl_date:
                crawl_date = datetime.now().strftime("%Y-%m-%d")

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
            logger.warning(f"标签 {tag} 未找到，跳过: {e.message}")
            results[tag] = {
                "status": "skipped",
                "tag": tag,
                "message": e.message,
            }
        except Exception as e:
            logger.error(f"标签 {tag} 爬取失败: {e}")
            results[tag] = {
                "status": "failed",
                "tag": tag,
                "message": str(e),
            }

    overall = "success" if all(r.get("status") == "success" for r in results.values()) else "partial"
    return jsonify({
        "status": overall,
        "results": results,
    })


# ==================== 从 CSV 读取基金数据 ====================
@funds_api_bp.route("/funds", methods=["GET"])
def get_funds_from_csv():
    """
    从 run_ocr.py 输出的 CSV 文件中读取基金数据。

    查询参数:
        tag (str): 基金标签，默认 "private"
        date (str): 爬取日期（YYYY-MM-DD），默认最新日期
        search (str): 基金名称搜索关键词（模糊匹配）
        page (int): 页码，默认 1
        page_size (int): 每页数量，默认 50

    返回示例:
    {
        "status": "success",
        "tag": "private",
        "crawl_date": "2026-04-28",
        "total": 22,
        "page": 1,
        "page_size": 50,
        "pages": 1,
        "funds": [...]
    }
    """
    import pandas as pd

    tag = request.args.get("tag", "private", type=str)
    crawl_date = request.args.get("date", "", type=str).strip()
    search = request.args.get("search", "", type=str).strip()
    page = request.args.get("page", 1, type=int)
    page_size = request.args.get("page_size", 50, type=int)

    if page < 1:
        page = 1
    if page_size < 1 or page_size > 200:
        page_size = 50

    if tag not in ALL_TAG_KEYS:
        return jsonify({
            "status": "error",
            "message": f"不支持的标签 '{tag}'，可选: {ALL_TAG_KEYS}",
        }), 400

    if not crawl_date:
        crawl_date = _get_latest_crawl_date(tag)
        if not crawl_date:
            return jsonify({
                "status": "error",
                "message": f"标签 '{tag}' 没有找到任何爬取记录",
                "tag": tag,
            }), 404

    csv_path = _csv_path_for_tag(tag, crawl_date)

    if not os.path.exists(csv_path):
        return jsonify({
            "status": "error",
            "message": f"日期 {crawl_date} 的数据文件不存在",
            "tag": tag,
            "crawl_date": crawl_date,
        }), 404

    try:
        df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    except Exception as e:
        logger.error(f"CSV 读取失败: {e}")
        return jsonify({
            "status": "error",
            "message": f"CSV 文件读取失败: {e}",
        }), 500

    # 搜索过滤
    if search:
        df = df[df["基金名称"].str.contains(search, na=False, case=False)]

    total = len(df)
    start = (page - 1) * page_size
    end = start + page_size
    paginated = df.iloc[start:end]
    funds = paginated.to_dict(orient="records")

    return jsonify({
        "status": "success",
        "tag": tag,
        "crawl_date": crawl_date,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size if total > 0 else 0,
        "funds": funds,
    })
