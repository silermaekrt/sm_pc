# -*- coding: utf-8 -*-
"""
app.py - Flask Web 应用入口

私募基金监控平台 API 服务

模块结构：
  routes/   - API 路由（page, fund, crawl, export, auth）
  tasks/    - 爬虫任务函数与统一调度器
  auth/     - 登录认证与 Cookie 管理
  app_state - 全局状态（避免循环导入）
"""

import logging
from flask import Flask
from models import db

import config
from app_state import crawl_status
from routes import register_routes

# ===================== Flask 应用配置 =====================
app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///funds.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["JSON_AS_ASCII"] = False

db.init_app(app)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)


# ===================== 注册路由 =====================
register_routes(app)


# ===================== 应用启动 =====================
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        logger.info("数据库初始化完成")

    import sys
    if "--debug" not in sys.argv:
        try:
            from tasks.crawl_task import init_scheduler
            scheduler = init_scheduler()
        except Exception as e:
            logger.warning(f"定时任务调度器启动失败: {e}")

    app.run(debug=True, port=5000, host="0.0.0.0")
