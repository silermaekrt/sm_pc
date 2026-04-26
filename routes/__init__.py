# -*- coding: utf-8 -*-
"""
routes/__init__.py - 注册所有 API 路由

职责：
- /          -> 主页
- /stats     -> 统计页面
- /api/*     -> 所有 API 路由
"""

from flask import Blueprint

from routes.page import page_bp
from routes.fund import fund_bp
from routes.crawl import crawl_bp
from routes.export import export_bp
from routes.auth import auth_bp


def register_routes(app):
    """将所有路由蓝图注册到 Flask 应用"""
    app.register_blueprint(page_bp)
    app.register_blueprint(fund_bp, url_prefix="/api")
    app.register_blueprint(crawl_bp, url_prefix="/api")
    app.register_blueprint(export_bp, url_prefix="/api")
    app.register_blueprint(auth_bp, url_prefix="/api/auth")
