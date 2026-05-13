# -*- coding: utf-8 -*-
"""
services/crawler/runner.py - 爬虫统一入口

职责：编排浏览器会话、OCR、解析、保存流程
"""

import os
import time
from datetime import datetime

from playwright.sync_api import sync_playwright
from playwright.sync_api import Error as PlaywrightError

import config
from config import (
    USER_AGENT, VIEWPORT_WIDTH, VIEWPORT_HEIGHT,
    GOTO_TIMEOUT, SELECTOR_TIMEOUT,
    PAGE_WAIT_TIME, VIEWPORT_WAIT_TIME,
    SAVE_SCREENSHOT,
    MAX_RETRIES, RETRY_DELAY, RETRY_BACKOFF,
    CRAWL, CROP_MARGIN,
    CUMULATIVE_CRAWL_INTERVAL,
)
from app_logging import get_logger
from exceptions import (
    BrowserError, PageLoadError, ElementNotFoundError,
    CookieError, TagNotFoundError, ScreenshotError,
)
from services.crawler import browser, ocr, parser, storage, nav_crawler
from exceptions import CrawlFailedError
from utils.file import safe_filename

logger = get_logger(__name__)

if not config.get_raw_cookie():
    logger.warning("SIMU_COOKIES 环境变量未设置，Cookie 将为空，可能导致抓取失败")

_TAG_KEY_LIST = config.get_fund_type_lists()[0]


# ===================== 重试相关 =====================
PLAYWRIGHT_RETRY_EXCEPTIONS = (
    PlaywrightError,
    TimeoutError,
    OSError,
)


def _log_and_sleep(attempt: int, e: Exception):
    """记录重试日志并等待退避时间"""
    logger.warning(f"第 {attempt}/{MAX_RETRIES} 次尝试失败: {e}")
    sleep_time = RETRY_DELAY * (RETRY_BACKOFF ** (attempt - 1))
    logger.info(f"{sleep_time:.1f} 秒后进行第 {attempt + 1} 次尝试...")
    time.sleep(sleep_time)


# ===================== 浏览器会话 =====================
def _run_browser_session(use_ocr: bool, tag: str = "private", date_str: str = "") -> tuple:
    """
    执行单次浏览器会话：导航、截图、提取数据。
    返回 (fund_positions, table_info, table_screenshot_path, rows_data)
    """
    with sync_playwright() as p:
        browser_inst = p.chromium.launch(headless=CRAWL.HEADLESS, args=["--start-maximized"])
        context = browser_inst.new_context(user_agent=USER_AGENT, viewport=None)
        browser.setup_cookies(context)

        page = context.new_page()
        nav_result = browser.navigate_and_wait(page, tag)

        if not nav_result["has_data"]:
            return [], None, "", [], None

        fund_positions = nav_result["fund_positions"]
        table_info = nav_result["table_info"]
        rows_data = nav_result["rows_data"]

        # 总是截图用于 OCR，SAVE_SCREENSHOT 只控制是否保存到磁盘
        table_screenshot_path = ""
        screenshot_bytes = None
        if table_info:
            if SAVE_SCREENSHOT:
                table_screenshot_path = browser.capture_table_screenshot(
                    page, table_info, date_str, tag
                )
            else:
                screenshot_bytes = browser.capture_table_screenshot_bytes(page, table_info)

        context.close()
        browser_inst.close()
        return fund_positions, table_info, table_screenshot_path, rows_data, screenshot_bytes


# ===================== 核心爬取 =====================
def crawl(use_ocr: bool = True, tag: str = "private") -> dict:
    """
    抓取私募排排网数据，支持 OCR 净值识别。

    Args:
        use_ocr: 是否启用 OCR 识别净值（默认 True）
        tag: 爬取哪个标签（默认 "private"）

    Returns:
        dict: {"total", "ocr_success", "parse_errors"}
    """
    logger.info(f"开始抓取私募排排网 - 标签={tag}")

    date_str = datetime.now().strftime("%Y%m%d")

    pytesseract = None
    if use_ocr:
        pytesseract = ocr.init_tesseract()
        if pytesseract is None:
            logger.info("OCR 已禁用，仅抓取文字数据")
    else:
        logger.info("OCR 已禁用，仅抓取文字数据")

    crawl_error = None

    try:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                logger.info(f"第 {attempt}/{MAX_RETRIES} 次尝试 - 启动浏览器...")
                fund_positions, table_info, table_screenshot_path, rows_data, screenshot_bytes = \
                    _run_browser_session(use_ocr, tag, date_str)
                break

            except TagNotFoundError as e:
                logger.warning(f"标签 '{tag}' 不存在: {e.message}")
                raise  # 标签不存在不重试，直接向上抛出

            except CookieError as e:
                raise  # Cookie 错误不重试，直接向上抛出

            except (PageLoadError, ElementNotFoundError, BrowserError, ScreenshotError) as e:
                crawl_error = e
                if attempt < MAX_RETRIES:
                    _log_and_sleep(attempt, e)
                else:
                    raise

            except Exception as e:
                crawl_error = e
                if attempt < MAX_RETRIES:
                    _log_and_sleep(attempt, e)
                else:
                    raise
        else:
            # All retries exhausted without breaking
            if crawl_error is not None:
                raise CrawlFailedError(f"重试 {MAX_RETRIES} 次后仍失败: {crawl_error}", crawl_error)

    except CrawlFailedError:
        raise
    except (TagNotFoundError, CookieError):
        raise
    except Exception as e:
        raise CrawlFailedError(f"爬取出错: {e}", e)

    funds, parse_errors = parser.parse_funds(rows_data, {})

    if not funds:
        logger.warning(f"标签 '{tag}' 未提取到任何基金数据")
        return {
            "total": 0,
            "ocr_success": 0,
            "parse_errors": len(parse_errors),
        }

    actual_fund_count = len(funds)

    ocr_results = {}
    if use_ocr and pytesseract:
        ocr_results, _ = ocr.recognize_net_values(
            pytesseract, fund_positions, table_info, table_screenshot_path,
            actual_fund_count, date_str, tag, screenshot_bytes,
        )
        for fund in funds:
            fund["最新净值"] = ocr_results.get(fund["基金名称"], fund["最新净值"])

    csv_path = storage.save_funds_csv(funds, date_str, tag)

    import pandas as pd
    df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)

    if use_ocr:
        parser.print_ocr_stats(df)

    return {
        "total": len(funds),
        "ocr_success": len(ocr_results),
        "parse_errors": len(parse_errors),
    }

# ===================== 单基金累计净值爬取 =====================
def crawl_single_fund(tag: str, fund_name: str) -> dict:
    """
    对单个基金进入详情页的历史净值/分红，截图并 OCR 提取净值存入 CSV。

    Args:
        tag: 标签（如 "private"、"exp"）
        fund_name: 基金名称（精确匹配）

    Returns:
        dict: {"success": bool, "ocr_count": int, "benchmark": str, "error": str or None}
    """
    from utils.file import safe_filename as _safe_filename

    if tag not in config.ALL_TAG_KEYS:
        raise ValueError(f"不支持的标签 '{tag}'，可选: {config.ALL_TAG_KEYS}")

    logger.info(f"[单基金爬取] 开始，标签={tag}，基金={fund_name}")

    result = {"success": False, "ocr_count": 0, "benchmark": "", "error": None}

    browser_inst = None
    context = None
    page = None
    new_page = None

    try:
        with sync_playwright() as p:
            browser_inst = p.chromium.launch(headless=CRAWL.HEADLESS, args=["--start-maximized"])
            context = browser_inst.new_context(user_agent=USER_AGENT, viewport=None)
            browser.setup_cookies(context)
            page = context.new_page()

            nav_result = browser.navigate_and_wait(page, tag)
            if not nav_result["has_data"]:
                result["error"] = f"标签 '{tag}' 无可见数据"
                logger.warning(result["error"])
                return result

            safe_name = _safe_filename(fund_name)
            try:
                page.click(f"a[title='{safe_name}']")
                page.wait_for_timeout(PAGE_WAIT_TIME)
            except Exception:
                result["error"] = f"未找到基金 '{fund_name}' 的链接"
                logger.error(result["error"])
                return result

            pages = context.pages
            new_page = pages[-1]
            new_page.set_viewport_size({"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT})

            try:
                new_page.click("text=我已知悉并申请查看", timeout=3000)
            except Exception:
                try:
                    new_page.click("text=申请查看", timeout=3000)
                except Exception:
                    pass
            new_page.wait_for_timeout(PAGE_WAIT_TIME)

            benchmark_index = browser.extract_benchmark_index(new_page)
            logger.info(f"[单基金爬取] 基准指数: {benchmark_index or '未找到'}（基金={fund_name}）")
            result["benchmark"] = benchmark_index

            try:
                new_page.click('h2:has-text("历史净值/分红")', timeout=5000)
            except Exception:
                pass
            new_page.wait_for_timeout(PAGE_WAIT_TIME)

            screenshot_path, ocr_data = nav_crawler.save_cumulative_screenshot(
                new_page, tag, fund_name
            )

            if ocr_data:
                storage.save_cumulative_csv(ocr_data, tag, fund_name, merge=True, benchmark=benchmark_index)
                result["ocr_count"] = len(ocr_data)
                result["success"] = True
                logger.info(f"[单基金爬取] 完成，基金={fund_name}，OCR 数据 {len(ocr_data)} 条")
            else:
                result["error"] = "OCR 未提取到任何净值数据"
                logger.warning(result["error"])

            new_page.close()
            page.bring_to_front()
            page.wait_for_timeout(500)

    except Exception as e:
        result["error"] = f"爬取异常: {e}"
        logger.error(result["error"])
    finally:
        if new_page:
            try:
                new_page.close()
            except Exception:
                pass
        if page:
            try:
                page.close()
            except Exception:
                pass
        if context:
            try:
                context.close()
            except Exception:
                pass
        if browser_inst:
            try:
                browser_inst.close()
            except Exception:
                pass

    return result


# ===================== 批量累计净值爬取 =====================
def crawl_cumulative_nav(
    tag: str = "private",
    batch_index: int = 0,
    batch_size: int = 0,
    skip_if_exists: bool = False,
) -> dict:
    """
    对标签下每个基金进入详情页的历史净值/分红，截图并提取净值日期和累计净值存入 CSV。

    Args:
        tag: 标签（如 "private"、"exp"）
        batch_index: 批次索引（从0开始），配合 batch_size 使用
        batch_size: 每批处理的基金数量，0 表示不限制
        skip_if_exists: 是否跳过已有 CSV 文件的基金

    Returns:
        dict: {"success": int, "failed": int, "skipped": int}
    """
    if tag not in config.ALL_TAG_KEYS:
        raise ValueError(f"不支持的标签 '{tag}'，可选: {config.ALL_TAG_KEYS}")

    logger.info(f"[累计净值] 开始爬取，标签={tag}")

    browser_inst = None
    context = None
    page = None

    def _is_page_alive(p: "Page") -> bool:
        """检查页面是否仍然可用"""
        try:
            if p.is_closed():
                return False
            p.title()
            return True
        except Exception:
            return False

    def _ensure_page_on_top(p: "Page", interval_ms: int) -> bool:
        """尝试将页面置前并等待间隔，返回是否成功"""
        try:
            p.bring_to_front()
            p.wait_for_timeout(interval_ms)
            return True
        except Exception:
            return False

    try:
        with sync_playwright() as p:
            browser_inst = p.chromium.launch(headless=CRAWL.HEADLESS, args=["--start-maximized"])
            context = browser_inst.new_context(user_agent=USER_AGENT, viewport=None)
            browser.setup_cookies(context)
            page = context.new_page()

            nav_result = browser.navigate_and_wait(page, tag)
            if not nav_result["has_data"]:
                logger.warning(f"标签 '{tag}' 无可见数据")
                return {"success": 0, "failed": 0, "skipped": 0}

            fund_names = [pos["fundName"] for pos in nav_result["fund_positions"]]
            # 排序保证分批顺序稳定，不受页面渲染顺序影响
            fund_names = sorted(fund_names)
            logger.info(f"[累计净值] 共 {len(fund_names)} 个基金")

            # 分批处理
            if batch_size > 0:
                start_idx = batch_index * batch_size
                end_idx = start_idx + batch_size
                fund_names = fund_names[start_idx:end_idx]
                logger.info(f"[累计净值] 批次 {batch_index}，处理 {start_idx}-{end_idx}，共 {len(fund_names)} 个基金")

            fund_links = [{"name": name} for name in fund_names if name]

            success_count = 0
            failed_count = 0
            skipped_count = 0

            for idx, fund_info in enumerate(fund_links):
                fund_name = fund_info["name"]
                safe_name = safe_filename(fund_name)
                logger.info(f"[累计净值] 处理基金: {fund_name}")

                print(f"{idx + 1}/{len(fund_links)}: {fund_name}")

                # 跳过已有 CSV 的基金
                if skip_if_exists:
                    csv_path = storage._get_cumulative_csv_path(tag, fund_name)
                    if csv_path and os.path.exists(csv_path):
                        logger.info(f"[累计净值] 跳过已有数据: {fund_name}")
                        skipped_count += 1
                        continue

                new_page = None
                try:
                    # 检查主列表页是否还可用
                    if not _is_page_alive(page):
                        logger.warning("[累计净值] 主列表页已失效，重新导航...")
                        nav_result = browser.navigate_and_wait(page, tag)
                        if not nav_result["has_data"]:
                            logger.error("重新导航失败，终止任务")
                            break

                    page.click(f"a[title='{safe_name}']")
                    new_page = context.wait_for_event("page")
                    new_page.set_viewport_size(
                        {"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT}
                    )
                    new_page.wait_for_load_state("networkidle", timeout=15000)

                    # 等待"我已知悉"弹窗出现
                    try:
                        new_page.click("text=我已知悉并申请查看", timeout=3000)
                    except Exception:
                        try:
                            new_page.click("text=申请查看", timeout=3000)
                        except Exception:
                            pass
                    new_page.wait_for_load_state("networkidle", timeout=10000)

                    benchmark_index = browser.extract_benchmark_index(new_page)
                    logger.info(f"[累计净值] 基准指数: {benchmark_index or '未找到'}（基金={fund_name}）")

                    # 点击"历史净值/分红"并等待表格加载
                    try:
                        new_page.click('h2:has-text("历史净值/分红")', timeout=8000)
                    except Exception:
                        pass
                    new_page.wait_for_load_state("networkidle", timeout=10000)

                    screenshot_path, ocr_data = nav_crawler.save_cumulative_screenshot(
                        new_page, tag, fund_name
                    )

                    storage.save_cumulative_csv(ocr_data, tag, fund_name, merge=True, benchmark=benchmark_index)

                    if ocr_data:
                        success_count += 1
                    else:
                        failed_count += 1

                except Exception as e:
                    logger.error(f"[累计净值] 基金={fund_name} 处理失败: {e}")
                    failed_count += 1
                finally:
                    if new_page:
                        try:
                            new_page.close()
                        except Exception:
                            pass

                # 页面失效时 break，不再尝试后续基金（后续批次会重启浏览器）
                if not _is_page_alive(page):
                    logger.warning(f"[累计净值] 主列表页已失效（基金={fund_name}），终止当前批次")
                    break

                _ensure_page_on_top(page, CUMULATIVE_CRAWL_INTERVAL)

            logger.info(f"[累计净值] 完成：成功 {success_count}，失败 {failed_count}，跳过 {skipped_count}")
            return {"success": success_count, "failed": failed_count, "skipped": skipped_count}

    except Exception as e:
        logger.error(f"[累计净值] 爬取出错: {e}")
        return {"success": 0, "failed": 0, "skipped": 0}
    finally:
        if page:
            try:
                page.close()
            except Exception:
                pass
        if context:
            try:
                context.close()
            except Exception:
                pass
        if browser_inst:
            try:
                browser_inst.close()
            except Exception:
                pass
