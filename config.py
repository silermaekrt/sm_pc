# -*- coding: utf-8 -*-
"""
config.py - 私募排排网抓取工具配置

配置优先级：环境变量 > .env文件 > 代码默认值
"""

import os
import re
import sys
import shutil
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


# ===================== 路径配置 =====================
BASE_DIR = Path(__file__).parent.absolute()
DATA_DIR = os.getenv("SIMU_SAVE_DIR", "data")
SCREENSHOT_DIR = os.getenv("SIMU_SCREENSHOT_DIR", "screenshots")


# ===================== Tesseract OCR 路径自动检测 =====================
def _detect_tesseract_path() -> str:
    """
    自动检测 Tesseract 可执行文件路径。

    检测顺序：
      1. TESSERACT_PATH 环境变量
      2. Windows 默认安装路径
      3. Linux/macOS PATH 中的 tesseract
      4. 返回空字符串（找不到时由调用方处理）
    """
    env_path = os.getenv("TESSERACT_PATH", "").strip()
    if env_path:
        return env_path

    if sys.platform == "win32":
        for base in [r"C:\Program Files", r"C:\Program Files (x86)", r"D:\tools"]:
            for ver in ["", "_ocr", r"Tesseract-OCR", r"Tesseract"]:
                candidate = os.path.join(base, ver, "tesseract.exe")
                if os.path.isfile(candidate):
                    return os.path.dirname(candidate)
        return r"D:\tools\tesseract_ocr"
    else:
        found = shutil.which("tesseract")
        if found:
            return os.path.dirname(found)
        return "/usr/bin"


TESSERACT_PATH = _detect_tesseract_path()


# ===================== 网站配置 =====================
SIMU_URL = os.getenv("SIMU_URL", "https://www.simuwang.com/user/option")
RAW_COOKIE = os.getenv("SIMU_COOKIES", "")


def get_raw_cookie() -> str:
    """动态获取 Cookie（支持运行时刷新后自动更新）"""
    return os.getenv("SIMU_COOKIES", "")

# ===================== 浏览器配置 =====================
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
VIEWPORT_WIDTH = 2200
VIEWPORT_HEIGHT = 4000

# ===================== 超时配置（毫秒）=====================
GOTO_TIMEOUT = 60000       # 页面跳转超时
SELECTOR_TIMEOUT = 30000  # 选择器等待超时
PAGE_WAIT_TIME = 2000      # 页面稳定等待时间
VIEWPORT_WAIT_TIME = 1000  # 视口调整后等待时间

# ===================== 数据验证配置 =====================
MIN_COLUMNS = 18           # 表格最小列数
CODE_PATTERN = re.compile(r"^[A-Z]{2,}\d+$")  # 基金代码正则

# ===================== 截图裁剪配置 =====================
CROP_MARGIN = 10           # 表格截图边距
CROP_X_OFFSET = 2          # 净值裁剪X方向边距
CROP_Y_OFFSET = 5          # 净值裁剪Y方向上偏移（避开日期）
CROP_HEIGHT_RATIO = 0.6    # 只截取单元格高度的60%（上半部分是净值数字）

# ===================== OCR 配置 =====================
OCR_PSM_MODES = [6, 7]     # 尝试的PSM模式（6和7识别数字效果最好）
NET_VALUE_DECIMAL = 4      # 净值小数位数

# ===================== 日志配置 =====================
LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s - %(message)s"

# ===================== 重试配置 =====================
MAX_RETRIES = 3                    # 最大重试次数
RETRY_DELAY = 2.0                  # 初始重试延迟（秒）
RETRY_BACKOFF = 2.0                # 重试延迟倍数
OCR_MAX_RETRIES = 2                # OCR 最大重试次数


# ===================== 确保目录存在 =====================
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(SCREENSHOT_DIR, exist_ok=True)
