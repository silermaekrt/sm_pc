# -*- coding: utf-8 -*-
"""
app.py - Flask Web 应用入口

私募基金监控平台 API 服务
"""

from dotenv import load_dotenv
load_dotenv()

from flask import Flask
from app_logging import get_logger

import config
from app_state import crawl_status
from routes import register_routes

logger = get_logger(__name__)

# ===================== Flask 应用配置 =====================
app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False

# 初始化 TAG_MODEL_MAP（必须在路由注册前完成）
config.init_tag_model_map()

# ===================== 注册路由 =====================
register_routes(app)

# ===================== 应用启动 =====================
if __name__ == "__main__":
    import sys
    if "--debug" not in sys.argv:
        try:
            from tasks.crawl_task import init_scheduler
            scheduler = init_scheduler(app=app)
        except Exception as e:
            logger.warning(f"定时任务调度器启动失败: {e}")

    app.run(debug=True, port=5000, host="0.0.0.0")
