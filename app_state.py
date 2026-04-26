# -*- coding: utf-8 -*-
"""app_state.py - 全局应用状态（避免循环导入）"""

crawl_status = {
    "is_running": False,
    "last_crawl": None,
    "last_error": None,
}
