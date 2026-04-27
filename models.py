# -*- coding: utf-8 -*-
"""
models.py - 数据库模型

使用 SQLAlchemy ORM 进行数据库操作
"""

from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import base64

db = SQLAlchemy()


class Fund(db.Model):
    """
    基金数据模型
    存储每次爬取后的基金数据
    """
    __tablename__ = "funds"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    fund_name = db.Column(db.String(100), nullable=False, comment="基金名称")
    fund_code = db.Column(db.String(20), comment="基金代码")
    strategy = db.Column(db.String(50), comment="策略")
    net_value_date = db.Column(db.String(20), comment="净值日期")
    net_value = db.Column(db.String(20), comment="最新净值（OCR识别）")
    net_change = db.Column(db.String(20), comment="净值变动")
    net_change_cmp = db.Column(db.String(20), comment="净值对比日期")
    annual_return = db.Column(db.String(20), comment="成立来年化")
    this_year = db.Column(db.String(20), comment="今年来")
    last_week = db.Column(db.String(20), comment="上周")
    last_week_range = db.Column(db.String(50), comment="上周区间")
    one_month = db.Column(db.String(20), comment="近一月")
    three_month = db.Column(db.String(20), comment="近三月")
    six_month = db.Column(db.String(20), comment="近半年")
    one_year = db.Column(db.String(20), comment="近一年")
    two_year = db.Column(db.String(20), comment="近两年")
    three_year = db.Column(db.String(20), comment="近三年")
    five_year = db.Column(db.String(20), comment="近五年")
    since_inception = db.Column(db.String(20), comment="成立来")
    this_week = db.Column(db.String(20), comment="本周")
    this_week_range = db.Column(db.String(50), comment="本周区间")
    drawdown = db.Column(db.String(20), comment="回撤")
    crawl_time = db.Column(db.DateTime, default=datetime.now, comment="爬取时间")
    crawl_date = db.Column(db.Date, comment="爬取日期（用于去重）")

    __table_args__ = (
        db.Index("idx_fund_name", "fund_name"),
        db.Index("idx_crawl_time", "crawl_time"),
        db.Index("idx_crawl_date", "crawl_date"),
        db.Index("idx_fund_name_crawl_date", "fund_name", "crawl_date"),
    )

    def to_dict(self):
        """转换为字典，用于 JSON 响应"""
        return {
            "id": self.id,
            "fund_name": self.fund_name,
            "fund_code": self.fund_code or "",
            "strategy": self.strategy or "",
            "net_value_date": self.net_value_date or "",
            "net_value": self.net_value or "",
            "net_change": self.net_change or "",
            "net_change_cmp": self.net_change_cmp or "",
            "annual_return": self.annual_return or "",
            "this_year": self.this_year or "",
            "last_week": self.last_week or "",
            "last_week_range": self.last_week_range or "",
            "one_month": self.one_month or "",
            "three_month": self.three_month or "",
            "six_month": self.six_month or "",
            "one_year": self.one_year or "",
            "two_year": self.two_year or "",
            "three_year": self.three_year or "",
            "five_year": self.five_year or "",
            "since_inception": self.since_inception or "",
            "this_week": self.this_week or "",
            "this_week_range": self.this_week_range or "",
            "drawdown": self.drawdown or "",
            "crawl_time": self.crawl_time.strftime("%Y-%m-%d %H:%M:%S") if self.crawl_time else "",
            "crawl_date": self.crawl_date.strftime("%Y-%m-%d") if self.crawl_date else "",
        }


class CrawlRecord(db.Model):
    """
    爬取记录模型
    记录每次爬取任务的执行情况
    """
    __tablename__ = "crawl_records"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    crawl_date = db.Column(db.Date, nullable=False, comment="爬取日期")
    start_time = db.Column(db.DateTime, default=datetime.now, comment="开始时间")
    end_time = db.Column(db.DateTime, comment="结束时间")
    status = db.Column(db.String(20), default="running", comment="状态: running/success/failed")
    total_funds = db.Column(db.Integer, default=0, comment="抓取基金数量")
    ocr_success = db.Column(db.Integer, default=0, comment="OCR成功数量")
    error_message = db.Column(db.Text, comment="错误信息")

    def to_dict(self):
        return {
            "id": self.id,
            "crawl_date": self.crawl_date.strftime("%Y-%m-%d") if self.crawl_date else "",
            "start_time": self.start_time.strftime("%Y-%m-%d %H:%M:%S") if self.start_time else "",
            "end_time": self.end_time.strftime("%Y-%m-%d %H:%M:%S") if self.end_time else "",
            "status": self.status,
            "total_funds": self.total_funds,
            "ocr_success": self.ocr_success,
            "error_message": self.error_message or "",
        }


class LoginCredential(db.Model):
    """
    登录凭证模型
    存储用户名密码用于自动刷新 Cookie
    """
    __tablename__ = "login_credentials"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(100), nullable=False, comment="用户名")
    password_encrypted = db.Column(db.String(256), nullable=False, comment="加密密码")
    is_active = db.Column(db.Boolean, default=True, comment="是否启用")
    last_refresh = db.Column(db.DateTime, comment="上次刷新时间")
    refresh_interval = db.Column(db.Integer, default=60, comment="刷新间隔(分钟)")
    created_at = db.Column(db.DateTime, default=datetime.now, comment="创建时间")
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")
    last_error = db.Column(db.Text, comment="上次错误信息")

    __table_args__ = (
        db.Index("idx_is_active", "is_active"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "is_active": self.is_active,
            "last_refresh": self.last_refresh.isoformat() if self.last_refresh else None,
            "refresh_interval": self.refresh_interval,
            "created_at": self.created_at.isoformat() if self.created_at else "",
            "last_error": self.last_error or "",
        }


# ===================== 密码加密工具 =====================
def encrypt_password_simple(password: str, secret: str = "simu_monitor_key") -> str:
    """简单加密：Base64 + XOR（用于本项目内部存储）"""
    key_bytes = secret.encode("utf-8")
    password_bytes = password.encode("utf-8")
    encrypted = bytearray()
    for i, b in enumerate(password_bytes):
        encrypted.append(b ^ key_bytes[i % len(key_bytes)])
    return base64.b64encode(bytes(encrypted)).decode("utf-8")


def decrypt_password_simple(encrypted: str, secret: str = "simu_monitor_key") -> str:
    """简单解密"""
    key_bytes = secret.encode("utf-8")
    encrypted_bytes = base64.b64decode(encrypted.encode("utf-8"))
    decrypted = bytearray()
    for i, b in enumerate(encrypted_bytes):
        decrypted.append(b ^ key_bytes[i % len(key_bytes)])
    return bytes(decrypted).decode("utf-8")
