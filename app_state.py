# -*- coding: utf-8 -*-
"""app_state.py - 全局应用状态（避免循环导入）"""

import threading

_crawl_lock = threading.Lock()

crawl_status = {
    "is_running": False,
    "last_crawl": None,
    "last_error": None,
}


def get_crawl_status() -> dict:
    """线程安全地读取爬虫状态"""
    with _crawl_lock:
        return dict(crawl_status)


def set_crawl_status(**kwargs) -> None:
    """线程安全地更新爬虫状态"""
    with _crawl_lock:
        crawl_status.update(kwargs)
