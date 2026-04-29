# -*- coding: utf-8 -*-
"""
cli.py - 命令行工具

提供命令行接口来操作爬虫和数据库

使用方法:
    python cli.py status          # 查看爬虫状态
    python cli.py crawl          # 手动触发爬取
    python cli.py import         # 导入 CSV 到数据库
    python cli.py list           # 列出所有基金
    python cli.py clear          # 清空数据库
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def cmd_status(args):
    """查看爬虫状态"""
    from models import CrawlRecord

    with app.app_context():
        latest = CrawlRecord.query.order_by(CrawlRecord.start_time.desc()).first()
        total = CrawlRecord.query.count()

        print("=" * 40)
        print("爬虫状态")
        print("=" * 40)
        print(f"总爬取次数: {total}")
        if latest:
            print(f"最近爬取: {latest.crawl_date}")
            print(f"状态: {latest.status}")
            print(f"基金数量: {latest.total_funds}")
        else:
            print("暂无爬取记录")


def cmd_crawl(args):
    """手动触发爬取"""
    from app_state import crawl_status
    from tasks.crawl_task import _run_crawl_task_inner, run_crawl_task

    if crawl_status["is_running"]:
        print("爬虫正在运行中...")
        return

    tag = args.tag or "private"
    print(f"开始爬取，标签={tag}...")
    run_crawl_task(use_ocr=not args.no_ocr, app=app, tag=tag)
    print("爬取完成")


def cmd_import(args):
    """导入 CSV 到数据库"""
    from tasks.crawl_task import _import_csv_to_db
    from datetime import datetime

    date_str = args.date or datetime.now().strftime("%Y%m%d")
    tag = args.tag or "private"
    count = _import_csv_to_db(date_str, tag=tag)
    print(f"导入完成，共 {count} 条记录")


def cmd_list(args):
    """列出基金"""
    from models import db, Fund

    with app.app_context():
        query = Fund.query

        if args.name:
            query = query.filter(Fund.fund_name.contains(args.name))

        if args.date:
            query = query.filter(Fund.crawl_date == args.date)

        funds = query.order_by(Fund.crawl_time.desc()).limit(args.limit).all()

        print(f"共找到 {len(funds)} 条记录:")
        print("-" * 80)
        for f in funds:
            print(f"{f.fund_name:30s} | {f.net_value:10s} | {f.crawl_date}")


def cmd_clear(args):
    """清空数据库"""
    from models import db, Fund, CrawlRecord

    with app.app_context():
        if args.confirm:
            Fund.query.delete()
            CrawlRecord.query.delete()
            db.session.commit()
            print("数据库已清空")
        else:
            print("请使用 --confirm 参数确认清空操作")


def main():
    parser = argparse.ArgumentParser(description="私募基金监控平台命令行工具")
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # status
    subparsers.add_parser("status", help="查看爬虫状态")

    # crawl
    crawl_parser = subparsers.add_parser("crawl", help="手动触发爬取")
    crawl_parser.add_argument("--no-ocr", action="store_true", help="禁用 OCR")
    crawl_parser.add_argument("--tag", type=str, default="private", help="基金标签 (default: private)")

    # import
    import_parser = subparsers.add_parser("import", help="导入 CSV 到数据库")
    import_parser.add_argument("--date", type=str, help="指定日期 (YYYYMMDD)")
    import_parser.add_argument("--tag", type=str, default="private", help="基金标签 (default: private)")

    # list
    list_parser = subparsers.add_parser("list", help="列出基金")
    list_parser.add_argument("--name", type=str, help="基金名称过滤")
    list_parser.add_argument("--date", type=str, help="指定日期")
    list_parser.add_argument("--limit", type=int, default=20, help="限制数量")

    # clear
    clear_parser = subparsers.add_parser("clear", help="清空数据库")
    clear_parser.add_argument("--confirm", action="store_true", help="确认清空")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    from flask import Flask
    from models import db

    global app
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///funds.db"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)

    # 根据命令执行
    if args.command == "status":
        cmd_status(args)
    elif args.command == "crawl":
        cmd_crawl(args)
    elif args.command == "import":
        cmd_import(args)
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "clear":
        cmd_clear(args)


if __name__ == "__main__":
    main()
