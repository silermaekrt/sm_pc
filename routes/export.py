# -*- coding: utf-8 -*-
"""
routes/export.py - 数据导出 API 路由
"""

import logging
from datetime import datetime
from flask import Blueprint, jsonify, request, Response

from models import Fund, CrawlRecord

logger = logging.getLogger(__name__)
export_bp = Blueprint("export", __name__)


@export_bp.route("/export", methods=["GET"])
def export_data():
    """
    导出基金数据为 CSV/JSON/XLSX

    Query Parameters:
        format: 导出格式 (csv/json/xlsx)，默认 csv
        crawl_date: 爬取日期筛选，默认导出最新日期
        search: 搜索关键词
    """
    export_format = request.args.get("format", "csv").lower()
    crawl_date = request.args.get("crawl_date", "", type=str)
    search = request.args.get("search", "", type=str)

    if export_format not in ("csv", "json", "xlsx"):
        return jsonify({"error": "不支持的导出格式，仅支持 csv/json/xlsx"}), 400

    if not crawl_date:
        latest_record = CrawlRecord.query.filter(
            CrawlRecord.status == "success"
        ).order_by(CrawlRecord.end_time.desc()).first()
        if latest_record:
            crawl_date = latest_record.crawl_date
        else:
            return jsonify({"error": "没有可导出的数据，请先执行抓取"}), 404

    query = Fund.query.filter(Fund.crawl_date == crawl_date)
    if search:
        query = query.filter(Fund.fund_name.contains(search))

    funds = query.order_by(Fund.fund_name.asc()).all()

    if not funds:
        return jsonify({"error": f"日期 {crawl_date} 没有数据"}), 404

    import pandas as pd
    data = [f.to_dict() for f in funds]
    df = pd.DataFrame(data)
    df = df[[c for c in df.columns if c != "id"]]

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename_base = f"fund_export_{crawl_date}_{timestamp}"

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

    elif export_format == "json":
        return Response(
            df.to_json(force_ascii=False, orient="records"),
            mimetype="application/json; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename={filename_base}.json"},
        )

    elif export_format == "xlsx":
        import io
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="基金数据")
        output.seek(0)
        return Response(
            output.getvalue(),
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename={filename_base}.xlsx",
                "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            },
        )
