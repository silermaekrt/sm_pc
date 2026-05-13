# -*- coding: utf-8 -*-
"""
utils/file.py - 文件操作工具
"""

import os
import re
import unicodedata


def safe_filename(name: str) -> str:
    """
    将名称转为安全的文件名（去除非法字符并截断至80字符）。

    增强版本：
    - 使用 Unicode NFC 标准化
    - 移除 Windows 非法字符
    - 限制长度
    """
    # Unicode 标准化（NFC 格式，兼容 Windows 文件系统）
    name = unicodedata.normalize('NFC', name)

    # 移除或替换 Windows 非法字符
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name)

    # 限制长度（Windows 路径长度限制 260 字符）
    name = name[:80]

    return name.strip()


def normalize_for_comparison(name: str) -> str:
    """
    标准化基金名称用于比较和匹配。
    返回小写 + NFC 标准化后的名称。
    """
    return unicodedata.normalize('NFC', str(name)).strip().lower()


def ensure_dir(path: str) -> None:
    """确保目录存在，不存在则创建"""
    os.makedirs(path, exist_ok=True)
