# -*- coding: utf-8 -*-
"""
run_ocr.py - 私募排排网抓取工具（CLI 入口）

内部实现已迁移至 services/crawler/ 包。此文件仅保留：
- 向后兼容的模块级常量和异常
- CLI 入口点（python run_ocr.py）
- 保留原有的函数签名和调用方式

使用方法：
    python run_ocr.py           # 抓取 + OCR 识别
    python run_ocr.py --tag private
    python run_ocr.py --cumulative --tag private
"""

import argparse
import sys
import os

# 确保项目根目录在模块搜索路径中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 加载 .env 文件（CLI 独立运行时需要）
from dotenv import load_dotenv
load_dotenv()

from app_logging import get_logger
from exceptions import TagNotFoundError, CrawlFailedError, CookieError
from services.crawler import crawl, crawl_cumulative_nav
import config

logger = get_logger(__name__)

if not config.get_raw_cookie():
    logger.error("SIMU_COOKIES 环境变量未设置，无法抓取。请先配置 SIMU_COOKIES 后重试。")
    exit(1)

_TAG_KEY_LIST = config.get_fund_type_lists()[0]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="私募排排网抓取工具（支持 OCR 净值识别）"
    )
    parser.add_argument(
        "--tag",
        default=None,
        help="指定标签: private / public / money（不指定则爬取全部标签）"
    )
    parser.add_argument(
        "--cumulative",
        action="store_true",
        help="爬取每个基金的累计净值（历史净值/分红），保存截图和 CSV"
    )
    args = parser.parse_args()

    if args.cumulative:
        tag = args.tag or "private"
        logger.info(f"=== 累计净值爬取测试 | 标签={tag} ===")
        result = crawl_cumulative_nav(tag=tag)
        logger.info(f"结果: {result}")
    else:
        tags_to_crawl = [args.tag] if args.tag else _TAG_KEY_LIST

        results = []
        for tag in tags_to_crawl:
            logger.info(f"开始爬取标签: {tag}")
            try:
                result = crawl(tag=tag)
                result["tag"] = tag
                results.append(result)
                logger.info(f"\n标签 {tag} 抓取完成: {result}")
            except TagNotFoundError as e:
                logger.warning(f"标签 '{tag}' 不存在，已跳过")
                logger.warning(f"  可用标签: {e.details.get('available_tags', _TAG_KEY_LIST)}")
                continue
            except CrawlFailedError as e:
                logger.error(f"抓取失败 [{tag}]: {e.message}")
                continue
            except CookieError as e:
                logger.error(f"Cookie 错误 [{tag}]: {e.message}")
                logger.error("请更新 SIMU_COOKIES 环境变量")
                exit(1)
            except Exception as e:
                logger.exception(f"抓取失败 [{tag}]: {e}")
                continue
