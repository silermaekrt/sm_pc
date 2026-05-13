# -*- coding: utf-8 -*-
"""
config/fund.py - 基金类型与表格列索引配置
"""

import re

# ===================== 基金标签 =====================
FUND_TYPES = [
    {"key": "private", "name": "私募"},
    {"key": "public",  "name": "公募"},
    {"key": "money",   "name": "货币"},
    {"key": "exp",     "name": "指数"},
    {"key": "temp",     "name": "月"},
]
ALL_TAG_KEYS = [t["key"] for t in FUND_TYPES]
SCHEDULED_TAGS = [t["key"] for t in FUND_TYPES if t["key"] in ("public")]
# 累计净值定时爬取标签（与 SCHEDULED_TAGS 共用同一份配置）
SCHEDULED_CUMULATIVE_TAGS = SCHEDULED_TAGS


def get_fund_type_map():
    """key → name 映射字典"""
    return {t["key"]: t["name"] for t in FUND_TYPES}


def get_fund_type_lists():
    """(keys_list, names_list)"""
    keys = [t["key"] for t in FUND_TYPES]
    names = [t["name"] for t in FUND_TYPES]
    return keys, names


def init_tag_model_map():
    """Flask 启动时调用（本版本已简化为单模型，无需初始化）"""
    pass


# ===================== 表格列索引（与 DOM 绑定，勿随意修改顺序）=====================
class COL:
    FUND_NAME = 1; NET_VALUE_DATE = 2; NET_CHANGE = 3; ANNUAL_RETURN = 4
    THIS_YEAR = 5; LAST_WEEK = 6; ONE_MONTH = 7; THREE_MONTH = 8
    SIX_MONTH = 9; ONE_YEAR = 10; TWO_YEAR = 11; THREE_YEAR = 12
    FIVE_YEAR = 13; SINCE_INCEPTION = 14; THIS_WEEK = 15; DRAWDOWN = 17


# ===================== 数据验证 =====================
MIN_COLUMNS = 18
CODE_PATTERN = re.compile(r"[A-Z0-9]+")
