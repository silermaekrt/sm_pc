# -*- coding: utf-8 -*-
"""
services/crawler/ocr.py - OCR 净值识别

职责：Tesseract 初始化、净值图像裁剪、OCR 识别、结果解析
"""

import os
import re
import sys
import time

import config
from config import (
    TESSERACT_PATH, OCR_PSM_MODES, NET_VALUE_DECIMAL,
    CROP_X_OFFSET, CROP_Y_OFFSET, CROP_HEIGHT_RATIO,
)
from app_logging import get_logger

logger = get_logger(__name__)


# ===================== Tesseract 初始化 =====================
def init_tesseract():
    """初始化 Tesseract OCR，返回 pytesseract 模块或 None"""
    try:
        import pytesseract

        if sys.platform == "win32":
            tesseract_exe = os.path.join(TESSERACT_PATH, "tesseract.exe")
        else:
            tesseract_exe = os.path.join(TESSERACT_PATH, "tesseract")
        if os.path.exists(tesseract_exe):
            pytesseract.pytesseract.tesseract_cmd = tesseract_exe
            return pytesseract
        else:
            return None
    except ImportError:
        logger.warning("pytesseract 未安装，请运行 pip install pytesseract")
        return None
    except Exception as e:
        logger.error(f"Tesseract 初始化失败: {e}")
        return None


# ===================== 净值提取 =====================
def format_net_value(val: str) -> str:
    """将净值字符串规范化为小数点后4位"""
    if "." in val:
        integer, decimal = val.split(".")
        decimal = (decimal + "0000")[:4]
        return f"{integer}.{decimal}"
    return f"{val}.0000"


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
        return format_net_value(match.group())
    return ""


# ===================== OCR 识别 =====================
def recognize_net_value(pytesseract, img, fund_name_for_debug: str = "", retry_count: int = 0) -> str:
    """
    用 Tesseract OCR 识别净值数字。
    返回识别的净值字符串（如 "1.2345"），失败返回 ""
    """
    if pytesseract is None:
        return ""

    try:
        best_non_decimal = ""
        for psm in OCR_PSM_MODES:
            raw = pytesseract.image_to_string(img, lang="eng", config=f"--psm {psm}")
            net_value = extract_net_value(raw)
            if net_value:
                if "." in net_value:
                    return net_value
                best_non_decimal = net_value
        return best_non_decimal

    except Exception:
        if retry_count < config.OCR_MAX_RETRIES:
            time.sleep(0.5)
            return recognize_net_value(pytesseract, img, fund_name_for_debug, retry_count + 1)
        return ""


# ===================== 累计净值截图 OCR =====================

# 列边界（像素），基于截图宽度 1242px
_CUMULATIVE_COL_DATE_LEFT = 0
_CUMULATIVE_COL_DATE_RIGHT = 206
_CUMULATIVE_COL_NAV_LEFT = 734
_CUMULATIVE_COL_NAV_RIGHT = 1039


def recognize_cumulative_nav_from_screenshot(
    screenshot_path: str,
    fund_name: str,
    debug_dir: str = None,
) -> list:
    """
    对累计净值截图做 OCR，提取日期和累计净值(分红再投资)。

    Args:
        screenshot_path: 截图文件路径
        fund_name:       基金名称（仅用于日志）
        debug_dir:       若非 None，保存左右两列裁剪图用于调试

    Returns:
        [{"净值日期": "2026-01-02", "累计净值(分红再投资)": "1.2345"}, ...]
        按日期降序排列。
    """
    from PIL import Image

    pytesseract = init_tesseract()
    if not pytesseract:
        logger.warning(f"Tesseract 不可用（基金={fund_name}）")
        return []

    img = Image.open(screenshot_path).convert("RGB")
    w, h = img.size
    logger.info(f"截图尺寸: {w}x{h}（基金={fund_name}）")

    # 按实际宽度等比缩放列边界
    scale = w / 1242.0
    left_l = int(_CUMULATIVE_COL_DATE_LEFT * scale)
    left_r = int(_CUMULATIVE_COL_DATE_RIGHT * scale)
    right_l = int(_CUMULATIVE_COL_NAV_LEFT * scale)
    right_r = int(_CUMULATIVE_COL_NAV_RIGHT * scale)

    left_crop = img.crop((left_l, 0, left_r, h))
    right_crop = img.crop((right_l, 0, right_r, h))

    if debug_dir:
        import os as _os
        _os.makedirs(debug_dir, exist_ok=True)
        base = os.path.splitext(os.path.basename(screenshot_path))[0]
        left_crop.save(os.path.join(debug_dir, f"{base}_col_left.png"))
        right_crop.save(os.path.join(debug_dir, f"{base}_col_right.png"))

    # OCR 日期列
    raw_dates = pytesseract.image_to_string(left_crop, lang="eng", config="--psm 6")
    dates_raw = re.findall(r"\d{4}[-/.]\d{2}[-/.]\d{2}", raw_dates)
    dates = [d.replace("/", "-").replace(".", "-") for d in dates_raw]
    if not dates:
        logger.warning(f"OCR 未提取到日期（基金={fund_name}）")
        return []

   

    # OCR 累计净值(分红再投资)列
    raw_navs = pytesseract.image_to_string(right_crop, lang="eng", config="--psm 6")
    logger.debug(f"NAV列原始OCR: {repr(raw_navs)}")

    # 按行处理，确保顺序对应日期
    nav_lines = raw_navs.strip().split("\n")
    floats = []
    missing_count = 0

    for line in nav_lines:
        line = line.strip()
        if not line:
            continue
        # 先尝试匹配标准浮点数
        match = re.search(r"(?<!\d)(\d{1,4}\.\d{1,6})(?!\d)", line)
        if match:
            val = match.group(1)
            if float(val.split(".")[0]) < 100:
                floats.append(val)
                continue
        # 如果匹配不到，尝试5-6位整数（可能是丢失小数点的净值）
        int_match = re.search(r"(?<!\d)(\d{5,6})(?!\d)", line)
        if int_match:
            raw_int = int_match.group(1)
            if len(raw_int) == 5:
                candidate = f"{raw_int[0]}.{raw_int[1:]}"  # 27141 -> 2.7141
            elif len(raw_int) == 6:
                candidate = f"{raw_int[0:2]}.{raw_int[2:]}"  # 123456 -> 12.3456
            else:
                candidate = None
            if candidate and float(candidate.split(".")[0]) < 100:
                floats.append(candidate)
                logger.info(f"恢复净值: {raw_int} -> {candidate}")
                missing_count += 1
                continue
        # 跳过表头等非数据行（如 RiP 1BRA) ©）
        if not re.search(r"\d", line):
            continue

    logger.debug(f"提取到的净值列表: {floats}")

    n = len(dates)
    if n == 0:
        logger.warning(f"未识别到日期（基金={fund_name}）")
        return []

    # 日期列和净值列应该行数一致，如果不一致可能是表头被误识别
    if len(floats) == n - 1:
        logger.info(f"日期比净值多1，跳过第一个日期（表头）重新配对（基金={fund_name}）")
        dates = dates[1:]
        n = len(dates)
    elif len(floats) < n:
        logger.warning(f"无法恢复足够净值（基金={fund_name}）")
        return []

    navs = floats[:n]

    results = []
    for i in range(n):
        date = dates[i]
        nav_raw = navs[i]
        results.append({
            "净值日期": date,
            "累计净值(分红再投资)": format_net_value(nav_raw),
        })

    # 按日期降序
    results.sort(key=lambda r: r["净值日期"], reverse=True)
    return results


# ===================== 图像处理与裁剪 =====================
def recognize_net_values(
    pytesseract,
    fund_positions: list,
    table_info: dict,
    table_screenshot_path: str = "",
    actual_fund_count: int = 0,
    date_str: str = "",
    tag: str = "",
    screenshot_bytes: bytes = None,
) -> tuple:
    """
    对表格截图进行 OCR 识别净值。
    支持从文件路径或 bytes 加载图片。
    返回 (ocr_results dict, failed list)
    """
    from utils.file import safe_filename

    if pytesseract is None:
        return {}, []

    try:
        from PIL import Image
        from io import BytesIO
        if screenshot_bytes:
            img = Image.open(BytesIO(screenshot_bytes)).convert("RGB")
        elif table_screenshot_path and os.path.exists(table_screenshot_path):
            img = Image.open(table_screenshot_path)
        else:
            return {}, []
    except Exception as e:
        logger.warning(f"PIL 打开截图失败，跳过 OCR（路径={table_screenshot_path}，错误={e}）")
        return {}, []

    crop_dir = os.path.join(config.SCREENSHOT_DIR, date_str, tag) if date_str and tag \
        else config.SCREENSHOT_DIR
    os.makedirs(crop_dir, exist_ok=True)


    ocr_results = {}
    ocr_failed_list = []

    for pos in fund_positions:
        fund_name = pos["fundName"]

        if not pos.get("netValueImg"):
            ocr_failed_list.append(fund_name)
            continue

        nv = pos["netValueImg"]
        local_x = nv["x"] - (table_info["x"] - config.CROP_MARGIN)
        local_y = nv["y"] - (table_info["y"] - config.CROP_MARGIN)

        crop_box = (
            max(0, int(local_x - CROP_X_OFFSET)),
            max(0, int(local_y - CROP_Y_OFFSET)),
            min(img.width, int(local_x + nv["width"] + CROP_X_OFFSET)),
            min(img.height, int(local_y + nv["height"] * CROP_HEIGHT_RATIO)),
        )

        if crop_box[2] <= crop_box[0] or crop_box[3] <= crop_box[1]:
            ocr_failed_list.append(fund_name)
            continue

        net_value_img = img.crop(crop_box)

        if config.SAVE_SCREENSHOT:
            debug_crop_path = os.path.join(crop_dir, f"{safe_filename(fund_name)}.png")
            net_value_img.save(debug_crop_path)

        net_value = recognize_net_value(pytesseract, net_value_img, fund_name)

        if net_value:
            ocr_results[fund_name] = net_value
        else:
            ocr_failed_list.append(fund_name)

    return ocr_results, ocr_failed_list
