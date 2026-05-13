# -*- coding: utf-8 -*-
"""
exceptions.py - 自定义异常类

定义爬虫相关的异常类型，便于错误分类和处理
"""


class CrawlerBaseError(Exception):
    """爬虫基类异常"""

    def __init__(self, message: str, code: str = None, details: dict = None):
        super().__init__(message)
        self.message = message
        self.code = code or "UNKNOWN_ERROR"
        self.details = details or {}


class NetworkError(CrawlerBaseError):
    """网络相关错误"""

    def __init__(self, message: str, url: str = None, status_code: int = None):
        details = {}
        if url:
            details["url"] = url
        if status_code:
            details["status_code"] = status_code
        super().__init__(message, code="NETWORK_ERROR", details=details)


class BrowserError(CrawlerBaseError):
    """浏览器操作错误"""

    def __init__(self, message: str, action: str = None, timeout: int = None):
        details = {}
        if action:
            details["action"] = action
        if timeout:
            details["timeout"] = timeout
        super().__init__(message, code="BROWSER_ERROR", details=details)


class PageLoadError(BrowserError):
    """页面加载失败"""

    def __init__(self, message: str, url: str = None, timeout: int = None):
        super().__init__(message, action="page_load", timeout=timeout)
        self.code = "PAGE_LOAD_ERROR"
        if url:
            self.details["url"] = url


class ElementNotFoundError(BrowserError):
    """页面元素未找到"""

    def __init__(self, message: str, selector: str = None):
        super().__init__(message, action="element_search")
        self.code = "ELEMENT_NOT_FOUND"
        if selector:
            self.details["selector"] = selector


class CookieError(CrawlerBaseError):
    """Cookie 相关错误"""

    def __init__(self, message: str, cookie_name: str = None, expired: bool = False):
        details = {"expired": expired}
        if cookie_name:
            details["cookie_name"] = cookie_name
        super().__init__(message, code="COOKIE_ERROR", details=details)




class CrawlFailedError(CrawlerBaseError):
    """爬虫执行失败异常（在 tasks/crawl_task.py 和 run_ocr.py 中使用）"""

    def __init__(self, message: str, original_error=None):
        super().__init__(message, code="CRAWL_FAILED", details={})
        self.original_error = original_error


class ScreenshotError(CrawlerBaseError):
    """截图相关错误"""

    def __init__(self, message: str, file_path: str = None):
        details = {}
        if file_path:
            details["file_path"] = file_path
        super().__init__(message, code="SCREENSHOT_ERROR", details=details)


class TagNotFoundError(CrawlerBaseError):
    """标签（Tab）未找到"""
    def __init__(self, tag: str, available_tags: list = None):
        details = {"tag": tag}
        if available_tags:
            details["available_tags"] = available_tags
        super().__init__(
            message=f"标签 '{tag}' 未找到或不存在，请检查标签名称",
            code="TAG_NOT_FOUND",
            details=details,
        )
