# -*- coding: utf-8 -*-
"""
tasks/crawl_task.py - 爬虫任务函数

职责：
- 执行爬虫并导入结果到数据库
- 定时爬取调度
"""

import os
import logging
from datetime import datetime
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

import config
from models import db, Fund, CrawlRecord
from app_state import crawl_status
from exceptions import (
    CookieError,
    PageLoadError,
    ElementNotFoundError,
    format_error_detail,
)

logger = logging.getLogger(__name__)

_scheduler: Optional[BackgroundScheduler] = None


def run_crawl_task(use_ocr: bool = True, app=None):
    """
    在后台线程中执行爬虫任务（由调度器调用）。
    app 参数必须由调用方传入，不依赖 current_app LocalProxy。
    """
    if app is None:
        raise RuntimeError("app instance must be passed to run_crawl_task")
    with app.app_context():
        _run_crawl_task_inner(use_ocr)


def _run_crawl_task_inner(use_ocr: bool = True):
    """
    爬虫任务内部实现（在应用上下文中运行）
    """
    global crawl_status

    crawl_status["is_running"] = True
    crawl_status["last_error"] = None

    date_str = datetime.now().strftime("%Y%m%d")
    crawl_date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    record = CrawlRecord(
        crawl_date=date_str,
        start_time=datetime.now(),
        status="running"
    )
    db.session.add(record)
    db.session.commit()
    record_id = record.id

    try:
        logger.info(f"[爬虫任务 {record_id}] 开始执行...")

        from run_ocr import crawl as run_crawl_func, CrawlFailedError
        crawl_result = run_crawl_func(use_ocr=use_ocr)

        imported = _import_csv_to_db(date_str)

        record.status = "success"
        record.end_time = datetime.now()
        record.total_funds = imported
        record.ocr_success = crawl_result.get("ocr_success", 0)
        db.session.commit()

        crawl_status["last_crawl"] = crawl_date_str
        logger.info(
            f"[爬虫任务 {record_id}] 完成，导入 {imported} 条数据 "
            f"(OCR 成功 {crawl_result.get('ocr_success', 0)} 条)"
        )

    except CookieError as e:
        logger.error(f"[爬虫任务 {record_id}] Cookie 错误: {e.message}")
        crawl_status["last_error"] = f"Cookie 错误: {e.message}，请更新 SIMU_COOKIES"
        record.status = "failed"
        record.end_time = datetime.now()
        record.error_message = f"Cookie 错误: {e.message}，请更新 Cookie"
        db.session.commit()

    except PageLoadError as e:
        logger.error(f"[爬虫任务 {record_id}] 页面加载失败: {e.message}")
        crawl_status["last_error"] = f"页面加载失败: {e.message}"
        record.status = "failed"
        record.end_time = datetime.now()
        record.error_message = "页面加载失败，请检查网络连接"
        db.session.commit()

    except ElementNotFoundError as e:
        logger.error(f"[爬虫任务 {record_id}] 页面元素未找到: {e.message}")
        crawl_status["last_error"] = f"页面结构变化: {e.message}"
        record.status = "failed"
        record.end_time = datetime.now()
        record.error_message = "页面结构可能已变化，请更新爬虫代码"
        db.session.commit()

    except CrawlFailedError as e:
        logger.error(f"[爬虫任务 {record_id}] 爬取失败: {e.message}")
        crawl_status["last_error"] = e.message
        record.status = "failed"
        record.end_time = datetime.now()
        record.error_message = e.message
        db.session.commit()

    except Exception as e:
        error_info = format_error_detail(e)
        logger.error(f"[爬虫任务 {record_id}] 未知错误: {e}")
        logger.debug(f"错误详情: {error_info}")
        crawl_status["last_error"] = f"未知错误: {str(e)}"
        record.status = "failed"
        record.end_time = datetime.now()
        record.error_message = "未知错误，请查看服务器日志"
        db.session.commit()

    finally:
        crawl_status["is_running"] = False


def _import_csv_to_db(date_str: str) -> int:
    """
    将爬虫生成的 CSV 文件导入数据库。
    返回导入的记录数。
    """
    csv_path = os.path.join(config.DATA_DIR, f"simu_option_{date_str}.csv")

    if not os.path.exists(csv_path):
        logger.warning(f"CSV 文件不存在: {csv_path}")
        return 0

    import pandas as pd

    try:
        df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
        logger.info(f"读取 CSV: {csv_path}, 共 {len(df)} 条记录")

        Fund.query.filter(Fund.crawl_date == date_str).delete()

        funds = []
        for _, row in df.iterrows():
            def _v(val):
                """安全转字符串，NaN 等空值返回空字符串"""
                if val is None or (isinstance(val, float) and val != val):
                    return ""
                return str(val)

            fund = Fund(
                fund_name=_v(row.get("基金名称", "")),
                fund_code=_v(row.get("基金代码", "")),
                strategy=_v(row.get("策略", "")),
                net_value_date=_v(row.get("净值日期", "")),
                net_value=_v(row.get("最新净值", "")),
                net_change=_v(row.get("净值变动", "")),
                net_change_cmp=_v(row.get("净值对比日期", "")),
                annual_return=_v(row.get("成立来年化", "")),
                this_year=_v(row.get("今年来", "")),
                last_week=_v(row.get("上周", "")),
                last_week_range=_v(row.get("上周区间", "")),
                one_month=_v(row.get("近一月", "")),
                three_month=_v(row.get("近三月", "")),
                six_month=_v(row.get("近半年", "")),
                one_year=_v(row.get("近一年", "")),
                two_year=_v(row.get("近两年", "")),
                three_year=_v(row.get("近三年", "")),
                five_year=_v(row.get("近五年", "")),
                since_inception=_v(row.get("成立来", "")),
                this_week=_v(row.get("本周", "")),
                this_week_range=_v(row.get("本周区间", "")),
                drawdown=_v(row.get("回撤", "")),
                crawl_date=date_str,
            )
            funds.append(fund)

        db.session.bulk_save_objects(funds)
        db.session.commit()

        logger.info(f"成功导入 {len(funds)} 条基金数据")
        return len(funds)

    except Exception as e:
        logger.error(f"导入 CSV 失败: {e}")
        db.session.rollback()
        return 0


def _cookie_refresh_wrapper(app=None):
    """APScheduler 调用的 Cookie 刷新包装函数"""
    if app is None:
        from flask import current_app
        app = current_app._get_current_object()
    with app.app_context():
        from auth.cookie import check_and_refresh_cookies
        check_and_refresh_cookies()


def init_scheduler(app=None):
    """
    初始化统一的定时任务调度器。
    合并了每日爬取任务、每周爬取任务和 Cookie 刷新任务。
    """
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    if app is None:
        from flask import current_app
        app = current_app._get_current_object()

    _scheduler = BackgroundScheduler()

    _scheduler.add_job(
        func=lambda app=app: run_crawl_task(use_ocr=True, app=app),
        trigger=CronTrigger(hour=9, minute=0),
        id="daily_crawl",
        name="每日基金数据爬取",
        replace_existing=True,
    )

    _scheduler.add_job(
        func=lambda app=app: run_crawl_task(use_ocr=True, app=app),
        trigger=CronTrigger(day_of_week="mon", hour=9, minute=30),
        id="weekly_crawl",
        name="每周基金数据爬取",
        replace_existing=True,
    )

    from apscheduler.triggers.interval import IntervalTrigger
    _scheduler.add_job(
        func=lambda app=app: _cookie_refresh_wrapper(app=app),
        trigger=IntervalTrigger(minutes=1),
        id="cookie_refresh",
        name="Cookie 自动刷新",
        replace_existing=True,
    )

    _scheduler.start()
    logger.info("定时任务调度器已启动（包含爬取任务和 Cookie 刷新）")
    return _scheduler
