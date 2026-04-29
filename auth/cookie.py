# -*- coding: utf-8 -*-
"""
auth/cookie.py - Cookie 自动刷新管理

职责：
- 通过模拟登录获取新 Cookie
- 将 Cookie 保存到 .env 文件
- 后台定时检查并刷新 Cookie
"""

import os
import re
import logging
import requests
from datetime import datetime

import config
from models import db, LoginCredential
from models import encrypt_password_simple, decrypt_password_simple

logger = logging.getLogger(__name__)


def refresh_cookies_from_login(username: str, password: str) -> tuple:
    """
    通过模拟登录获取新的 Cookie。
    返回 (success, cookies_str, error_msg)
    """
    try:
        session = requests.Session()
        session.headers.update({
            "User-Agent": config.USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
        })

        # 步骤1: 访问登录页获取 token
        login_page_url = "https://www.simuwang.com/user/login"
        resp = session.get(login_page_url, timeout=30)
        resp.raise_for_status()

        token = None
        token_patterns = [
            r'name="_token"\s+value="([^"]+)"',
            r'name="token"\s+value="([^"]+)"',
            r'"token"\s*:\s*"([^"]+)"',
            r'_csrf\s*=\s*"([^"]+)"',
        ]
        for pattern in token_patterns:
            match = re.search(pattern, resp.text)
            if match:
                token = match.group(1)
                break

        # 步骤2: 执行登录
        login_url = "https://www.simuwang.com/user/login"
        login_data = {
            "account": username,
            "password": password,
            "remember": "on",
        }
        if token:
            login_data["_token"] = token

        login_resp = session.post(login_url, data=login_data, timeout=30, allow_redirects=True)

        cookies_dict = session.cookies.get_dict()
        if not cookies_dict:
            return False, None, "登录后未获取到任何 Cookie"

        cookie_parts = [f"{k}={v}" for k, v in cookies_dict.items()]
        cookies_str = "; ".join(cookie_parts)

        verify_resp = session.get(config.SIMU_URL, timeout=30)
        if verify_resp.status_code == 200 and "登录" not in verify_resp.text[:500]:
            return True, cookies_str, None
        else:
            return True, cookies_str, "Cookie 获取成功但验证失败"

    except requests.exceptions.Timeout:
        return False, None, "登录请求超时"
    except requests.exceptions.RequestException as e:
        return False, None, f"网络请求失败: {str(e)}"
    except Exception as e:
        return False, None, f"未知错误: {str(e)}"


def save_cookies_to_env(cookies: str):
    """将 Cookie 保存到 .env 文件"""
    from config import BASE_DIR
    env_path = os.path.join(BASE_DIR, ".env")
    lines = []
    found = False
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith("SIMU_COOKIES="):
                    lines.append(f"SIMU_COOKIES={cookies}\n")
                    found = True
                else:
                    lines.append(line)

    if not found:
        lines.append(f"SIMU_COOKIES={cookies}\n")

    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(lines)

    logger.info("Cookie 已保存到 .env 文件")


def check_and_refresh_cookies():
    """检查并刷新 Cookie（如果到期）"""
    cred = LoginCredential.query.filter_by(is_active=True).first()
    if not cred:
        return

    if cred.last_refresh:
        elapsed = (datetime.now() - cred.last_refresh).total_seconds() / 60
        if elapsed < cred.refresh_interval:
            return
        logger.info(f"Cookie 刷新检查：距上次 {elapsed:.0f} 分钟（间隔 {cred.refresh_interval} 分钟）")

    logger.info("Cookie 刷新到期，开始自动刷新...")

    try:
        password = decrypt_password_simple(cred.password_encrypted)
    except Exception as e:
        logger.error(f"密码解密失败: {e}")
        cred.last_error = f"密码解密失败: {e}"
        db.session.commit()
        return

    success, cookies, error_msg = refresh_cookies_from_login(cred.username, password)

    if success and cookies:
        os.environ["SIMU_COOKIES"] = cookies
        save_cookies_to_env(cookies)
        cred.last_refresh = datetime.now()
        cred.last_error = None
        db.session.commit()
        logger.info("Cookie 自动刷新成功")
    else:
        logger.error(f"Cookie 自动刷新失败: {error_msg}")
        cred.last_error = error_msg
        db.session.commit()
