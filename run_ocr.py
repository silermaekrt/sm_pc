# -*- coding: utf-8 -*-
"""
run_ocr.py - 带 OCR 净值识别的私募排排网抓取工具

使用方法：
    python run_ocr.py           # 抓取 + OCR 识别
    python run_ocr.py --no-ocr  # 仅抓取文字数据（不 OCR）
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
    NetworkError,
    BrowserError,
    PageLoadError,
    ElementNotFoundError,
    CookieError,
    DataParseError,
    OCRError,
    ScreenshotError,
    CSVError,
    format_error_detail,
)
from retry_utils import retry_on_exception, RetryContext

# ===================== 日志配置 =====================
logging.basicConfig(level=config.LOG_LEVEL, format=config.LOG_FORMAT)
logger = logging.getLogger(__name__)

if not config.get_raw_cookie():
    logger.warning("SIMU_COOKIES 环境变量未设置，Cookie 将为空，可能导致抓取失败")


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
                [{"name": k, "value": v, "domain": ".simuwang.com", "path": "/"}]
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


def _navigate_and_wait(page):
    """跳转到目标页面并等待表格加载"""
    try:
        page.goto(config.SIMU_URL, wait_until="load", timeout=config.GOTO_TIMEOUT)
        logger.info(f"页面加载完成: {page.title()}")
    except PlaywrightError as e:
        raise PageLoadError(f"页面加载失败: {e}", url=config.SIMU_URL, timeout=config.GOTO_TIMEOUT)

    try:
        page.wait_for_selector("tr.el-table__row", timeout=config.SELECTOR_TIMEOUT)
        logger.info("表格加载完成")
    except PlaywrightError:
        raise ElementNotFoundError(
            "表格行未找到，可能页面结构变化或数据为空",
            selector="tr.el-table__row",
        )

    page.wait_for_timeout(config.PAGE_WAIT_TIME)
    page.set_viewport_size(
        {"width": config.VIEWPORT_WIDTH, "height": config.VIEWPORT_HEIGHT}
    )
    page.wait_for_timeout(config.VIEWPORT_WAIT_TIME)


def _extract_positions(page) -> list:
    """从页面中提取所有基金行的位置信息"""
    try:
        positions = page.evaluate(
            """
() => {
    const rows = Array.from(document.querySelectorAll('tbody tr.el-table__row'));
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

    for (const row of rows) {
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


def _get_table_info(page) -> dict:
    """获取表格区域信息"""
    return page.evaluate(
        """
() => {
    const table = document.querySelector('.el-table__body-wrapper');
    if (!table) return null;
    const rect = table.getBoundingClientRect();
    return { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
}
"""
    )


def _capture_table_screenshot(page, table_info: dict) -> str:
    """截取表格区域并保存，返回截图路径"""
    clip_x = max(0, table_info["x"] - config.CROP_MARGIN)
    clip_y = max(0, table_info["y"] - config.CROP_MARGIN)
    clip_w = table_info["width"] + config.CROP_MARGIN * 2
    clip_h = table_info["height"] + config.CROP_MARGIN * 2

    logger.info(f"截图区域: x={clip_x}, y={clip_y}, w={clip_w}, h={clip_h}")

    try:
        screenshot_bytes = page.screenshot(
            type="png",
            clip={"x": clip_x, "y": clip_y, "width": clip_w, "height": clip_h},
        )
        screenshot_path = os.path.join(
            config.SCREENSHOT_DIR, "table_full_screenshot.png"
        )
        with open(screenshot_path, "wb") as f:
            f.write(screenshot_bytes)
        logger.info(f"表格截图已保存: {screenshot_path} ({len(screenshot_bytes)} bytes)")
        return screenshot_path
    except Exception as e:
        raise ScreenshotError(f"截图保存失败: {e}")


def _extract_text_data(page) -> list:
    """从页面提取所有行的文本数据"""
    try:
        rows_data = page.evaluate(
            """
() => {
    const rows = Array.from(document.querySelectorAll('tbody tr.el-table__row'));
    return rows.map(row => {
        const cells = Array.from(row.querySelectorAll('td'));
        return cells.map(cell => cell.innerText.trim());
    }).filter(cells => cells.length >= 18);
}
"""
        )
    except PlaywrightError as e:
        raise BrowserError(f"提取文本数据失败: {e}", action="evaluate_js")
    return rows_data


def _run_browser_session(use_ocr: bool) -> tuple:
    """
    执行单次浏览器会话：导航、截图、提取数据。
    返回 (fund_positions, table_info, table_screenshot_path, rows_data)
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=config.USER_AGENT)
        _setup_cookies(context)

        page = context.new_page()
        _navigate_and_wait(page)

        fund_positions = _extract_positions(page)
        table_info = _get_table_info(page)

        table_screenshot_path = ""
        if table_info:
            table_screenshot_path = _capture_table_screenshot(page, table_info)

        rows_data = _extract_text_data(page)

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
) -> tuple:
    """
    对表格截图进行 OCR 识别净值。
    actual_fund_count: 实际解析出的基金行数（用于统计分母）
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

        debug_crop_path = os.path.join(
            config.SCREENSHOT_DIR,
            f"CROP_{_safe_filename(fund_name)}_{i+1:02d}.png",
        )
        net_value_img.save(debug_crop_path)

        net_value = ocr_recognize_net_value(pytesseract, net_value_img, fund_name)

        if net_value:
            ocr_results[fund_name] = net_value
            logger.info(f"[{fund_name}] OCR成功: {net_value}")
        else:
            ocr_failed_list.append(fund_name)
            logger.debug(f"[{fund_name}] OCR失败")

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
            if len(row) < config.MIN_COLUMNS:
                raise DataParseError(
                    f"行 {idx + 1} 字段数不足: {len(row)} < {config.MIN_COLUMNS}",
                    field="row_length",
                )

            fund_name, fund_code, strategy = _parse_name_cell(row[1])
            net_value_date = row[2].strip()
            net_change, net_change_cmp = _parse_change_cell(row[3])
            annual_return = row[4].strip()
            this_year = row[5].strip()
            last_week, last_week_range = _parse_week_cell(row[6])
            one_month = row[7].strip()
            three_month = row[8].strip()
            six_month = row[9].strip()
            one_year = row[10].strip()
            two_year = row[11].strip()
            three_year = row[12].strip()
            five_year = row[13].strip()
            since_inception = row[14].strip()
            this_week, this_week_range = _parse_week_cell(row[15])
            drawdown = row[17].strip()

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
def _save_funds_csv(funds: list) -> str:
    """将基金数据保存为 CSV，返回文件路径"""
    date_str = datetime.now().strftime("%Y%m%d")
    path = os.path.join(config.DATA_DIR, f"simu_option_{date_str}.csv")

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
def crawl(use_ocr: bool = True):
    """
    抓取私募排排网数据，支持 OCR 净值识别。

    流程分为以下阶段：
      1. 初始化 Tesseract OCR
      2. 浏览器会话（导航 + 截图 + 提取数据）
      3. OCR 识别净值（可选）
      4. 解析基金数据
      5. 保存 CSV 并输出预览

    Args:
        use_ocr: 是否启用 OCR 识别净值（默认 True）
    """
    logger.info("开始抓取私募排排网 - 我的自选（Playwright）")

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
                _run_browser_session(use_ocr)
            break

        except (PageLoadError, ElementNotFoundError, BrowserError, ScreenshotError) as e:
            crawl_error = e
            logger.warning(f"第 {attempt}/{config.MAX_RETRIES} 次尝试失败: {e}")

            if attempt < config.MAX_RETRIES:
                sleep_time = config.RETRY_DELAY * (config.RETRY_BACKOFF ** (attempt - 1))
                logger.info(f"{sleep_time:.1f} 秒后进行第 {attempt + 1} 次尝试...")
                time.sleep(sleep_time)
            else:
                logger.error(f"重试次数用尽，最终失败: {e}")
                error_detail = format_error_detail(e)
                raise CrawlFailedError(f"抓取失败: {error_detail['message']}", e)

        except CookieError as e:
            raise e  # Cookie 错误不重试

        except Exception as e:
            crawl_error = e
            logger.error(f"发生未预期的错误: {e}")

            if attempt < config.MAX_RETRIES:
                sleep_time = config.RETRY_DELAY * (config.RETRY_BACKOFF ** (attempt - 1))
                logger.info(f"{sleep_time:.1f} 秒后进行第 {attempt + 1} 次尝试...")
                time.sleep(sleep_time)
            else:
                logger.error(f"重试次数用尽，最终失败: {e}")
                raise CrawlFailedError(f"抓取失败: {e}", e)

    # 解析
    ocr_results = {}  # 空结果，OCR 完成后会更新
    funds, parse_errors = _parse_funds(rows_data, ocr_results)

    if not funds:
        raise CrawlFailedError("未提取到任何有效基金数据", crawl_error or "unknown")

    actual_fund_count = len(funds)

    # OCR 识别
    ocr_results = {}
    ocr_failed_list = []
    if use_ocr and pytesseract:
        ocr_results, ocr_failed_list = _recognize_net_values(
            pytesseract, fund_positions, table_info, table_screenshot_path, actual_fund_count
        )
        # 用 OCR 结果更新已解析的基金净值
        for fund in funds:
            fund["最新净值"] = ocr_results.get(fund["基金名称"], fund["最新净值"])

    # 保存
    csv_path = _save_funds_csv(funds)
    df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)

    # 预览
    _print_preview(df)
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
    parser.add_argument("--no-ocr", action="store_true", help="禁用 OCR，仅抓取文字数据")
    args = parser.parse_args()

    try:
        result = crawl(use_ocr=not args.no_ocr)
        print(f"\n抓取完成: {result}")
    except CrawlFailedError as e:
        print(f"\n抓取失败: {e}")
        exit(1)
    except CookieError as e:
        print(f"\nCookie 错误: {e.message}")
        print("请更新 SIMU_COOKIES 环境变量")
        exit(1)
