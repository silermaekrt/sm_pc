# -*- coding: utf-8 -*-
"""
services/csv_store.py - 纯 CSV 存储服务层

存储结构：
  data/YYYYMMDD/{tag}.csv           ← 爬取归档快照（权威数据源）
  data/.{tag}.index.json              ← 持久化索引文件
  cumulative/crawl_records.csv        ← 爬取记录

无 meta.csv，全部数据直接从 data/ 目录读取。
索引机制：爬取后生成 .index.json，加速 get_latest_fund_meta 查询。
"""

import os
import csv
import json
from datetime import datetime
from typing import Optional

import pandas as pd

import config
from utils.file import safe_filename

from app_logging import get_logger
logger = get_logger(__name__)

# ===================== 路径常量 =====================

CUMULATIVE_BASE = str(config.CUMULATIVE_BASE_DIR)
CRAWL_RECORDS_CSV = os.path.join(CUMULATIVE_BASE, "crawl_records.csv")

RECORD_COLUMNS = [
    "id", "tag", "crawl_date", "start_time", "end_time",
    "status", "total_funds", "ocr_success", "error_message",
]


# ===================== 索引文件机制 =====================

def _get_index_path(tag: str) -> str:
    """获取索引文件路径"""
    return os.path.join(str(config.DATA_DIR), f".{tag}.index.json")


def _ensure_index(tag: str) -> dict:
    """
    确保索引存在，返回索引数据。
    索引结构: {
        "version": 1,
        "last_updated": "YYYY-MM-DD HH:MM:SS",
        "funds": {
            "基金名称": {
                "latest_date": "YYYY-MM-DD",
                "csv_path": "path/to/file.csv"
            }
        }
    }
    """
    index_path = _get_index_path(tag)
    if os.path.exists(index_path):
        try:
            with open(index_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            logger.warning(f"索引文件损坏，将重新构建: {index_path}, 错误: {e}")
        except Exception as e:
            logger.warning(f"读取索引文件失败，将重新构建: {index_path}, 错误: {e}")
    return _build_index(tag)


def _build_index(tag: str) -> dict:
    """构建并保存索引"""
    index_path = _get_index_path(tag)
    data_dir = str(config.DATA_DIR)
    date_dirs = _list_date_dirs(data_dir)

    funds_map = {}
    for _, date_compact in date_dirs:
        csv_path = os.path.join(data_dir, date_compact, f"{tag}.csv")
        if not os.path.exists(csv_path):
            continue
        try:
            df = pd.read_csv(csv_path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
            name_col = _find_name_col(df)
            if not name_col:
                continue
            crawl_date_fmt = f"{date_compact[:4]}-{date_compact[4:6]}-{date_compact[6:8]}"
            for _, row in df.iterrows():
                fund_name = str(row.get(name_col, "")).strip()
                if not fund_name:
                    continue
                existing = funds_map.get(fund_name)
                if existing is None or crawl_date_fmt > existing.get("latest_date", ""):
                    funds_map[fund_name] = {
                        "latest_date": crawl_date_fmt,
                        "csv_path": csv_path,
                    }
        except Exception:
            continue

    index = {
        "version": 1,
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "funds": funds_map,
    }

    try:
        os.makedirs(os.path.dirname(index_path), exist_ok=True)
        with open(index_path, 'w', encoding='utf-8') as f:
            json.dump(index, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"写入索引文件失败: {index_path}, 错误: {e}")

    return index


def invalidate_index(tag: str) -> None:
    """使索引失效，爬取完成后调用"""
    index_path = _get_index_path(tag)
    if os.path.exists(index_path):
        try:
            os.remove(index_path)
        except Exception:
            pass


# ===================== 爬取记录 =====================

def _init_crawl_records_csv():
    if not os.path.exists(CRAWL_RECORDS_CSV):
        os.makedirs(os.path.dirname(CRAWL_RECORDS_CSV), exist_ok=True)
        with open(CRAWL_RECORDS_CSV, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=RECORD_COLUMNS)
            writer.writeheader()


class _CrawlRecordContext:
    """
    上下文管理器：创建爬取记录 → 执行任务 → 更新状态。
    统一爬取异步逻辑，避免在 routes 层重复编写 record 保存/更新模板。

    注意：不再管理 is_running 状态，交给外层 routes/_run 统一管理。

    用法：
        with _CrawlRecordContext(tag, "批量爬取") as ctx:
            # 执行任务
            ctx.update_success(total=10, ocr=10)
        # 或省略 update_*/status 参数时自动按异常/success 处理
    """

    def __init__(self, tag: str, label: str = ""):
        self.tag = tag
        self.label = label or tag
        self.record_id: str = ""
        self.crawl_date: str = ""
        self.start_time: str = ""

    def __enter__(self):
        from datetime import datetime as _dt
        now = _dt.now()
        self.crawl_date = now.strftime("%Y-%m-%d")
        self.start_time = now.strftime("%Y-%m-%d %H:%M:%S")
        self.record_id = save_crawl_record({
            "id": None,
            "tag": self.tag,
            "crawl_date": self.crawl_date,
            "start_time": self.start_time,
            "end_time": "",
            "status": "running",
            "total_funds": 0,
            "ocr_success": 0,
            "error_message": "",
        })
        return self

    def update(self, **fields):
        from datetime import datetime as _dt
        fields["id"] = self.record_id
        fields["tag"] = self.tag
        fields["crawl_date"] = self.crawl_date
        fields["start_time"] = self.start_time
        fields["end_time"] = _dt.now().strftime("%Y-%m-%d %H:%M:%S")
        save_crawl_record(fields)

    def update_success(self, total: int = 0, ocr: int = 0, error: str = ""):
        self.update(status="success", total_funds=total, ocr_success=ocr, error_message=error)

    def update_failed(self, error: str):
        self.update(status="failed", total_funds=0, ocr_success=0, error_message=error)

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False


def save_crawl_record(record: dict) -> str:
    """追加或更新 crawl_records.csv"""
    _init_crawl_records_csv()

    records = []
    if os.path.exists(CRAWL_RECORDS_CSV):
        try:
            records = pd.read_csv(CRAWL_RECORDS_CSV, dtype=str, keep_default_na=False, encoding="utf-8-sig").to_dict("records")
        except Exception:
            records = []

    record_id = record.get("id")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if record_id and str(record_id).strip():
        record_id = str(record_id).strip()
        found = False
        for r in records:
            if str(r.get("id", "")) == record_id:
                for k, v in record.items():
                    if k != "id":
                        r[k] = v if v is not None else ""
                found = True
                break
        if not found:
            new_record = {c: record.get(c, "") for c in RECORD_COLUMNS}
            new_record["id"] = record_id
            records.append(new_record)
    else:
        max_id = 0
        for r in records:
            try:
                mid = int(r.get("id", 0))
                if mid > max_id:
                    max_id = mid
            except (ValueError, TypeError):
                pass
        new_id = max_id + 1
        new_record = {c: record.get(c, "") for c in RECORD_COLUMNS}
        new_record["id"] = str(new_id)
        new_record["start_time"] = now_str
        records.append(new_record)
        record_id = str(new_id)

    with open(CRAWL_RECORDS_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=RECORD_COLUMNS)
        writer.writeheader()
        writer.writerows(records)

    return record_id


def get_crawl_records(tag: str = "", page: int = 1, per_page: int = 10) -> dict:
    """分页读取 crawl_records.csv，按 start_time 降序"""
    _init_crawl_records_csv()
    if not os.path.exists(CRAWL_RECORDS_CSV):
        return {"items": [], "total": 0, "page": page, "per_page": per_page, "pages": 0}
    try:
        df = pd.read_csv(CRAWL_RECORDS_CSV, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    except Exception:
        return {"items": [], "total": 0, "page": page, "per_page": per_page, "pages": 0}

    if tag and "tag" in df.columns:
        df = df[df["tag"] == tag]

    df["_sort"] = pd.to_datetime(df["start_time"], errors="coerce") if "start_time" in df.columns else pd.Series(dtype="datetime64[ns]")
    df = df.dropna(subset=["_sort"])
    df = df.sort_values("_sort", ascending=False)

    total = len(df)
    pages = max(1, (total + per_page - 1) // per_page)
    start = (page - 1) * per_page
    end = start + per_page

    page_df = df.iloc[start:end]
    items = page_df[RECORD_COLUMNS].to_dict("records")
    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
    }


def delete_crawl_records(ids: list[str]) -> int:
    """从 crawl_records.csv 中删除指定 id 的记录，返回删除条数"""
    _init_crawl_records_csv()
    if not os.path.exists(CRAWL_RECORDS_CSV):
        return 0
    try:
        records = pd.read_csv(CRAWL_RECORDS_CSV, dtype=str, keep_default_na=False, encoding="utf-8-sig").to_dict("records")
    except Exception:
        return 0

    id_set = set(str(i).strip() for i in ids)
    original_count = len(records)
    records = [r for r in records if str(r.get("id", "")).strip() not in id_set]
    deleted = original_count - len(records)

    if deleted > 0:
        with open(CRAWL_RECORDS_CSV, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=RECORD_COLUMNS)
            writer.writeheader()
            writer.writerows(records)

    return deleted


def get_latest_success_crawl(tag: str) -> dict | None:
    """找 tag 下最近一次 status=success 的爬取记录"""
    _init_crawl_records_csv()
    if not os.path.exists(CRAWL_RECORDS_CSV):
        return _find_latest_crawl_from_data(tag)

    try:
        df = pd.read_csv(CRAWL_RECORDS_CSV, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    except Exception:
        return _find_latest_crawl_from_data(tag)

    df = df[df["tag"] == tag] if "tag" in df.columns else df[df.index == -1]
    df = df[df["status"] == "success"] if "status" in df.columns else df[df.index == -1]
    if df.empty:
        return _find_latest_crawl_from_data(tag)

    df["_sort"] = pd.to_datetime(df["end_time"], errors="coerce") if "end_time" in df.columns else pd.Series(dtype="datetime64[ns]")
    df = df.dropna(subset=["_sort"])
    df = df.sort_values("_sort", ascending=False)
    return df.iloc[0].to_dict()


def _find_latest_crawl_from_data(tag: str) -> dict | None:
    """从 data/ 目录扫描最新日期的 CSV"""
    data_dir = str(config.DATA_DIR)
    if not os.path.isdir(data_dir):
        return None

    date_dirs = _list_date_dirs(data_dir)
    if not date_dirs:
        return None

    for _, date_compact in reversed(date_dirs):
        csv_path = os.path.join(data_dir, date_compact, f"{tag}.csv")
        if os.path.exists(csv_path):
            try:
                df = pd.read_csv(csv_path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
            except Exception:
                continue
            if df.empty:
                continue
            crawl_date = f"{date_compact[:4]}-{date_compact[4:6]}-{date_compact[6:8]}"
            return {
                "id": "", "tag": tag,
                "crawl_date": crawl_date,
                "start_time": crawl_date + " 00:00:00",
                "end_time": crawl_date + " 00:00:00",
                "status": "success",
                "total_funds": str(len(df)),
                "ocr_success": "0",
                "error_message": "",
            }
    return None


def get_tag_summary(tag: str) -> dict:
    """统计：基金数量、最后成功爬取时间"""
    data_dir = str(config.DATA_DIR)
    if not os.path.isdir(data_dir):
        tag_name = next((t["name"] for t in config.FUND_TYPES if t["key"] == tag), tag)
        return {
            "tag": tag,
            "tag_name": tag_name,
            "total_funds": 0,
            "latest_crawl": None,
        }

    # 扫描最新日期 CSV 一次，复用于基金数量和爬取记录
    date_dirs = _list_date_dirs(data_dir)
    latest_csv_path = None
    latest_crawl_date = None

    for _, date_compact in date_dirs:
        csv_path = os.path.join(data_dir, date_compact, f"{tag}.csv")
        if os.path.exists(csv_path):
            latest_csv_path = csv_path
            latest_crawl_date = f"{date_compact[:4]}-{date_compact[4:6]}-{date_compact[6:8]}"
            break

    fund_count = 0
    if latest_csv_path:
        try:
            df = pd.read_csv(latest_csv_path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
            if not df.empty:
                fund_count = len(df)
        except Exception:
            pass

    latest_crawl = None
    if latest_crawl_date:
        latest_crawl = {
            "id": "",
            "tag": tag,
            "crawl_date": latest_crawl_date,
            "start_time": latest_crawl_date + " 00:00:00",
            "end_time": latest_crawl_date + " 00:00:00",
            "status": "success",
            "total_funds": str(fund_count),
            "ocr_success": "0",
            "error_message": "",
        }

    tag_name = next((t["name"] for t in config.FUND_TYPES if t["key"] == tag), tag)
    return {
        "tag": tag,
        "tag_name": tag_name,
        "total_funds": fund_count,
        "latest_crawl": latest_crawl,
    }


def _list_date_dirs(data_dir: str) -> list:
    """返回按日期降序排列的日期目录列表 [(datetime, name), ...]"""
    dirs = []
    try:
        for entry in os.scandir(data_dir):
            if not entry.is_dir():
                continue
            name = entry.name
            if len(name) == 8 and name.isdigit():
                try:
                    dt = datetime.strptime(name, "%Y%m%d")
                    dirs.append((dt, name))
                except ValueError:
                    pass
    except OSError:
        pass
    dirs.sort(key=lambda x: x[0], reverse=True)
    return dirs


# ===================== 基金数据读取（直接读 data/ 目录）=====================

def get_latest_fund_meta(
    tag: str,
    page: int = 1,
    per_page: int = 20,
    search: str = "",
    sort: str = "crawl_time",
    order: str = "desc",
) -> dict:
    """
    从 data/ 目录扫描所有日期的 {tag}.csv，对每个基金只保留最新爬取日期的记录。
    优先使用持久化索引文件加速查询。
    """
    # 使用索引加速
    index = _ensure_index(tag)
    funds_index = index.get("funds", {})

    latest_map: dict[str, dict] = {}
    # 已按日期降序排列的路径列表
    date_dirs = _list_date_dirs(str(config.DATA_DIR))

    # 建立 path -> 日期 的映射（用于按日期筛选）
    path_dates: dict[str, str] = {}
    for _, date_compact in date_dirs:
        csv_path = os.path.join(str(config.DATA_DIR), date_compact, f"{tag}.csv")
        path_dates[csv_path] = f"{date_compact[:4]}-{date_compact[4:6]}-{date_compact[6:8]}"

    # 按 csv_path 分组，避免重复读取同一文件
    csv_to_funds: dict[str, list[str]] = {}
    for fund_name, info in funds_index.items():
        csv_path = info.get("csv_path", "")
        if not csv_path:
            continue
        if csv_path not in csv_to_funds:
            csv_to_funds[csv_path] = []
        csv_to_funds[csv_path].append(fund_name)

    # 按路径批量处理
    for csv_path, fund_names in csv_to_funds.items():
        if not os.path.exists(csv_path):
            continue
        try:
            df = pd.read_csv(csv_path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
            name_col = _find_name_col(df)
            if not name_col:
                continue
            crawl_date_fmt = path_dates.get(csv_path, "")

            for fund_name in fund_names:
                matched = df[df[name_col].astype(str).str.strip() == fund_name]
                if matched.empty:
                    continue
                record = matched.iloc[0].to_dict()
                record["基金名称"] = fund_name
                record["爬取日期"] = crawl_date_fmt
                latest_map[fund_name] = record
        except Exception:
            continue

    all_meta = list(latest_map.values())

    if search:
        s = search.lower()
        all_meta = [m for m in all_meta if s in m.get("基金名称", "").lower()]

    sort_col_map = {
        "crawl_time": "爬取日期",
        "fund_name": "基金名称",
        "crawl_date": "爬取日期",
    }
    sort_col = sort_col_map.get(sort, "爬取日期")
    reverse = order == "desc"
    all_meta.sort(key=lambda m: m.get(sort_col, ""), reverse=reverse)

    total = len(all_meta)
    pages = max(1, (total + per_page - 1) // per_page)
    start = (page - 1) * per_page
    end = start + per_page
    items = all_meta[start:end]

    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
        "tag": tag,
    }


def get_all_fund_meta(
    tag: str,
    page: int = 1,
    per_page: int = 20,
    search: str = "",
    sort: str = "crawl_time",
    order: str = "desc",
    crawl_date: str = "",
) -> dict:
    """
    从 data/ 读取指定日期的 {tag}.csv（未指定 crawl_date 时取最新日期）。
    搜索/排序/分页在 Python 层实现。
    """
    data_dir = str(config.DATA_DIR)
    date_dirs = _list_date_dirs(data_dir)

    # 确定读取哪个 CSV
    target_csv = None
    if crawl_date:
        # 精确匹配：YYYY-MM-DD -> YYYYMMDD
        compact = crawl_date.replace("-", "")
        csv_path = os.path.join(data_dir, compact, f"{tag}.csv")
        if os.path.exists(csv_path):
            target_csv = csv_path
    else:
        # 默认取最新日期
        for _, date_compact in date_dirs:
            csv_path = os.path.join(data_dir, date_compact, f"{tag}.csv")
            if os.path.exists(csv_path):
                target_csv = csv_path
                break

    all_meta = []
    if target_csv:
        try:
            df = pd.read_csv(target_csv, dtype=str, keep_default_na=False, encoding="utf-8-sig")
            name_col = _find_name_col(df)
            if name_col:
                crawl_date_fmt = target_csv.split(os.sep)[-2]
                crawl_date_fmt = f"{crawl_date_fmt[:4]}-{crawl_date_fmt[4:6]}-{crawl_date_fmt[6:8]}"
                for _, row in df.iterrows():
                    fund_name = str(row.get(name_col, "")).strip()
                    if not fund_name:
                        continue
                    record = row.to_dict()
                    record["基金名称"] = fund_name
                    record["爬取日期"] = crawl_date_fmt
                    all_meta.append(record)
        except Exception:
            pass

    # 搜索
    if search:
        s = search.lower()
        all_meta = [m for m in all_meta if s in m.get("基金名称", "").lower()]

    # 排序
    sort_col_map = {
        "crawl_time": "爬取日期",
        "fund_name": "基金名称",
        "crawl_date": "爬取日期",
    }
    sort_col = sort_col_map.get(sort, "爬取日期")
    reverse = order == "desc"
    all_meta.sort(key=lambda m: m.get(sort_col, ""), reverse=reverse)

    # 分页
    total = len(all_meta)
    pages = max(1, (total + per_page - 1) // per_page)
    start = (page - 1) * per_page
    end = start + per_page
    items = all_meta[start:end]

    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
        "tag": tag,
        "crawl_date": crawl_date,
    }


def get_fund_meta_history(tag: str, fund_name: str, page: int = 1, per_page: int = 20) -> dict:
    """
    从所有 data/YYYYMMDD/{tag}.csv 扫描该基金的历史记录。
    """
    data_dir = str(config.DATA_DIR)
    date_dirs = _list_date_dirs(data_dir)

    all_rows = []
    for _, date_compact in date_dirs:
        csv_path = os.path.join(data_dir, date_compact, f"{tag}.csv")
        if not os.path.exists(csv_path):
            continue
        try:
            df = pd.read_csv(csv_path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
        except Exception:
            continue
        if df.empty:
            continue

        name_col = _find_name_col(df)
        if name_col is None:
            continue

        matched = df[df[name_col].astype(str).str.strip() == fund_name]
        if matched.empty:
            matched = df[df[name_col].astype(str).str.contains(
                fund_name.replace("\\", "\\\\"), regex=True, na=False
            )]
        if matched.empty:
            continue

        crawl_date = f"{date_compact[:4]}-{date_compact[4:6]}-{date_compact[6:8]}"
        for _, row in matched.iterrows():
            record = row.to_dict()
            record["爬取日期"] = crawl_date
            record["爬取时间"] = crawl_date + " 00:00:00"
            all_rows.append(record)

    # 按爬取日期降序
    all_rows.sort(key=lambda r: r.get("爬取日期", ""), reverse=True)

    total = len(all_rows)
    pages = max(1, (total + per_page - 1) // per_page)
    start = (page - 1) * per_page
    end = start + per_page
    records = all_rows[start:end]

    return {
        "records": records,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
        "tag": tag,
        "fund_name": fund_name,
    }


def _find_name_col(df: pd.DataFrame) -> str | None:
    """查找基金名称列"""
    for col in ["基金名称", "fund_name", "名称"]:
        if col in df.columns:
            return col
    return None


# ===================== 日期范围 =====================

def _correct_fund_date_boundary(df, date_str: str) -> str:
    """
    将外部日期映射到基金净值数据中存在的最近日期。

    若 date_str 恰好在 df 中有对应记录则直接返回；
    否则找小于 date_str 的最近净值日期；
    若没有更早的日期则返回 None。
    """
    import numpy as np
    from datetime import datetime as _dt

    if not date_str:
        return None
    try:
        target = _dt.strptime(date_str, "%Y-%m-%d")
    except (ValueError, TypeError):
        return None

    mask_eq = df["_sort_date"] == target
    if mask_eq.any():
        return date_str

    mask_lt = df["_sort_date"] < target
    pos = np.where(mask_lt.values)[0]
    if len(pos) > 0:
        return df["净值日期"].iloc[pos[-1]]
    return None


def get_data_date_range(tag: str) -> dict:
    """
    扫描 data/ 目录，返回指定 tag 的可用日期范围。
    """
    data_dir = str(config.DATA_DIR)
    if not os.path.isdir(data_dir):
        return {"min_date": None, "max_date": None, "available_dates": []}

    date_dirs = _list_date_dirs(data_dir)
    available_dates = []

    for _, date_compact in date_dirs:
        csv_path = os.path.join(data_dir, date_compact, f"{tag}.csv")
        if os.path.exists(csv_path):
            try:
                df = pd.read_csv(csv_path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
                if not df.empty:
                    available_dates.append(
                        f"{date_compact[:4]}-{date_compact[4:6]}-{date_compact[6:8]}"
                    )
            except Exception:
                pass

    if not available_dates:
        return {"min_date": None, "max_date": None, "available_dates": []}

    available_dates.sort()
    return {
        "min_date": available_dates[0],
        "max_date": available_dates[-1],
        "available_dates": available_dates,
    }
