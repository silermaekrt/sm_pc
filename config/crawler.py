# -*- coding: utf-8 -*-
"""
config/crawler.py - 爬虫行为配置
"""

# ===================== 爬虫常量 =====================
class CRAWL:
    HEADLESS = False
    COOKIE_DOMAIN = ".simuwang.com"
    PAGE_LOAD_WAIT = "load"
    TABLE_ROW_SELECTOR = "tr.el-table__row"
    NET_VALUE_HEADER = "最新净值"
    NET_VALUE_IMG_MIN_W = 30
    NET_VALUE_IMG_MAX_W = 150
    NET_VALUE_IMG_H = 8
    NET_VALUE_IMG_FALLBACK_W = 35
    NET_VALUE_IMG_FALLBACK_H = 20


# ===================== 浏览器 =====================
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
VIEWPORT_WIDTH = 2200
VIEWPORT_HEIGHT = 4000


# ===================== 超时（毫秒）=====================
GOTO_TIMEOUT = 60000
SELECTOR_TIMEOUT = 30000
PAGE_WAIT_TIME = 2000
VIEWPORT_WAIT_TIME = 1000
TAB_SWITCH_WAIT_TIME = 1500
# 累计净值爬取时，每个基金详情页之间的间隔（毫秒）
# 设置较大值以避免平台风控（验证码），建议 3000~15000
CUMULATIVE_CRAWL_INTERVAL = 15000
# 批次之间间隔（秒），每批跑完后等待这段时间再继续下一批
BATCH_WAIT_BETWEEN = 300  # 5分钟


# ===================== 截图裁剪 =====================
CROP_MARGIN = 10
CROP_X_OFFSET = 2
CROP_Y_OFFSET = 5
CROP_HEIGHT_RATIO = 0.6


# ===================== 功能开关 =====================
SAVE_SCREENSHOT = __import__("os").getenv("SAVE_SCREENSHOT", "true").lower() == "true"


# ===================== 重试 =====================
MAX_RETRIES = 3
RETRY_DELAY = 2.0
RETRY_BACKOFF = 2.0
OCR_MAX_RETRIES = 2


# ===================== 累计净值表格 =====================
# 精确指向历史净值模块：<section class="mt-16"> → div[data-v-dd0a6ac4]
CUMULATIVE_SECTION_SELECTOR = "section.mt-16"
CUMULATIVE_TABLE_SELECTOR = "section.mt-16 .el-table--scrollable-y"
CUMULATIVE_BODY_SELECTOR = "section.mt-16 .el-table__body-wrapper"
# Element UI 表格行、单元格
CUMULATIVE_ROW_SELECTOR = "section.mt-16 tbody tr.el-table__row"
# 列索引（0-based）：0=日期 1=单位净值 2=分红不投资 3=空白占位 4=分红再投资 5=净值变动
COL_IDX_DATE = 0
COL_IDX_UNIT_NAV = 1      # 单位净值
COL_IDX_DIV_REINVEST_NO = 2   # 分红不投资
COL_IDX_SPACER = 3
COL_IDX_DIV_REINVEST_YES = 4  # 分红再投资（累计净值）
COL_IDX_CHANGE = 5       # 净值变动


# ===================== 基准指数 =====================
BENCHMARK_SELECTOR = ".dropdown-modify .el-tooltip__trigger"
BENCHMARK_TEXT_PATTERN = r"[\u4e00-\u9fff·\w]+"  # 匹配中文、英文、数字组成的指数名
