# -*- coding: utf-8 -*-
"""
models.py - 数据库模型（SQLAlchemy ORM）
"""

from datetime import datetime
import base64

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

_FUND_FIELDS = [
    "id", "tag", "fund_name", "fund_code", "strategy", "net_value_date",
    "net_value", "net_change", "net_change_cmp", "annual_return",
    "this_year", "last_week", "last_week_range", "one_month",
    "three_month", "six_month", "one_year", "two_year", "three_year",
    "five_year", "since_inception", "this_week", "this_week_range",
    "drawdown", "crawl_time", "crawl_date",
]


class Fund(db.Model):
    """基金数据（统一存储私募/公募/货币基金，通过 tag 字段区分）"""
    __tablename__ = "funds"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tag = db.Column(db.String(20), default="private", comment="基金标签: private/public/money")
    fund_name = db.Column(db.String(100), nullable=False, comment="基金名称")
    fund_code = db.Column(db.String(20), comment="基金代码")
    strategy = db.Column(db.String(50), comment="策略")
    net_value_date = db.Column(db.String(20), comment="净值日期")
    net_value = db.Column(db.String(20), comment="最新净值")
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
    crawl_date = db.Column(db.Date, comment="爬取日期")

    __table_args__ = (
        db.Index("idx_fund_tag", "tag"),
        db.Index("idx_fund_name", "fund_name"),
        db.Index("idx_crawl_time", "crawl_time"),
        db.Index("idx_crawl_date", "crawl_date"),
        db.Index("idx_fund_tag_name_date", "tag", "fund_name", "crawl_date"),
    )

    def to_dict(self):
        result = {}
        for field in _FUND_FIELDS:
            val = getattr(self, field, None)
            if field == "crawl_time":
                result[field] = val.strftime("%Y-%m-%d %H:%M:%S") if val else ""
            elif field == "crawl_date":
                result[field] = val.strftime("%Y-%m-%d") if val else ""
            else:
                result[field] = val or ""
        return result


class CrawlRecord(db.Model):
    """爬取记录"""
    __tablename__ = "crawl_records"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tag = db.Column(db.String(20), default="private", comment="基金标签")
    crawl_date = db.Column(db.Date, nullable=False, comment="爬取日期")
    start_time = db.Column(db.DateTime, default=datetime.now, comment="开始时间")
    end_time = db.Column(db.DateTime, comment="结束时间")
    status = db.Column(db.String(20), default="running", comment="running/success/failed")
    total_funds = db.Column(db.Integer, default=0, comment="抓取基金数量")
    ocr_success = db.Column(db.Integer, default=0, comment="OCR成功数量")
    error_message = db.Column(db.Text, comment="错误信息")

    __table_args__ = (
        db.Index("idx_crawl_record_tag", "tag"),
        db.Index("idx_crawl_record_status", "status"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "tag": self.tag,
            "crawl_date": self.crawl_date.strftime("%Y-%m-%d") if self.crawl_date else "",
            "start_time": self.start_time.strftime("%Y-%m-%d %H:%M:%S") if self.start_time else "",
            "end_time": self.end_time.strftime("%Y-%m-%d %H:%M:%S") if self.end_time else "",
            "status": self.status,
            "total_funds": self.total_funds,
            "ocr_success": self.ocr_success,
            "error_message": self.error_message or "",
        }


class LoginCredential(db.Model):
    """登录凭证（用于自动刷新 Cookie）"""
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

    __table_args__ = (db.Index("idx_is_active", "is_active"),)

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


# ===================== 密码加密（Base64 + XOR）=====================
def encrypt_password_simple(password: str, secret: str = None) -> str:
    if secret is None:
        from config import ENCRYPTION_SECRET
        secret = ENCRYPTION_SECRET
    key = secret.encode()
    encrypted = bytes([b ^ key[i % len(key)] for i, b in enumerate(password.encode())])
    return base64.b64encode(encrypted).decode()


def decrypt_password_simple(encrypted: str, secret: str = None) -> str:
    if secret is None:
        from config import ENCRYPTION_SECRET
        secret = ENCRYPTION_SECRET
    key = secret.encode()
    decrypted = bytes([b ^ key[i % len(key)] for i, b in enumerate(base64.b64decode(encrypted.encode()))])
    return decrypted.decode()
