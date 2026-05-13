# -*- coding: utf-8 -*-
"""
测试累计净值爬取 - 仅爬取私募 (private)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from tasks.crawl_task import run_cumulative_task

if __name__ == "__main__":
    from app import app

    print("=" * 60)
    print("测试累计净值爬取 - 私募")
    print("=" * 60)

    # 仅爬取私募 (private)，跳过已有的
    run_cumulative_task(
        app=app,
        tag="private",
        batch_size=5,
        skip_if_exists=False,
        wait_between=10
    )

    print("=" * 60)
    print("测试完成")
    print("=" * 60)
