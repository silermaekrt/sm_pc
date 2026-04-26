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


class DataParseError(CrawlerBaseError):
    """数据解析错误"""

    def __init__(self, message: str, field: str = None, raw_data: str = None):
        details = {}
        if field:
            details["field"] = field
        if raw_data:
            # 截断过长的原始数据
            details["raw_data"] = raw_data[:200] if len(raw_data) > 200 else raw_data
        super().__init__(message, code="PARSE_ERROR", details=details)


class OCRError(CrawlerBaseError):
    """OCR 识别错误"""

    def __init__(self, message: str, fund_name: str = None, retry_count: int = 0):
        details = {"retry_count": retry_count}
        if fund_name:
            details["fund_name"] = fund_name
        super().__init__(message, code="OCR_ERROR", details=details)


class ScreenshotError(CrawlerBaseError):
    """截图相关错误"""

    def __init__(self, message: str, file_path: str = None):
        details = {}
        if file_path:
            details["file_path"] = file_path
        super().__init__(message, code="SCREENSHOT_ERROR", details=details)


class CSVError(CrawlerBaseError):
    """CSV 文件操作错误"""

    def __init__(self, message: str, file_path: str = None):
        details = {}
        if file_path:
            details["file_path"] = file_path
        super().__init__(message, code="CSV_ERROR", details=details)


class ConfigError(CrawlerBaseError):
    """配置错误"""

    def __init__(self, message: str, config_key: str = None):
        details = {}
        if config_key:
            details["config_key"] = config_key
        super().__init__(message, code="CONFIG_ERROR", details=details)


def format_error_detail(error: Exception) -> dict:
    """格式化错误详情，用于日志和响应"""
    if isinstance(error, CrawlerBaseError):
        return {
            "type": error.code,
            "message": error.message,
            "details": error.details,
        }

    # 处理非自定义异常
    return {
        "type": type(error).__name__.upper(),
        "message": str(error),
        "details": {},
    }
