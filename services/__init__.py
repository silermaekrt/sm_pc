# -*- coding: utf-8 -*-
"""
services/__init__.py - 服务包
"""

from services.csv_store import (
    get_all_fund_meta,
    get_fund_meta_history,
    get_data_date_range,
    get_latest_fund_meta,
    invalidate_index,
)
from services.data_service import (
    DataService,
    COLUMN_NAME_MAP,
    compute_daily_returns,
    CrawlRecordContext,
    get_crawl_records,
    delete_crawl_records,
    get_tag_summary,
    save_crawl_record,
)
from services.metrics import (
    compute_risk_metrics,
    compute_max_drawdown_from_prices,
    compute_excess_drawdown_from_series,
    align_benchmark_by_date,
)
from services.period_stats import (
    BENCHMARK_CODE_MAP,
    read_base_quote,
    compute_benchmark_interval_return,
    compute_benchmark_drawdown,
)
