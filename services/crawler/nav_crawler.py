# -*- coding: utf-8 -*-
"""
services/crawler/nav_crawler.py - 累计净值爬取

方案：截取历史净值表格可见区域 → 分列裁剪 + OCR 识别
"""

import os

import config
from services.crawler import ocr as _ocr_mod
from utils.file import safe_filename
from app_logging import get_logger

logger = get_logger(__name__)


def save_cumulative_screenshot(new_page, tag: str, fund_name: str) -> tuple:
    """
    截取历史净值表格可见区域 + OCR，返回截图路径和净值列表。
    """
    safe_name = safe_filename(fund_name)
    fund_dir = os.path.join(config.CUMULATIVE_BASE_DIR, tag, safe_name)
    os.makedirs(fund_dir, exist_ok=True)
    screenshot_path = os.path.join(fund_dir, f"{safe_name}.png")

    table_locator = new_page.locator(".el-table--scrollable-y")
    if not table_locator.count():
        logger.warning(f"未找到历史净值表格（基金={fund_name}）")
        return screenshot_path, []

    # 截图（先写临时文件，OCR 成功后再 rename，保护已有截图不被覆盖）
    debug_dir = fund_dir if config.SAVE_SCREENSHOT else None
    temp_path = screenshot_path.replace(".png", "_temp.png")
    try:
        table_locator.first.screenshot(path=temp_path)
    except Exception as e:
        logger.warning(f"截图失败（基金={fund_name}）: {e}")
        return screenshot_path, []

    # OCR（复用通用累计净值识别函数）
    ocr_data = _ocr_mod.recognize_cumulative_nav_from_screenshot(
        temp_path, fund_name, debug_dir
    )

    # 有效数据判定：OCR 返回的列表中，有累计净值字段值的行
    valid = sum(1 for r in ocr_data if r["累计净值(分红再投资)"])
    logger.info(
        f"历史净值提取完成（基金={fund_name}）：共 {len(ocr_data)} 行，"
        f"有效净值 {valid} 条"
    )

    # OCR 成功（至少有条有效数据）才正式保存截图，失败则删除临时文件
    if valid > 0:
        os.replace(temp_path, screenshot_path)
    else:
        try:
            os.remove(temp_path)
        except OSError:
            pass

    return screenshot_path, ocr_data
