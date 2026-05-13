# -*- coding: utf-8 -*-
"""
utils/http.py - HTTP 响应辅助函数
"""

from flask import jsonify


def json_error(message: str, status_code: int = 400):
    """标准错误响应"""
    return jsonify({"status": "error", "message": message}), status_code


def json_success(data: dict, status_code: int = 200):
    """标准成功响应"""
    return jsonify({"status": "success", **data}), status_code
