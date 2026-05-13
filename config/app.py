# -*- coding: utf-8 -*-
"""
config/app.py - Flask / 路径相关配置

惰性初始化目录，避免在 import 时产生副作用。
"""

import os
from pathlib import Path

# ===================== 路径（惰性初始化）=====================
BASE_DIR = Path(__file__).parent.parent.absolute()


def _get_path(name: str, default: str) -> str:
    """惰性获取路径值，首次访问时确保目录存在"""
    value = os.getenv(name, default)
    os.makedirs(value, exist_ok=True)
    return value


class _LazyPath:
    """延迟解析路径属性，初次访问时触发目录创建"""

    def __init__(self, env_var: str, default: str):
        self._env_var = env_var
        self._default = default
        self._value = None

    def _resolve(self):
        if self._value is None:
            self._value = os.getenv(self._env_var, self._default)
            os.makedirs(self._value, exist_ok=True)
        return self._value

    def __str__(self):
        return self._resolve()

    def __repr__(self):
        return repr(self._resolve())

    def __fspath__(self):
        return self._resolve()

    def __eq__(self, other):
        return self._resolve() == (other._resolve() if isinstance(other, _LazyPath) else other)

    def __ne__(self, other):
        return self._resolve() != (other._resolve() if isinstance(other, _LazyPath) else other)

    def __hash__(self):
        return hash(self._resolve())


DATA_DIR = _LazyPath("SIMU_SAVE_DIR", "data")
SCREENSHOT_DIR = _LazyPath("SIMU_SCREENSHOT_DIR", "screenshots")
CUMULATIVE_BASE_DIR = _LazyPath("CUMULATIVE_DIR", "cumulative")
INDICES_BASE_DIR = _LazyPath("INDICES_DIR", "indices")
# 基准指数文件根目录（支持通过环境变量 BASE_INDEX_DIR 配置）
# 默认: {BASE_DIR}/base/{yyyy}/{m}/{d}/QT_INDEXQUOTE.txt
# 可配置为其他路径如: /data/v1/raw/JY/IndexQuote/{yyyy}/{m}/{d}/QT_INDEXQUOTE.txt
BASE_INDEX_DIR = os.getenv("BASE_INDEX_DIR", "base")
