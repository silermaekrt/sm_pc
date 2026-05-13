# -*- coding: utf-8 -*-
"""
routes/export.py - 数据导出 API

改用 DataService 统一数据访问层。
"""

from datetime import datetime

from flask import Blueprint, jsonify, request, Response

import config
from config import ALL_TAG_KEYS, FUND_TYPES
from services import DataService, COLUMN_NAME_MAP
from utils.http import json_error as _error

from app_logging import get_logger
logger = get_logger(__name__)

export_bp = Blueprint("export", __name__)


@export_bp.route("/export", methods=["GET"])
def export_data():
    """导出基金数据（CSV/JSON/XLSX）"""
    import pandas as pd

    export_format = request.args.get("format", "csv").lower()
    tag = request.args.get("tag", "private", type=str)
    crawl_date = request.args.get("date", "", type=str).strip()
    search = request.args.get("name", "", type=str).strip()

    if export_format not in ("csv", "json", "xlsx"):
        return _error("不支持的导出格式，仅支持 csv/json/xlsx")
    if tag not in ALL_TAG_KEYS:
        return _error(f"不支持的标签 '{tag}'，可选: {ALL_TAG_KEYS}")

    # 确定爬取日期
    if not crawl_date:
        date_range = DataService.get_data_date_range(tag)
        if not date_range["max_date"]:
            return _error(f"标签 '{tag}' 没有可导出的数据，请先执行抓取", 404)
        crawl_date = date_range["max_date"]

    # 使用 DataService 获取数据
    result = DataService.get_all_funds(
        tag=tag, page=1, per_page=10000, search=search, crawl_date=crawl_date
    )
    items = result.get("items", [])

    df = pd.DataFrame(items)
    # 排除内部字段
    drop_cols = ["fund_name", "crawl_date", "crawl_time", "_sort"]
    df = df[[c for c in df.columns if c not in drop_cols]]

    # 列名中文化
    rename_map = {k: f"{v[0]} ({v[1]})" for k, v in COLUMN_NAME_MAP.items() if k in df.columns}
    df = df.rename(columns=rename_map)

    tag_name = next((t["name"] for t in FUND_TYPES if t["key"] == tag), tag)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename_base = f"fund_{tag}_{crawl_date}_{timestamp}"

    if export_format == "csv":
        import io
        output = io.StringIO()
        df.to_csv(output, index=False, encoding="utf-8-sig")
        return Response(
            output.getvalue(),
            mimetype="text/csv; charset=utf-8-sig",
            headers={
                "Content-Disposition": f"attachment; filename={filename_base}.csv",
                "Content-Type": "text/csv; charset=utf-8-sig",
            },
        )

    if export_format == "json":
        return Response(
            df.to_json(force_ascii=False, orient="records"),
            mimetype="application/json; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename={filename_base}.json"},
        )

    # xlsx
    import io
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=f"{tag_name}基金数据")
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename={filename_base}.xlsx",
            "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        },
    )
