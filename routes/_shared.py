# -*- coding: utf-8 -*-
"""
routes/_shared.py - 跨蓝图共享的工具函数

改用纯 CSV 存储。
"""

from config import FUND_TYPES
from services.csv_store import get_latest_success_crawl, get_tag_summary


def get_latest_crawl_date(tag: str) -> str | None:
    """返回指定标签最近一次成功爬取的日期字符串，失败返回 None"""
    record = get_latest_success_crawl(tag)
    if record:
        return str(record.get("crawl_date", "") or "")
    return None


def tag_summary(tag: str) -> dict:
    """构建单个标签的统计摘要"""
    return get_tag_summary(tag)
