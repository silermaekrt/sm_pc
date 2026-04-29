# -*- coding: utf-8 -*-
"""
retry_utils.py - 重试机制工具

提供函数装饰器用于重试逻辑
"""

import time
import logging
from functools import wraps
from typing import Callable, Tuple, Type

logger = logging.getLogger(__name__)

# 可重试的异常类型元组
RetryableException = (ConnectionError, TimeoutError, OSError)


def retry_on_exception(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: Tuple[Type[Exception], ...] = RetryableException,
    on_retry: Callable[[Exception, int], None] = None,
    log_retry: bool = True,
):
    """
    重试装饰器

    Args:
        max_attempts: 最大尝试次数（默认 3）
        delay: 初始延迟秒数（默认 1.0）
        backoff: 退避系数（默认 2.0，每次失败延迟翻倍）
        exceptions: 可重试的异常类型元组
        on_retry: 重试时的回调函数，签名 on_retry(exception, attempt)
        log_retry: 是否记录重试日志
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            current_delay = delay
            last_exception = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    if attempt == max_attempts:
                        if log_retry:
                            logger.error(
                                "%s 失败 %d 次后放弃: %s",
                                func.__name__, max_attempts, e
                            )
                        raise

                    if log_retry:
                        logger.warning(
                            "%s 第 %d/%d 次尝试失败: %s, %.1f秒后重试...",
                            func.__name__, attempt, max_attempts, e, current_delay
                        )

                    if on_retry:
                        on_retry(e, attempt)

                    time.sleep(current_delay)
                    current_delay *= backoff

            # 不应该到达这里，但以防万一
            if last_exception:
                raise last_exception

        return wrapper

    return decorator
