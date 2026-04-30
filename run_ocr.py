# -*- coding: utf-8 -*-
"""
run_ocr.py - 带 OCR 净值识别的私募排排网抓取工具

使用方法：
    python run_ocr.py           # 抓取 + OCR 识别
"""

import os
import re
import time
import logging
import argparse
import pandas as pd
from datetime import datetime

from playwright.sync_api import sync_playwright, Error as PlaywrightError
import config
from exceptions import (
    BrowserError,
    PageLoadError,
    ElementNotFoundError,
    CookieError,
    DataParseError,
    ScreenshotError,
    CSVError,
    TagNotFoundError,
    format_error_detail,
)
from retry_utils import retry_on_exception

# ===================== 日志配置 =====================
logging.basicConfig(level=config.LOG_LEVEL, format=config.LOG_FORMAT)
logger = logging.getLogger(__name__)

if not config.get_raw_cookie():
    logger.warning("SIMU_COOKIES 环境变量未设置，Cookie 将为空，可能导致抓取失败")


# ===================== 模块级常量 =====================
_TAG_KEYWORD_MAP = config.get_fund_type_map()
_TAG_KEY_LIST=config.get_fund_type_lists()[0]
_TAG_VALUE_LIST=config.get_fund_type_lists()[1]

# ===================== 异常类型 =====================
PLAYWRIGHT_RETRY_EXCEPTIONS = (
    PlaywrightError,
    TimeoutError,
    OSError,
)


def retryable(func):
    """重试装饰器"""
    return retry_on_exception(
        max_attempts=config.MAX_RETRIES,
        delay=config.RETRY_DELAY,
        backoff=config.RETRY_BACKOFF,
        exceptions=PLAYWRIGHT_RETRY_EXCEPTIONS,
        on_retry=lambda e, n: logger.warning(f"重试 {n}/{config.MAX_RETRIES}: {e}"),
    )


def _log_and_sleep(attempt: int, e: Exception):
    """记录重试日志并等待退避时间"""
    logger.warning(f"第 {attempt}/{config.MAX_RETRIES} 次尝试失败: {e}")
    sleep_time = config.RETRY_DELAY * (config.RETRY_BACKOFF ** (attempt - 1))
    logger.info(f"{sleep_time:.1f} 秒后进行第 {attempt + 1} 次尝试...")
    time.sleep(sleep_time)


# ===================== OCR 识别 =====================
def ocr_recognize_net_value(pytesseract, img, fund_name_for_debug="", retry_count=0):
    """
    用 Tesseract OCR 识别净值数字。
    返回识别的净值字符串（如 "1.2345"），失败返回 ""
    """
    if pytesseract is None:
        return ""

    try:
        candidates = []
        for psm in [6, 7]:
            raw = pytesseract.image_to_string(img, lang="eng", config=f"--psm {psm}")
            net_value = extract_net_value(raw)
            if net_value:
                candidates.append(net_value)

        decimal_candidates = [c for c in candidates if "." in c]
        if decimal_candidates:
            return decimal_candidates[0]
        return candidates[0] if candidates else ""

    except Exception as e:
        logger.debug(f"OCR 失败 [{fund_name_for_debug}]: {e}")
        if retry_count < config.OCR_MAX_RETRIES:
            logger.warning(
                f"OCR 识别失败 [{fund_name_for_debug}]，重试 {retry_count + 1}/{config.OCR_MAX_RETRIES}"
            )
            time.sleep(0.5)
            return ocr_recognize_net_value(
                pytesseract, img, fund_name_for_debug, retry_count + 1
            )
        return ""


def extract_net_value(text: str) -> str:
    """从 OCR 文本中提取净值数值，强制保留小数点后4位"""
    if not text:
        return ""
    text = text.strip().replace("\n", " ").replace("\r", " ")
    text = re.sub(r"[^\d.\-]", "", text)
    text = text.lstrip(".")
    if not text:
        return ""
    match = re.search(r"\d+\.\d+|\d+", text)
    if match:
        val = match.group()
        if "." in val:
            integer, decimal = val.split(".")
            decimal = (decimal + "0000")[:4]
            return f"{integer}.{decimal}"
        return f"{val}.0000"
    return ""


# ===================== 辅助函数 =====================
def _parse_name_cell(text: str) -> tuple:
    """解析基金名称单元格，返回 (基金名称, 基金代码, 策略)"""
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    fund_name = lines[0] if lines else ""
    fund_code = ""
    strategy = ""
    print( lines)
    for line in lines[1:]:
        if config.CODE_PATTERN.match(line):
            fund_code = line
        elif line and len(line) < 20:
            strategy = line
    return fund_name, fund_code, strategy


def _parse_change_cell(text: str) -> tuple:
    """解析净值变动单元格，返回 (变动值, 对比日期)"""
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    return (lines[0] if lines else "", lines[1] if len(lines) > 1 else "")


def _parse_week_cell(text: str) -> tuple:
    """解析本周/上周单元格，返回 (值, 日期区间)"""
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    return (lines[0] if lines else "", lines[1] if len(lines) > 1 else "")


def _safe_filename(name: str) -> str:
    """将基金名称转为安全的文件名"""
    name = re.sub(r"[\\/:*?\"<>|]", "_", name)
    return name[:40]


def _switch_to_tag(page, tag: str) -> bool:
    """
    切换到指定标签页。
    tag
    返回 True 表示成功，False 表示标签不存在或切换失败。
    """
    tab_keyword = _TAG_KEYWORD_MAP.get(tag, tag)
    try:
        page.evaluate('''(kw) => {
                   const tabs = document.querySelectorAll('.xs-nav-item');
                   tabs.forEach(t => {
                       if(t.innerText.includes(kw)) t.click();
                   });
               }''', tab_keyword)

        # 2. 【关键】等待标签变成【选中状态】，确保页面真切换了
        page.wait_for_selector(
            f'.xs-nav-item.is-active:text("({tab_keyword})"), .xs-nav-item.active:text("{tab_keyword}")',
            timeout=3000
        )

        logger.info(f"已点击标签: {tab_keyword!r}")

        page.wait_for_timeout(config.TAB_SWITCH_WAIT_TIME)
        return True

    except Exception as e:
        logger.warning(f"切换标签 '{tab_keyword}' 失败: {e}")
        return False


def _ensure_tag_exists(page, tag: str) -> bool:
    """验证指定标签页是否存在"""
    tab_keyword = _TAG_KEYWORD_MAP.get(tag, tag)
    try:
        exists = page.evaluate(
            f'''() => {{
                return Array.from(document.querySelectorAll(".xs-nav-item"))
                    .some(el => el.innerText.includes("{tab_keyword}"));
            }}'''
        )
        if not exists:
            logger.warning(f"标签 '{tab_keyword}' 不存在")
        return exists
    except Exception as e:
        logger.warning(f"检查标签 '{tab_keyword}' 时出错: {e}")
        return False

def _setup_cookies(context):
    """设置 Cookie，统一处理异常"""
    raw_cookie = config.get_raw_cookie()
    if not raw_cookie:
        raise CookieError("SIMU_COOKIES 环境变量未设置", expired=True)

    success_count = 0
    failed_cookies = []

    for item in raw_cookie.split(";"):
        item = item.strip()
        if not item or "=" not in item:
            continue
        k, v = item.split("=", 1)
        k, v = k.strip(), v.strip()
        if not k:
            continue
        try:
            context.add_cookies(
                [{"name": k, "value": v, "domain": config.CRAWL.COOKIE_DOMAIN, "path": "/"}]
            )
            success_count += 1
        except Exception as e:
            failed_cookies.append(k)
            logger.debug(f"Cookie 设置失败 [{k}]: {e}")

    if success_count == 0:
        raise CookieError(
            "所有 Cookie 设置均失败，请检查 Cookie 格式", expired=True
        )

    if failed_cookies:
        logger.warning(f"部分 Cookie 设置失败: {failed_cookies}")

    logger.info(f"Cookie 设置完成，成功 {success_count} 个")


# ===================== 浏览器交互阶段 =====================
def _init_tesseract():
    """初始化 Tesseract OCR，返回 pytesseract 模块或 None"""
    try:
        import pytesseract

        import sys
        if sys.platform == "win32":
            tesseract_exe = os.path.join(config.TESSERACT_PATH, "tesseract.exe")
        else:
            tesseract_exe = os.path.join(config.TESSERACT_PATH, "tesseract")
        if os.path.exists(tesseract_exe):
            pytesseract.pytesseract.tesseract_cmd = tesseract_exe
            logger.info(f"Tesseract 初始化完成: {tesseract_exe}")
        else:
            logger.warning(f"Tesseract 未找到: {tesseract_exe}，OCR 功能将被禁用")
            pytesseract = None
    except ImportError:
        logger.warning("pytesseract 未安装，OCR 功能将被禁用")
        pytesseract = None
    except Exception as e:
        logger.warning(f"Tesseract 初始化失败: {e}，OCR 功能将被禁用")
        pytesseract = None

    return pytesseract


def _navigate_and_wait(page, tag: str = "private") -> dict:
    """
    跳转到目标页面，切换标签，等待表格加载，提取位置/表格信息/文本数据。

    标签切换完成并稳定后，才执行数据提取，确保用的是切换后页面的坐标和文本。

    返回 dict:
      - has_data: bool
      - tag: str
      - fund_positions: list
      - table_info: dict | None
      - rows_data: list
    """
    try:
        page.goto(config.SIMU_URL, wait_until=config.CRAWL.PAGE_LOAD_WAIT, timeout=config.GOTO_TIMEOUT)
        logger.info(f"页面加载完成: {page.title()}")
    except PlaywrightError as e:
        raise PageLoadError(f"页面加载失败: {e}", url=config.SIMU_URL, timeout=config.GOTO_TIMEOUT)

    page.set_viewport_size(
        {"width": config.VIEWPORT_WIDTH, "height": config.VIEWPORT_HEIGHT}
    )

    try:
        page.wait_for_selector(config.CRAWL.TABLE_ROW_SELECTOR, timeout=config.SELECTOR_TIMEOUT)
        logger.info("表格加载完成")
    except PlaywrightError:
        raise ElementNotFoundError(
            "表格行未找到，可能页面结构变化或数据为空",
            selector=config.CRAWL.TABLE_ROW_SELECTOR,
        )

    page.wait_for_timeout(config.VIEWPORT_WAIT_TIME)

    if tag != "private":
        if not _ensure_tag_exists(page, tag):
            raise TagNotFoundError(tag=tag, available_tags=_TAG_KEY_LIST)
        if not _switch_to_tag(page, tag):
            raise TagNotFoundError(tag=tag, available_tags=_TAG_KEY_LIST)
        try:
            page.wait_for_selector(
                f"{config.CRAWL.TABLE_ROW_SELECTOR}:visible",
                timeout=config.SELECTOR_TIMEOUT,
            )
            page.wait_for_timeout(config.PAGE_WAIT_TIME)
        except PlaywrightError:
            logger.warning(f"切换标签 '{tag}' 后表格未出现，该标签无可见数据")


    fund_positions = _extract_positions(page)
    table_info = _get_table_info(page)
    rows_data = _extract_text_data(page)

    logger.info(f"数据提取完成: {len(rows_data)} 行")


    return {
        "has_data": True,
        "tag": tag,
        "fund_positions": fund_positions,
        "table_info": table_info,
        "rows_data": rows_data,
    }


def _extract_positions(page) -> list:
    """从页面中提取所有基金行的位置信息"""
    try:
        positions = page.evaluate(
            """
() => {
    const rows = Array.from(document.querySelectorAll('tbody tr.el-table__row'));
    const visibleRows = rows.filter(row => {
        let el = row;
        for (let i=0; i<7; i++) el = el?.parentElement;
            if (!el) return false;        // 第八个父亲不存在 → 不要
            if (el.offsetParent === null) return false;  // 第八个父亲隐藏 → 不要
            return true;                  // 否则留下
           });
    const positions = [];
    
    const headerCells = document.querySelectorAll('thead th');
    let netValueColIndex = -1;
    for (let i = 0; i < headerCells.length; i++) {
        const text = headerCells[i].innerText.trim();
        if (text === '最新净值') {
            netValueColIndex = i;
            break;
        }
    }

    for (const row of visibleRows) {
        const cells = row.querySelectorAll('td');
        if (cells.length < 2) continue;

        const nameCell = cells[1];
        const fundName = nameCell ? (nameCell.querySelector('a')?.title || nameCell.innerText.split('\\n')[0].trim()) : '';
        if (!fundName) continue;

        const nameRect = nameCell.getBoundingClientRect();
        const rowRect = row.getBoundingClientRect();

        let netValueImg = null;
        if (netValueColIndex >= 0 && cells[netValueColIndex]) {
            const netValueCell = cells[netValueColIndex];

            const imgs = netValueCell.querySelectorAll('img');
            for (const img of imgs) {
                const rect = img.getBoundingClientRect();
                if (rect.width > 30 && rect.width < 150 && rect.height > 8 && rect.height < 35) {
                    netValueImg = { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
                    break;
                }
            }

            if (!netValueImg) {
                const allElements = netValueCell.querySelectorAll('*');
                for (const el of allElements) {
                    if (el.tagName === 'IMG') {
                        const rect = el.getBoundingClientRect();
                        if (rect.width > 30 && rect.width < 150 && rect.height > 8 && rect.height < 35) {
                            netValueImg = { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
                            break;
                        }
                    }
                }
            }

            if (!netValueImg) {
                const rect = netValueCell.getBoundingClientRect();
                if (rect.width > 30 && rect.height > 20) {
                    netValueImg = { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
                }
            }
        }

        positions.push({
            fundName,
            nameX: nameRect.x,
            nameY: nameRect.y,
            nameWidth: nameRect.width,
            nameHeight: nameRect.height,
            rowY: rowRect.y,
            rowHeight: rowRect.height,
            netValueImg,
            netValueColIndex
        });
    }

    return positions;
}
"""
        )
    except PlaywrightError as e:
        raise BrowserError(f"提取位置信息失败: {e}", action="evaluate_js")

    logger.info(f"找到 {len(positions)} 个基金位置信息")
    return positions


def _get_table_info(page) -> dict | None:
    """获取表格区域信息，若表格不可见则返回 None"""
    info = page.evaluate(
        """
() => {
    // 查找 祖先节点没有被隐藏 的那个表格
    const allTables = document.querySelectorAll('.el-table__body-wrapper');
    for (const table of allTables) {
        let parent = table;
        let isHidden = false;
        // 向上查找3层，判断是否被隐藏
        for (let i = 0; i < 5; i++) {
            if (!parent) break;
            const style = parent.style.display || '';
            if (style === 'none') {
                isHidden = true;
                break;
            }
            parent = parent.parentElement;
        }
        if (!isHidden) {
            const rect = table.getBoundingClientRect();
            return { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
        }
    }
    return null;
}
"""
    )

    if info is None or info.get("width", 0) <= 0 or info.get("height", 0) <= 0:
        return None
    return info


def _capture_table_screenshot(page, table_info: dict | None, date_str: str = "", tag: str = "") -> str:
    """截取表格区域并保存，返回截图路径。table_info 为 None 时跳过。"""
    if table_info is None:
        return ""

    clip_x = max(0, table_info["x"] - config.CROP_MARGIN)
    clip_y = max(0, table_info["y"] - config.CROP_MARGIN)
    clip_w = table_info["width"] + config.CROP_MARGIN * 2
    clip_h = table_info["height"] + config.CROP_MARGIN * 2

    logger.info(f"截图区域: x={clip_x}, y={clip_y}, w={clip_w}, h={clip_h}")

    if date_str:
        tag_dir = os.path.join(config.SCREENSHOT_DIR, date_str, tag)
    else:
        tag_dir = config.SCREENSHOT_DIR
    os.makedirs(tag_dir, exist_ok=True)

    try:
        screenshot_bytes = page.screenshot(
            type="png",
            clip={"x": clip_x, "y": clip_y, "width": clip_w, "height": clip_h},
        )
        screenshot_path = os.path.join(tag_dir, "table_full_screenshot.png")
        with open(screenshot_path, "wb") as f:
            f.write(screenshot_bytes)
        logger.info(f"表格截图已保存: {screenshot_path} ({len(screenshot_bytes)} bytes)")
        return screenshot_path
    except Exception as e:
        raise ScreenshotError(f"截图保存失败: {e}")


def _extract_text_data(page) -> list:
    """从页面提取所有可见行的文本数据"""
    try:
        js_code = (
            """
() => {
    const rows = [];
    const allRows = document.querySelectorAll('tbody """ + config.CRAWL.TABLE_ROW_SELECTOR + """');

    for (const row of allRows) {
        // 只保留：第7层父级 没有 display: none 的行
        let el = row;
        let hidden = false;

        // 向上找 7 层父级
        for (let i = 0; i < 8; i++) {
            if (!el) break;
            el = el.parentElement;
        }

        // 检查第7层父亲是否隐藏
        if (el && el.style.display === 'none') {
            hidden = true;
        }

        if (!hidden && !(row.getAttribute('style') || '').includes('display: none')) {
            rows.push(row);
        }
    }

    return rows.map(row => {
        const cells = Array.from(row.querySelectorAll('td'));
        return cells.map(cell => cell.innerText.trim());
    }).filter(cells => cells.length >= """ + str(config.COL.MIN) + """);
}
"""
        )

        rows_data = page.evaluate(js_code)
    except PlaywrightError as e:
        raise BrowserError(f"提取文本数据失败: {e}", action="evaluate_js")
    return rows_data


def _run_browser_session(use_ocr: bool, tag: str = "private", date_str: str = "") -> tuple:
    """
    执行单次浏览器会话：导航、截图、提取数据。
    返回 (fund_positions, table_info, table_screenshot_path, rows_data)
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=config.CRAWL.HEADLESS,args=["--start-maximized"])
        context = browser.new_context(user_agent=config.USER_AGENT,viewport=None)
        _setup_cookies(context)

        page = context.new_page()
        nav_result = _navigate_and_wait(page, tag)

        if not nav_result["has_data"]:
            logger.warning(f"标签 '{tag}' 表格无可见数据，跳过提取")
            return [], None, "", []

        fund_positions = nav_result["fund_positions"]
        table_info = nav_result["table_info"]
        rows_data = nav_result["rows_data"]

        table_screenshot_path = ""
        if config.SAVE_SCREENSHOT and table_info:
            print("开始截图...")
            table_screenshot_path = _capture_table_screenshot(page, table_info, date_str, tag)

        context.close()
        browser.close()
        logger.info("浏览器会话成功完成")

        return fund_positions, table_info, table_screenshot_path, rows_data


# ===================== OCR 阶段 =====================
def _recognize_net_values(
    pytesseract,
    fund_positions: list,
    table_info: dict,
    table_screenshot_path: str,
    actual_fund_count: int,
    date_str: str = "",
    tag: str = "",
) -> tuple:
    """
    对表格截图进行 OCR 识别净值。
    actual_fund_count: 实际解析出的基金行数（用于统计分母）
    date_str / tag: 用于截图子目录路径
    返回 (ocr_results dict, failed list)
    """
    if pytesseract is None or not table_screenshot_path or not os.path.exists(table_screenshot_path):
        return {}, []

    logger.info("开始 OCR 识别净值...")

    try:
        from PIL import Image
        img = Image.open(table_screenshot_path)
    except ImportError:
        logger.warning("Pillow 未安装，无法进行 OCR 处理")
        return {}, []
    except Exception as e:
        logger.error(f"OCR 图片加载失败: {e}")
        return {}, []

    # 截图子目录
    if date_str and tag:
        crop_dir = os.path.join(config.SCREENSHOT_DIR, date_str, tag)
        os.makedirs(crop_dir, exist_ok=True)
    else:
        crop_dir = config.SCREENSHOT_DIR

    ocr_results = {}
    ocr_failed_list = []

    for i, pos in enumerate(fund_positions):
        fund_name = pos["fundName"]

        if not pos.get("netValueImg"):
            ocr_failed_list.append(fund_name)
            logger.debug(f"[{fund_name}] 未找到净值图片")
            continue

        nv = pos["netValueImg"]
        local_x = nv["x"] - (table_info["x"] - config.CROP_MARGIN)
        local_y = nv["y"] - (table_info["y"] - config.CROP_MARGIN)

        crop_box = (
            max(0, int(local_x - config.CROP_X_OFFSET)),
            max(0, int(local_y - config.CROP_Y_OFFSET)),
            min(img.width, int(local_x + nv["width"] + config.CROP_X_OFFSET)),
            min(img.height, int(local_y + nv["height"] * config.CROP_HEIGHT_RATIO)),
        )

        if crop_box[2] <= crop_box[0] or crop_box[3] <= crop_box[1]:
            ocr_failed_list.append(fund_name)
            continue

        net_value_img = img.crop(crop_box)

        # 保存裁剪图（仅在开启截图功能时保存）
        if config.SAVE_SCREENSHOT:
            debug_crop_path = os.path.join(
                crop_dir,
                f"{_safe_filename(fund_name)}.png",
            )
            net_value_img.save(debug_crop_path)

        net_value = ocr_recognize_net_value(pytesseract, net_value_img, fund_name)

        if net_value:
            ocr_results[fund_name] = net_value
            logger.info(f"[{fund_name}] OCR成功: {net_value}")
        else:
            ocr_failed_list.append(fund_name)
            logger.debug(f"[{fund_name}] OCR失败")
        ocr_failed_list = []

    success_count = len(ocr_results)
    fail_count = len(ocr_failed_list)
    total_count = actual_fund_count

    logger.info(f"OCR 识别完成：{success_count}/{total_count} 成功，{fail_count} 失败")

    if ocr_failed_list:
        logger.warning(f"OCR 失败基金列表: {ocr_failed_list[:5]}...")

    return ocr_results, ocr_failed_list


# ===================== 解析阶段 =====================
def _parse_funds(rows_data: list, ocr_results: dict) -> tuple:
    """
    解析基金行数据，合并 OCR 净值结果。
    返回 (funds list, parse_errors list)
    """
    if not rows_data:
        raise CrawlFailedError("未找到任何基金行数据")

    logger.info(f"找到 {len(rows_data)} 行基金数据")

    funds = []
    parse_errors = []

    for idx, row in enumerate(rows_data):
        try:
            if len(row) < config.COL.MIN:
                raise DataParseError(
                    f"行 {idx + 1} 字段数不足: {len(row)} < {config.COL.MIN}",
                    field="row_length",
                )
            print(row)
            print("00000000000000000000000000000000000000000000000")
            fund_name, fund_code, strategy = _parse_name_cell(row[config.COL.FUND_NAME])
            net_value_date = row[config.COL.NET_VALUE_DATE].strip()
            net_change, net_change_cmp = _parse_change_cell(row[config.COL.NET_CHANGE])
            annual_return = row[config.COL.ANNUAL_RETURN].strip()
            this_year = row[config.COL.THIS_YEAR].strip()
            last_week, last_week_range = _parse_week_cell(row[config.COL.LAST_WEEK])
            one_month = row[config.COL.ONE_MONTH].strip()
            three_month = row[config.COL.THREE_MONTH].strip()
            six_month = row[config.COL.SIX_MONTH].strip()
            one_year = row[config.COL.ONE_YEAR].strip()
            two_year = row[config.COL.TWO_YEAR].strip()
            three_year = row[config.COL.THREE_YEAR].strip()
            five_year = row[config.COL.FIVE_YEAR].strip()
            since_inception = row[config.COL.SINCE_INCEPTION].strip()
            this_week, this_week_range = _parse_week_cell(row[config.COL.THIS_WEEK])
            drawdown = row[config.COL.DRAWDOWN].strip()

            if not fund_name:
                continue
            funds.append({
                "基金名称": fund_name,
                "基金代码": fund_code,
                "策略": strategy,
                "净值日期": net_value_date,
                "最新净值": ocr_results.get(fund_name, ""),
                "净值变动": net_change,
                "净值对比日期": net_change_cmp,
                "成立来年化": annual_return,
                "今年来": this_year,
                "上周": last_week,
                "上周区间": last_week_range,
                "近一月": one_month,
                "近三月": three_month,
                "近半年": six_month,
                "近一年": one_year,
                "近两年": two_year,
                "近三年": three_year,
                "近五年": five_year,
                "成立来": since_inception,
                "本周": this_week,
                "本周区间": this_week_range,
                "回撤": drawdown,
            })
        except DataParseError as e:
            parse_errors.append(f"行 {idx + 1}: {e.message}")
            logger.debug(f"解析行 {idx + 1} 失败: {e.message}")
            continue

    if parse_errors:
        logger.warning(f"共 {len(parse_errors)} 行解析失败")

    return funds, parse_errors


# ===================== 保存阶段 =====================
def _save_funds_csv(funds: list, date_str: str = "", tag: str = "private") -> str:
    """将基金数据保存为 CSV，返回文件路径"""
    if date_str:
        tag_dir = os.path.join(config.DATA_DIR, date_str)
    else:
        date_str = datetime.now().strftime("%Y%m%d")
        tag_dir = os.path.join(config.DATA_DIR, date_str)
    os.makedirs(tag_dir, exist_ok=True)
    path = os.path.join(tag_dir, f"{tag}.csv")

    try:
        df = pd.DataFrame([{k: str(v) if v is not None else "" for k, v in f.items()} for f in funds])
        df.to_csv(path, index=False, encoding="utf-8-sig")
        logger.info(f"抓取成功！共 {len(funds)} 条 -> {path}")
        return path
    except Exception as e:
        raise CSVError(f"CSV 保存失败: {e}", file_path=path)


def _print_preview(df: pd.DataFrame):
    """打印数据预览（前5条）"""
    print("\n=== 数据预览（前5条）===")
    preview_cols = [
        "基金名称", "基金代码", "策略", "净值日期", "最新净值",
        "净值变动", "今年来", "近一年", "近三年", "成立来", "回撤",
    ]
    available = [c for c in preview_cols if c in df.columns]
    preview_df = df[available].head()

    col_widths = {col: len(col) for col in preview_df.columns}
    for col in preview_df.columns:
        for val in preview_df[col].astype(object).fillna("").astype(str).values:
            display_len = sum(2 if ("\u4e00" <= c <= "\u9fff") else 1 for c in val)
            col_widths[col] = max(col_widths[col], display_len)

    header = "  ".join(col.ljust(col_widths[col]) for col in preview_df.columns)
    sep = "  ".join("-" * col_widths[col] for col in preview_df.columns)
    print(header)
    print(sep)

    for _, row in preview_df.iterrows():
        parts = []
        for col in preview_df.columns:
            val = str(row[col])
            display_len = sum(2 if ("\u4e00" <= c <= "\u9fff") else 1 for c in val)
            parts.append(val.ljust(col_widths[col]))
        print("  ".join(parts))


def _print_ocr_stats(df: pd.DataFrame):
    """打印 OCR 成功率统计"""
    nv_col = "最新净值"
    if nv_col not in df.columns:
        return
    total = len(df)
    success = sum(1 for v in df[nv_col] if v)
    fail = total - success
    msg = f"\n[OCR 统计] 总行数={total}，成功={success}，失败={fail}，成功率={success/total*100:.1f}%"
    logger.info(msg.strip())
    print(msg)


# ===================== 核心抓取 =====================
def crawl(use_ocr: bool = True, tag: str = "private"):
    """
    抓取私募排排网数据，支持 OCR 净值识别。

    Args:
        use_ocr: 是否启用 OCR 识别净值（默认 True）
        tag: 爬取哪个标签（默认 "private"）
    """
    logger.info(f"开始抓取私募排排网 - 标签={tag}")

    date_str = datetime.now().strftime("%Y%m%d")

    pytesseract = None
    crawl_error = None

    if use_ocr:
        pytesseract = _init_tesseract()
        if pytesseract is None:
            logger.info("OCR 已禁用，仅抓取文字数据")
    else:
        logger.info("OCR 已禁用，仅抓取文字数据")

    # 浏览器会话（带重试）
    for attempt in range(1, config.MAX_RETRIES + 1):
        try:
            logger.info(f"第 {attempt}/{config.MAX_RETRIES} 次尝试 - 启动浏览器...")
            fund_positions, table_info, table_screenshot_path, rows_data = \
                _run_browser_session(use_ocr, tag, date_str)
            break

        except TagNotFoundError as e:
            logger.warning(f"标签 '{tag}' 不存在: {e.message}，提示用户并跳过")
            raise TagNotFoundError(
                tag=tag,
                available_tags=e.details.get("available_tags", _TAG_KEY_LIST),
            )

        except (PageLoadError, ElementNotFoundError, BrowserError, ScreenshotError) as e:
            crawl_error = e
            if attempt < config.MAX_RETRIES:
                _log_and_sleep(attempt, e)
            else:
                error_detail = format_error_detail(e)
                raise CrawlFailedError(f"抓取失败: {error_detail['message']}", e)

        except CookieError as e:
            raise e  # Cookie 错误不重试

        except Exception as e:
            crawl_error = e
            if attempt < config.MAX_RETRIES:
                _log_and_sleep(attempt, e)
            else:
                raise CrawlFailedError(f"抓取失败: {e}", e)

    # 解析
    funds, parse_errors = _parse_funds(rows_data, {})

    if not funds:
        logger.warning(f"标签 '{tag}' 未提取到任何基金数据（可能该标签为空或页面无数据），已跳过")
        return {
            "total": 0,
            "ocr_success": 0,
            "ocr_failed": 0,
            "parse_errors": len(parse_errors),
        }

    actual_fund_count = len(funds)

    # OCR 识别
    ocr_results = {}
    ocr_failed_list = []
    if use_ocr and pytesseract:
        ocr_results, ocr_failed_list = _recognize_net_values(
            pytesseract, fund_positions, table_info, table_screenshot_path,
            actual_fund_count, date_str, tag,
        )
        # 用 OCR 结果更新已解析的基金净值
        for fund in funds:
            fund["最新净值"] = ocr_results.get(fund["基金名称"], fund["最新净值"])
    print(funds)
    # 保存
    csv_path = _save_funds_csv(funds, date_str, tag)
    df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)

    # 预览
    # _print_preview(df)
    if use_ocr:
        _print_ocr_stats(df)

    return {
        "total": len(funds),
        "ocr_success": len(ocr_results),
        "ocr_failed": len(ocr_failed_list),
        "parse_errors": len(parse_errors),
    }


class CrawlFailedError(Exception):
    """爬虫执行失败异常"""

    def __init__(self, message: str, original_error=None):
        super().__init__(message)
        self.message = message
        self.original_error = original_error


# ===================== 入口 =====================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="私募排排网抓取工具（支持 OCR 净值识别）"
    )
    parser.add_argument(
        "--tag",
        default=None,
        help="指定标签: private / public / money（不指定则爬取全部标签）"
    )
    args = parser.parse_args()

    tags_to_crawl = [args.tag] if args.tag else _TAG_KEY_LIST

    results = []
    for tag in tags_to_crawl:
        print(f"\n{'='*50}")
        print(f"开始爬取标签: {tag}")
        print(f"{'='*50}")
        try:
            result = crawl(tag=tag)
            result["tag"] = tag
            results.append(result)
            print(f"\n标签 {tag} 抓取完成: {result}")
        except TagNotFoundError as e:
            print(f"\n警告: 标签 '{tag}' 不存在，已跳过")
            print(f"  可用标签: {e.details.get('available_tags', _TAG_KEY_LIST)}")
            continue
        except CrawlFailedError as e:
            print(f"\n抓取失败 [{tag}]: {e}")
            continue
        except CookieError as e:
            print(f"\nCookie 错误 [{tag}]: {e.message}")
            print("请更新 SIMU_COOKIES 环境变量")
            exit(1)

