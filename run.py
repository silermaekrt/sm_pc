# -*- coding: utf-8 -*-
"""
启动脚本 - 启动 Flask Web 服务

使用方法:
    python run.py              # 普通模式
    python run.py --port 8080  # 指定端口
    python run.py --no-scheduler  # 禁用定时任务
"""

import argparse
import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    parser = argparse.ArgumentParser(description="私募基金监控平台启动脚本")
    parser.add_argument("--port", type=int, default=5000, help="服务端口（默认 5000）")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="服务地址（默认 0.0.0.0）")
    parser.add_argument("--debug", action="store_true", help="启用调试模式")
    parser.add_argument("--no-scheduler", action="store_true", help="禁用定时任务")
    args = parser.parse_args()

    from app import app

    # 启动定时任务（除非明确禁用）
    if not args.no_scheduler and not args.debug:
        try:
            from tasks.crawl_task import init_scheduler
            scheduler = init_scheduler(app)
            print("定时任务调度器已启动")
            print("  - 每日 09:00 自动爬取")
            print("  - 每周一 09:30 自动爬取")
        except Exception as e:
            print(f"警告: 定时任务启动失败: {e}")
            print("定时任务将在下次启动时自动调度")

    print()
    print("=" * 50)
    print(f"私募基金监控平台已启动")
    print(f"访问地址: http://127.0.0.1:{args.port}")
    print("=" * 50)
    print("按 Ctrl+C 停止服务")

    # 启动 Flask
    app.run(
        host=args.host,
        port=args.port,
        debug=args.debug
    )


if __name__ == "__main__":
    main()
