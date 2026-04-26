# -*- coding: utf-8 -*-
"""
retry_utils.py - 重试机制工具

提供函数装饰器和上下文管理器用于重试逻辑
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


class RetryContext:
    """
    上下文管理器式的重试控制

    用法:
        with RetryContext(max_attempts=3, delay=1.0) as retry:
            if some_condition:
                retry.fail("自定义失败原因")
            return success_value
    """

    def __init__(
        self,
        max_attempts: int = 3,
        delay: float = 1.0,
        backoff: float = 2.0,
        exceptions: Tuple[Type[Exception], ...] = RetryableException,
        on_retry: Callable[[Exception, int], None] = None,
        on_failure: Callable[[Exception], None] = None,
    ):
        self.max_attempts = max_attempts
        self.delay = delay
        self.backoff = backoff
        self.exceptions = exceptions
        self.on_retry = on_retry
        self.on_failure = on_failure
        self.current_attempt = 0
        self.current_delay = delay
        self._should_retry = True
        self._last_exception = None

    def __enter__(self):
        self.current_attempt += 1
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            # 没有异常，成功
            self._should_retry = False
            return False

        # 检查是否是可重试的异常
        if not issubclass(exc_type, self.exceptions):
            # 不可重试的异常，直接抛出
            self._last_exception = exc_val
            if self.on_failure:
                self.on_failure(exc_val)
            return False

        self._last_exception = exc_val

        # 检查是否还有重试次数
        if self.current_attempt >= self.max_attempts:
            logger.warning(
                "重试次数用尽 (%d/%d): %s",
                self.current_attempt, self.max_attempts, exc_val
            )
            if self.on_failure:
                self.on_failure(exc_val)
            return False

        # 执行重试
        logger.warning(
            "第 %d/%d 次尝试失败: %s, %.1f秒后重试...",
            self.current_attempt, self.max_attempts, exc_val, self.current_delay
        )

        if self.on_retry:
            self.on_retry(exc_val, self.current_attempt)

        time.sleep(self.current_delay)
        self.current_delay *= self.backoff

        # 返回 True 抑制异常，让代码继续执行进行重试
        return True

    def fail(self, message: str):
        """手动标记失败，抛出异常"""
        raise RetryFailedError(message)

    @property
    def can_retry(self) -> bool:
        return self.current_attempt < self.max_attempts

    @property
    def is_last_attempt(self) -> bool:
        return self.current_attempt == self.max_attempts


class RetryFailedError(Exception):
    """手动触发的重试失败"""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


