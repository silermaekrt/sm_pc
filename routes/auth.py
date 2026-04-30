# -*- coding: utf-8 -*-
"""
routes/auth.py - 登录凭证 API
"""

import os
from datetime import datetime

from flask import Blueprint, jsonify, request
from app_logging import get_logger

from models import db, LoginCredential, encrypt_password_simple, decrypt_password_simple
from auth.cookie import refresh_cookies_from_login, save_cookies_to_env

logger = get_logger(__name__)
auth_bp = Blueprint("auth", __name__)


def _error(message: str, status_code: int = 400):
    return jsonify({"status": "error", "message": message}), status_code


def _active_cred():
    """获取当前激活的凭证，无则返回 None"""
    return LoginCredential.query.filter_by(is_active=True).first()


def _save_cookies(cookies: str):
    os.environ["SIMU_COOKIES"] = cookies
    save_cookies_to_env(cookies)


@auth_bp.route("/login", methods=["POST"])
def save_login_credentials():
    """POST /api/auth/login - 保存登录凭证"""
    if not request.json:
        return _error("请提供用户名和密码")

    username = request.json.get("username", "").strip()
    password = request.json.get("password", "")
    refresh_interval = request.json.get("refresh_interval", 60, type=int)

    if not username or not password:
        return _error("用户名和密码不能为空")
    if refresh_interval < 10:
        return _error("刷新间隔不能少于10分钟")

    cred = _active_cred()
    if cred:
        cred.username = username
        cred.password_encrypted = encrypt_password_simple(password)
        cred.refresh_interval = refresh_interval
        cred.updated_at = datetime.now()
        cred.last_error = None
    else:
        cred = LoginCredential(
            username=username,
            password_encrypted=encrypt_password_simple(password),
            is_active=True, refresh_interval=refresh_interval,
        )
        db.session.add(cred)
    db.session.commit()

    success, cookies, error_msg = refresh_cookies_from_login(username, password)

    if success and cookies:
        _save_cookies(cookies)
        cred.last_refresh = datetime.now()
        cred.last_error = None
        db.session.commit()
        return jsonify({
            "message": "登录凭证保存成功，Cookie 已刷新",
            "last_refresh": datetime.now().isoformat(),
        })

    cred.last_error = error_msg
    db.session.commit()
    return jsonify({
        "status": "partial",
        "message": f"凭证保存成功，但 Cookie 刷新失败: {error_msg}",
        "hint": "请确认用户名密码正确，下次刷新间隔到期时会自动重试",
    })


@auth_bp.route("/credentials", methods=["GET"])
def get_auth_credentials():
    """GET /api/auth/credentials - 获取凭证状态（不返回密码）"""
    cred = _active_cred()
    if not cred:
        return jsonify({"has_credentials": False})
    return jsonify({
        "has_credentials": True,
        "username": cred.username,
        "last_refresh": cred.last_refresh.isoformat() if cred.last_refresh else None,
        "refresh_interval": cred.refresh_interval,
        "is_active": cred.is_active,
        "last_error": cred.last_error or "",
        "created_at": cred.created_at.isoformat() if cred.created_at else "",
    })


@auth_bp.route("/credentials", methods=["DELETE"])
def delete_auth_credentials():
    """DELETE /api/auth/credentials - 删除凭证"""
    cred = _active_cred()
    if cred:
        cred.is_active = False
        db.session.commit()
    return jsonify({"message": "登录凭证已删除"})


@auth_bp.route("/refresh", methods=["POST"])
def manual_refresh_cookies():
    """POST /api/auth/refresh - 手动刷新 Cookie"""
    cred = _active_cred()
    if not cred:
        return _error("没有保存的登录凭证，请先调用 /api/auth/login", 404)

    try:
        password = decrypt_password_simple(cred.password_encrypted)
    except (ValueError, TypeError):
        return _error("密码解密失败，请重新保存凭证", 500)

    success, cookies, error_msg = refresh_cookies_from_login(cred.username, password)

    if success and cookies:
        _save_cookies(cookies)
        cred.last_refresh = datetime.now()
        cred.last_error = None
        db.session.commit()
        return jsonify({
            "message": "Cookie 刷新成功",
            "cookies": (cookies[:50] + "...") if len(cookies) > 50 else cookies,
        })

    cred.last_error = error_msg
    db.session.commit()
    return _error(f"Cookie 刷新失败: {error_msg}", 500)
