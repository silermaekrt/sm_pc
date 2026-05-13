# -*- coding: utf-8 -*-
"""
tasks/crawl_task.py - 爬虫任务函数

职责：
- 执行爬虫并写入 CSV 快照
- 定时爬取调度
"""

import os
from datetime import datetime
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app_logging import get_logger

import config
from config import ALL_TAG_KEYS, SCHEDULED_TAGS, SCHEDULED_CUMULATIVE_TAGS, BATCH_WAIT_BETWEEN
from app_state import crawl_status, set_crawl_status
from exceptions import (
    CookieError,
    PageLoadError,
    ElementNotFoundError,
    TagNotFoundError,
    CrawlFailedError,
)
from services.crawler.runner import crawl, crawl_cumulative_nav
from services.csv_store import save_crawl_record, invalidate_index

logger = get_logger(__name__)

_scheduler: Optional[BackgroundScheduler] = None


def run_crawl_task(use_ocr: bool = True, app=None, tag: str = "private"):
    """
    在后台线程中执行爬虫任务（由调度器调用）。
    app 参数必须由调用方传入，不依赖 current_app LocalProxy。
    tag: 基金标签，默认 "private"
    """
    if tag not in ALL_TAG_KEYS:
        raise ValueError(f"不支持的标签 '{tag}'，可选: {ALL_TAG_KEYS}")
    if app is None:
        raise RuntimeError("app instance must be passed to run_crawl_task")
    with app.app_context():
        _run_crawl_task_inner(use_ocr=use_ocr, tag=tag)


def _run_crawl_task_inner(use_ocr: bool = True, tag: str = "private"):
    """
    爬虫任务内部实现。
    tag: 基金标签，对应 config.FUND_TYPES 中的 key
    """
    global crawl_status

    set_crawl_status(is_running=True, last_error=None)

    now = datetime.now()
    crawl_date_str = now.strftime("%Y-%m-%d")
    crawl_time_str = now.strftime("%Y-%m-%d %H:%M:%S")
    crawl_date_compact = crawl_date_str.replace("-", "")

    # 1. 写入爬取记录（running 状态）
    record_id = save_crawl_record({
        "id": None,
        "tag": tag,
        "crawl_date": crawl_date_str,
        "start_time": crawl_time_str,
        "end_time": "",
        "status": "running",
        "total_funds": 0,
        "ocr_success": 0,
        "error_message": "",
    })

    try:
        logger.info(f"[爬虫任务 {record_id}] 开始执行，标签={tag}...")

        crawl_result = crawl(use_ocr=use_ocr, tag=tag)

        # 2. 统计本次爬取结果
        imported = 0
        ocr_success_count = crawl_result.get("ocr_success", 0)
        csv_path = os.path.join(config.DATA_DIR, crawl_date_compact, f"{tag}.csv")
        if os.path.exists(csv_path):
            try:
                import pandas as pd
                df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
                imported = len(df)
            except Exception:
                imported = 0

        logger.info(f"[爬虫任务 {record_id}] 标签={tag} 完成，"
                    f"data/{crawl_date_compact}/{tag}.csv 含 {imported} 条 "
                    f"(OCR 成功 {ocr_success_count} 条)")

        # 3. 更新爬取记录（success）
        save_crawl_record({
            "id": record_id,
            "tag": tag,
            "crawl_date": crawl_date_str,
            "start_time": crawl_time_str,
            "end_time": crawl_time_str,
            "status": "success",
            "total_funds": imported,
            "ocr_success": ocr_success_count,
            "error_message": "",
        })

        set_crawl_status(last_crawl=crawl_time_str)

        # 爬取成功后使索引失效，下次查询时会自动重建
        invalidate_index(tag)

    except TagNotFoundError as e:
        logger.warning(f"[爬虫任务 {record_id}] 标签 '{tag}' 未找到: {e.message}")
        set_crawl_status(last_error=f"标签 '{tag}' 未找到，请检查标签名称是否正确")
        save_crawl_record({
            "id": record_id, "tag": tag, "crawl_date": crawl_date_str,
            "start_time": crawl_time_str, "end_time": crawl_time_str,
            "status": "skipped", "total_funds": 0, "ocr_success": 0,
            "error_message": e.message,
        })

    except CookieError as e:
        logger.error(f"[爬虫任务 {record_id}] Cookie 错误: {e.message}")
        set_crawl_status(last_error=f"Cookie 错误: {e.message}，请更新 SIMU_COOKIES")
        save_crawl_record({
            "id": record_id, "tag": tag, "crawl_date": crawl_date_str,
            "start_time": crawl_time_str, "end_time": crawl_time_str,
            "status": "failed", "total_funds": 0, "ocr_success": 0,
            "error_message": f"Cookie 错误: {e.message}，请更新 Cookie",
        })

    except PageLoadError as e:
        logger.error(f"[爬虫任务 {record_id}] 页面加载失败: {e.message}")
        set_crawl_status(last_error=f"页面加载失败: {e.message}")
        save_crawl_record({
            "id": record_id, "tag": tag, "crawl_date": crawl_date_str,
            "start_time": crawl_time_str, "end_time": crawl_time_str,
            "status": "failed", "total_funds": 0, "ocr_success": 0,
            "error_message": "页面加载失败，请检查网络连接",
        })

    except ElementNotFoundError as e:
        logger.error(f"[爬虫任务 {record_id}] 页面元素未找到: {e.message}")
        set_crawl_status(last_error=f"页面结构变化: {e.message}")
        save_crawl_record({
            "id": record_id, "tag": tag, "crawl_date": crawl_date_str,
            "start_time": crawl_time_str, "end_time": crawl_time_str,
            "status": "failed", "total_funds": 0, "ocr_success": 0,
            "error_message": "页面结构可能已变化，请更新爬虫代码",
        })

    except CrawlFailedError as e:
        logger.error(f"[爬虫任务 {record_id}] 爬取失败: {e.message}")
        set_crawl_status(last_error=e.message)
        save_crawl_record({
            "id": record_id, "tag": tag, "crawl_date": crawl_date_str,
            "start_time": crawl_time_str, "end_time": crawl_time_str,
            "status": "failed", "total_funds": 0, "ocr_success": 0,
            "error_message": e.message,
        })

    except Exception as e:
        logger.error(f"[爬虫任务 {record_id}] 未知错误: {e}")
        logger.debug(f"错误详情: {type(e).__name__}: {e}")
        set_crawl_status(last_error=f"未知错误: {str(e)}")
        save_crawl_record({
            "id": record_id, "tag": tag, "crawl_date": crawl_date_str,
            "start_time": crawl_time_str, "end_time": crawl_time_str,
            "status": "failed", "total_funds": 0, "ocr_success": 0,
            "error_message": "未知错误，请查看服务器日志",
        })

    finally:
        set_crawl_status(is_running=False)


def run_cumulative_task(
    app=None,
    tag: str = "private",
    batch_size: int = 5,
    skip_if_exists: bool = False,
    wait_between: int = BATCH_WAIT_BETWEEN,
):
    """
    在后台线程中执行单标签累计净值爬取任务（由调度器调用）。
    app 参数必须由调用方传入，不依赖 current_app LocalProxy。

    Args:
        app: Flask 应用实例
        tag: 基金标签，默认 "private"
        batch_size: 每批处理的基金数量，默认 5
        skip_if_exists: 是否跳过已有 CSV 文件的基金
        wait_between: 批次间等待秒数（默认从配置读取）
    """
    if tag not in ALL_TAG_KEYS:
        raise ValueError(f"不支持的标签 '{tag}'，可选: {ALL_TAG_KEYS}")
    if app is None:
        raise RuntimeError("app instance must be passed to run_cumulative_task")
    with app.app_context():
        _run_cumulative_task_inner(
            tag=tag,
            batch_size=batch_size,
            skip_if_exists=skip_if_exists,
            wait_between=wait_between,
        )


def _run_cumulative_task_inner(
    tag: str = "private",
    batch_size: int = 5,
    skip_if_exists: bool = False,
    wait_between: int = BATCH_WAIT_BETWEEN,
):
    """
    累计净值爬取任务内部实现。自动遍历所有批次，批次间等待。

    Args:
        tag: 基金标签，对应 config.FUND_TYPES 中的 key
        batch_size: 每批处理的基金数量
        skip_if_exists: 是否跳过已有 CSV 的基金
        wait_between: 批次间等待秒数
    """
    global crawl_status
    import time

    set_crawl_status(is_running=True, last_error=None)

    now = datetime.now()
    crawl_date_str = now.strftime("%Y-%m-%d")

    total_success = 0
    total_failed = 0
    total_skipped = 0

    batch_index = 0
    while True:
        crawl_time_str = now.strftime("%Y-%m-%d %H:%M:%S") if batch_index == 0 else datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        batch_info = f" [批次 {batch_index}，每批 {batch_size}]"
        if skip_if_exists:
            batch_info += " [跳过已有]"

        record_id = save_crawl_record({
            "id": None,
            "tag": tag,
            "crawl_date": crawl_date_str,
            "start_time": crawl_time_str,
            "end_time": "",
            "status": "running",
            "total_funds": 0,
            "ocr_success": 0,
            "error_message": f"[累计净值]{batch_info} {tag}",
        })

        try:
            logger.info(f"[累计净值任务 {record_id}] 开始执行，标签={tag}{batch_info}...")

            result = crawl_cumulative_nav(
                tag=tag,
                batch_index=batch_index,
                batch_size=batch_size,
                skip_if_exists=skip_if_exists,
            )
            success_count = result.get("success", 0)
            failed_count = result.get("failed", 0)
            skipped_count = result.get("skipped", 0)
            total_success += success_count
            total_failed += failed_count
            total_skipped += skipped_count

            logger.info(f"[累计净值任务 {record_id}] 批次 {batch_index} 完成，"
                        f"成功 {success_count}，失败 {failed_count}，跳过 {skipped_count}")

            if success_count == 0 and failed_count == 0 and skipped_count == 0:
                logger.info(f"[累计净值任务] 标签={tag} 已无可处理基金，退出")
                break

            save_crawl_record({
                "id": record_id,
                "tag": tag,
                "crawl_date": crawl_date_str,
                "start_time": crawl_time_str,
                "end_time": crawl_time_str,
                "status": "success",
                "total_funds": success_count,
                "ocr_success": success_count,
                "error_message": f"成功 {success_count} / 失败 {failed_count} / 跳过 {skipped_count}",
            })

            batch_index += 1
            if wait_between > 0:
                logger.info(f"[累计净值任务] 等待 {wait_between}s 后继续下一批...")
                time.sleep(wait_between)

        except Exception as e:
            logger.error(f"[累计净值任务 {record_id}] 批次 {batch_index} 失败: {e}")
            save_crawl_record({
                "id": record_id,
                "tag": tag,
                "crawl_date": crawl_date_str,
                "start_time": crawl_time_str,
                "end_time": crawl_time_str,
                "status": "failed",
                "total_funds": 0,
                "ocr_success": 0,
                "error_message": f"[累计净值] {tag}: {str(e)}",
            })
            break

    set_crawl_status(is_running=False)
    set_crawl_status(last_crawl=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    logger.info(f"[累计净值任务] 标签={tag} 全部完成，累计成功 {total_success}，失败 {total_failed}，跳过 {total_skipped}")


def _run_scheduled_crawl(app):
    """定时任务入口：遍历所有配置的标签执行爬取"""
    for tag in config.SCHEDULED_TAGS:
        try:
            from app_state import get_crawl_status as _get
            if _get()["is_running"]:
                logger.warning(f"[定时任务] 爬虫正在运行中，跳过标签={tag}")
                continue
            run_crawl_task(use_ocr=True, app=app, tag=tag)
        except Exception as e:
            logger.error(f"[定时任务] 标签 '{tag}' 爬取失败: {e}")


def _run_scheduled_cumulative(app):
    """定时任务入口：遍历所有配置的标签执行累计净值爬取"""
    for tag in SCHEDULED_CUMULATIVE_TAGS:
        try:
            from app_state import get_crawl_status as _get
            if _get()["is_running"]:
                logger.warning(f"[累计净值定时任务] 爬虫正在运行中，跳过标签={tag}")
                continue
            run_cumulative_task(app=app, tag=tag, batch_size=5, skip_if_exists=False)
        except Exception as e:
            logger.error(f"[累计净值定时任务] 标签 '{tag}' 爬取失败: {e}")


def init_scheduler(app=None):
    """
    初始化统一的定时任务调度器。
    """
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    if app is None:
        from flask import current_app
        app = current_app._get_current_object()

    _scheduler = BackgroundScheduler()

    _scheduler.add_job(
        func=lambda: _run_scheduled_crawl(app),
        trigger=CronTrigger(hour=9, minute=0),
        id="daily_crawl",
        name="每日基金数据爬取",
        replace_existing=True,
    )

    _scheduler.add_job(
        func=lambda: _run_scheduled_crawl(app),
        trigger=CronTrigger(day_of_week="mon", hour=9, minute=30),
        id="weekly_crawl",
        name="每周基金数据爬取",
        replace_existing=True,
    )

    _scheduler.add_job(
        func=lambda: _run_scheduled_cumulative(app),
        trigger=CronTrigger(hour=10, minute=0),
        id="daily_cumulative_crawl",
        name="每日累计净值爬取",
        replace_existing=True,
    )

    _scheduler.start()
    logger.info("定时任务调度器已启动")
    return _scheduler
