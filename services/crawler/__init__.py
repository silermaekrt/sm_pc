# -*- coding: utf-8 -*-
"""
services/crawler/__init__.py - 爬虫服务包

提供爬虫核心功能，与 Flask 完全解耦。
"""

from services.crawler.runner import crawl, crawl_cumulative_nav

__all__ = ["crawl", "crawl_cumulative_nav"]
