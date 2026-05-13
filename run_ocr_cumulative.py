# -*- coding: utf-8 -*-
"""
run_ocr_cumulative.py - 对历史净值截图进行 OCR 识别并保存 CSV

使用方法：
    python run_ocr_cumulative.py "截图路径" "基金名称" [--tag exp]

OCR 逻辑已提取到 services/crawler/ocr.py 中的 recognize_cumulative_nav_from_screenshot()。
"""

import argparse
import os

from dotenv import load_dotenv
load_dotenv()

import config
from services.crawler import ocr as _ocr_mod
from services.crawler import storage as _storage_mod
from app_logging import get_logger

logger = get_logger(__name__)


def main():
    parser = argparse.ArgumentParser(description="OCR 识别历史净值截图并保存 CSV")
    parser.add_argument("screenshot", help="截图路径")
    parser.add_argument("fund_name", help="基金名称")
    parser.add_argument(
        "--tag", default="exp",
        help="标签目录（默认 exp）"
    )
    parser.add_argument(
        "--no-merge", action="store_true",
        help="禁用追加合并，直接覆盖 CSV"
    )
    args = parser.parse_args()

    debug_dir = None
    if config.SAVE_SCREENSHOT:
        from utils.file import safe_filename
        safe_name = safe_filename(args.fund_name)
        debug_dir = os.path.join(config.SCREENSHOT_DIR, "ocr_debug", safe_name)

    results = _ocr_mod.recognize_cumulative_nav_from_screenshot(
        args.screenshot, args.fund_name, debug_dir
    )
    if not results:
        print("OCR 未提取到数据")
        return

    # 复用 storage 中的统一保存逻辑
    csv_path = _storage_mod.save_cumulative_csv(
        results, args.tag, args.fund_name, merge=not args.no_merge
    )
    print(f"结果已保存: {csv_path}")


if __name__ == "__main__":
    main()
