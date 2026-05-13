# -*- coding: utf-8 -*-
"""
config/site.py - 目标网站配置
"""

import os

# ===================== 网站 =====================
SIMU_URL = os.getenv("SIMU_URL", "https://www.simuwang.com/user/option")
RAW_COOKIE = os.getenv("SIMU_COOKIES", "")


def get_raw_cookie() -> str:
    return os.getenv("SIMU_COOKIES", "")


# ===================== 安全 =====================
ENCRYPTION_SECRET = os.getenv("SIMU_ENCRYPTION_SECRET", "simu_monitor_key")
