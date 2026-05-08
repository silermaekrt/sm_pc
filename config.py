# -*- coding: utf-8 -*-
"""
config.py - 配置
"""

import os
import re
import sys
import shutil
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ===================== 路径 =====================
BASE_DIR = Path(__file__).parent.absolute()
DATA_DIR = os.getenv("SIMU_SAVE_DIR", "data")
SCREENSHOT_DIR = os.getenv("SIMU_SCREENSHOT_DIR", "screenshots")


# ===================== 基金标签 =====================
FUND_TYPES = [
    {"key": "private", "name": "私募"},
    {"key": "public",  "name": "公募"},
    {"key": "money",   "name": "货币"},
    {"key": "exp",     "name": "指数"},
]
ALL_TAG_KEYS = [t["key"] for t in FUND_TYPES]


def get_fund_type_map():
    """key → name 映射字典"""
    return {t["key"]: t["name"] for t in FUND_TYPES}


def get_fund_type_lists():
    """(keys_list, names_list)"""
    keys = [t["key"] for t in FUND_TYPES]
    names = [t["name"] for t in FUND_TYPES]
    return keys, names


def get_tag_model_map():
    """标签 → Fund 模型映射"""
    from models import Fund
    return {tag: Fund for tag in ALL_TAG_KEYS}


def init_tag_model_map():
    """Flask 启动时调用（本版本已简化为单模型，无需初始化）"""
    pass


# ===================== 表格列索引（与 DOM 绑定，勿随意修改顺序）=====================
class COL:
    FUND_NAME = 1; NET_VALUE_DATE = 2; NET_CHANGE = 3; ANNUAL_RETURN = 4
    THIS_YEAR = 5; LAST_WEEK = 6; ONE_MONTH = 7; THREE_MONTH = 8
    SIX_MONTH = 9; ONE_YEAR = 10; TWO_YEAR = 11; THREE_YEAR = 12
    FIVE_YEAR = 13; SINCE_INCEPTION = 14; THIS_WEEK = 15; DRAWDOWN = 17
    MIN = 18


# ===================== 爬虫常量 =====================
class CRAWL:
    HEADLESS = False
    COOKIE_DOMAIN = ".simuwang.com"
    PAGE_LOAD_WAIT = "load"
    TABLE_ROW_SELECTOR = "tr.el-table__row"
    NET_VALUE_HEADER = "最新净值"
    NET_VALUE_IMG_MIN_W = 30; NET_VALUE_IMG_MAX_W = 150
    NET_VALUE_IMG_H = 8; NET_VALUE_IMG_FALLBACK_W = 35; NET_VALUE_IMG_FALLBACK_H = 20


# ===================== 安全 =====================
ENCRYPTION_SECRET = os.getenv("SIMU_ENCRYPTION_SECRET", "simu_monitor_key")


# ===================== Tesseract OCR 路径自动检测 =====================
def _detect_tesseract_path() -> str:
    env_path = os.getenv("TESSERACT_PATH", "").strip()
    if env_path:
        return env_path

    if sys.platform == "win32":
        for base in [r"C:\Program Files", r"C:\Program Files (x86)", r"D:\tools", r"D:\software"]:
            for ver in ["", "_ocr", r"Tesseract-OCR", r"Tesseract", "tesseract"]:
                candidate = os.path.join(base, ver, "tesseract.exe")
                if os.path.isfile(candidate):
                    return os.path.dirname(candidate)
        return r"D:\tools\tesseract_ocr"
    else:
        found = shutil.which("tesseract")
        return os.path.dirname(found) if found else "/usr/bin"


TESSERACT_PATH = _detect_tesseract_path()


# ===================== 网站 =====================
SIMU_URL = os.getenv("SIMU_URL", "https://www.simuwang.com/user/option")
RAW_COOKIE = os.getenv("SIMU_COOKIES", "")


def get_raw_cookie() -> str:
    return os.getenv("SIMU_COOKIES", "")


# ===================== 浏览器 =====================
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
VIEWPORT_WIDTH = 2200; VIEWPORT_HEIGHT = 4000


# ===================== 超时（毫秒）=====================
GOTO_TIMEOUT = 60000; SELECTOR_TIMEOUT = 30000
PAGE_WAIT_TIME = 2000; VIEWPORT_WAIT_TIME = 1000; TAB_SWITCH_WAIT_TIME = 1500


# ===================== 数据验证 =====================
MIN_COLUMNS = 18
CODE_PATTERN = re.compile(r"[A-Z0-9]+")


# ===================== 截图裁剪 =====================
CROP_MARGIN = 10; CROP_X_OFFSET = 2; CROP_Y_OFFSET = 5; CROP_HEIGHT_RATIO = 0.6


# ===================== 功能开关 =====================
SAVE_SCREENSHOT = os.getenv("SAVE_SCREENSHOT", "true").lower() == "true"
SAVE_DB = os.getenv("SAVE_DB", "true").lower() == "true"


# ===================== OCR =====================
OCR_PSM_MODES = [6, 7]
NET_VALUE_DECIMAL = 4



# ===================== 重试 =====================
MAX_RETRIES = 3; RETRY_DELAY = 2.0; RETRY_BACKOFF = 2.0; OCR_MAX_RETRIES = 2


# ===================== 初始化目录 =====================
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(SCREENSHOT_DIR, exist_ok=True)


# ===================== 累计净值 =====================
CUMULATIVE_BASE_DIR = os.getenv("CUMULATIVE_DIR", "cumulative")
