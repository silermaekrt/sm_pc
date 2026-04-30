# -*- coding: utf-8 -*-
"""
logging.py - 统一日志配置

功能：
- 控制台输出 + 按日期分割的日志文件
- 统一日志格式
- 可通过环境变量配置日志级别
- 全局复用，无冗余配置

使用方法：
    from logging import get_logger
    logger = get_logger(__name__)
"""

import os
import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path


# ===================== 日志目录 =====================
_LOG_DIR = Path(__file__).parent / "logs"
_LOG_DIR.mkdir(exist_ok=True)


# ===================== 日志格式 =====================
_LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


# ===================== 日志级别（支持环境变量覆盖）=====================
_LOG_LEVEL = os.getenv("SIMU_LOG_LEVEL", "INFO").upper()
_LEVEL_MAP = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}
_LEVEL = _LEVEL_MAP.get(_LOG_LEVEL, logging.INFO)


# ===================== 已初始化的标记 =====================
_initialized = False


def _setup_logging():
    """初始化日志系统（只执行一次）"""
    global _initialized
    if _initialized:
        return
    _initialized = True

    # 禁用已有的 root handlers（避免重复）
    root = logging.getLogger()
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    # 控制台 Handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(_LEVEL)
    console_formatter = logging.Formatter(_LOG_FORMAT, _DATE_FORMAT)
    console_handler.setFormatter(console_formatter)

    # 文件 Handler（按日期分割）
    file_handler = TimedRotatingFileHandler(
        filename=str(_LOG_DIR / "app.log"),
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    file_handler.setLevel(_LEVEL)
    file_formatter = logging.Formatter(_LOG_FORMAT, _DATE_FORMAT)
    file_handler.setFormatter(file_formatter)

    # 配置 root logger
    root.setLevel(_LEVEL)
    root.addHandler(console_handler)
    root.addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    """
    获取带统一配置的 logger。

    Args:
        name: 通常传入 __name__，表示模块名称

    Returns:
        配置好的 logger 实例
    """
    _setup_logging()
    return logging.getLogger(name)
