# -*- coding: utf-8 -*-
"""routes/page.py - 页面路由"""

from flask import Blueprint, render_template

page_bp = Blueprint("page", __name__)


@page_bp.route("/")
def index():
    return render_template("index.html")


@page_bp.route("/stats")
def stats_page():
    return render_template("stats.html")
