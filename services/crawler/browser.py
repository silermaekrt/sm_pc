# -*- coding: utf-8 -*-
"""
services/crawler/browser.py - 浏览器会话管理

职责：Playwright 初始化、Cookie 设置、页面导航、元素提取
"""

import time

import config
from config import (
    USER_AGENT, VIEWPORT_WIDTH, VIEWPORT_HEIGHT,
    GOTO_TIMEOUT, SELECTOR_TIMEOUT,
    PAGE_WAIT_TIME, VIEWPORT_WAIT_TIME, TAB_SWITCH_WAIT_TIME,
    CRAWL, CROP_MARGIN,
)
from app_logging import get_logger
from exceptions import (
    BrowserError, PageLoadError, ElementNotFoundError,
    CookieError, TagNotFoundError, ScreenshotError,
)

logger = get_logger(__name__)


# ===================== Cookie 设置 =====================
def setup_cookies(context):
    """设置 Cookie，解析失败时仅警告，不中断流程"""
    raw_cookie = config.get_raw_cookie()
    if not raw_cookie:
        return 0  # 无 cookie，继续运行

    success_count = 0
    failed_cookies = []

    for item in raw_cookie.split(";"):
        item = item.strip()
        if not item or "=" not in item:
            continue
        k, v = item.split("=", 1)
        k, v = k.strip(), v.strip()
        if not k:
            continue
        try:
            context.add_cookies(
                [{"name": k, "value": v, "domain": CRAWL.COOKIE_DOMAIN, "path": "/"}]
            )
            success_count += 1
        except Exception as e:
            failed_cookies.append(k)
            logger.debug(f"Cookie 设置失败 [{k}]: {e}")

    if failed_cookies:
        logger.warning(f"部分 Cookie 设置失败: {failed_cookies}")

    if success_count == 0 and raw_cookie:
        raise CookieError(
            "所有 Cookie 设置均失败，请检查 Cookie 格式", expired=True
        )

    logger.info(f"Cookie 设置完成（共 {success_count} 条）")
    return success_count


# ===================== 标签页切换 =====================
_TAG_KEYWORD_MAP = None

def _get_tag_keyword_map():
    global _TAG_KEYWORD_MAP
    if _TAG_KEYWORD_MAP is None:
        from config import get_fund_type_map
        _TAG_KEYWORD_MAP = get_fund_type_map()
    return _TAG_KEYWORD_MAP


def _switch_to_tag(page, tag: str) -> bool:
    """切换到指定标签页，返回 True 表示成功"""
    tag_keyword_map = _get_tag_keyword_map()
    tab_keyword = tag_keyword_map.get(tag, tag)
    try:
        page.evaluate(
            '''(kw) => {
                const tabs = document.querySelectorAll('.xs-nav-item');
                tabs.forEach(t => {
                    if(t.innerText.includes(kw)) t.click();
                });
            }''',
            tab_keyword
        )
        page.wait_for_selector(
            f'.xs-nav-item.is-active:text("({tab_keyword})"), .xs-nav-item.active:text("{tab_keyword}")',
            timeout=3000
        )
        page.wait_for_timeout(TAB_SWITCH_WAIT_TIME)
        return True
    except Exception:
        return False


def _ensure_tag_exists(page, tag: str) -> bool:
    """验证指定标签页是否存在"""
    tag_keyword_map = _get_tag_keyword_map()
    tab_keyword = tag_keyword_map.get(tag, tag)
    try:
        exists = page.evaluate(
            f'''() => {{
                return Array.from(document.querySelectorAll(".xs-nav-item"))
                    .some(el => el.innerText.includes("{tab_keyword}"));
            }}'''
        )
        return exists
    except Exception:
        return False


# ===================== 位置提取 =====================
def extract_fund_positions(page) -> list:
    """从页面提取所有基金行的位置信息"""
    positions = page.evaluate(
        """
() => {
    const rows = Array.from(document.querySelectorAll('tbody tr.el-table__row'));
    const visibleRows = rows.filter(row => {
        let el = row;
        for (let i=0; i<7; i++) el = el?.parentElement;
            if (!el) return false;
            if (el.offsetParent === null) return false;
            return true;
           });
    const positions = [];

    const headerCells = document.querySelectorAll('thead th');
    let netValueColIndex = -1;
    for (let i = 0; i < headerCells.length; i++) {
        const text = headerCells[i].innerText.trim();
        if (text === '最新净值') {
            netValueColIndex = i;
            break;
        }
    }

    for (const row of visibleRows) {
        const cells = row.querySelectorAll('td');
        if (cells.length < 2) continue;

        const nameCell = cells[1];
        const fundName = nameCell ? (nameCell.querySelector('a')?.title || nameCell.innerText.split('\\n')[0].trim()) : '';
        if (!fundName) continue;

        const nameRect = nameCell.getBoundingClientRect();
        const rowRect = row.getBoundingClientRect();

        let netValueImg = null;
        if (netValueColIndex >= 0 && cells[netValueColIndex]) {
            const netValueCell = cells[netValueColIndex];

            const imgs = netValueCell.querySelectorAll('img');
            for (const img of imgs) {
                const rect = img.getBoundingClientRect();
                if (rect.width > 30 && rect.width < 150 && rect.height > 8 && rect.height < 35) {
                    netValueImg = { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
                    break;
                }
            }

            if (!netValueImg) {
                const allElements = netValueCell.querySelectorAll('*');
                for (const el of allElements) {
                    if (el.tagName === 'IMG') {
                        const rect = el.getBoundingClientRect();
                        if (rect.width > 30 && rect.width < 150 && rect.height > 8 && rect.height < 35) {
                            netValueImg = { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
                            break;
                        }
                    }
                }
            }

            if (!netValueImg) {
                const rect = netValueCell.getBoundingClientRect();
                if (rect.width > 30 && rect.height > 20) {
                    netValueImg = { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
                }
            }
        }

        positions.push({
            fundName,
            nameX: nameRect.x,
            nameY: nameRect.y,
            nameWidth: nameRect.width,
            nameHeight: nameRect.height,
            rowY: rowRect.y,
            rowHeight: rowRect.height,
            netValueImg,
            netValueColIndex
        });
    }

    return positions;
}
"""
    )
    return positions


# ===================== 表格信息 =====================
def get_table_info(page) -> dict | None:
    """获取可见表格区域信息，无可见表格则返回 None"""
    info = page.evaluate(
        """
() => {
    const allTables = document.querySelectorAll('.el-table__body-wrapper');
    for (const table of allTables) {
        let parent = table;
        let isHidden = false;
        for (let i = 0; i < 5; i++) {
            if (!parent) break;
            const style = parent.style.display || '';
            if (style === 'none') {
                isHidden = true;
                break;
            }
            parent = parent.parentElement;
        }
        if (!isHidden) {
            const rect = table.getBoundingClientRect();
            return { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
        }
    }
    return null;
}
"""
    )
    if info is None or info.get("width", 0) <= 0 or info.get("height", 0) <= 0:
        return None
    return info


# ===================== 文本数据提取 =====================
def extract_text_data(page) -> list:
    """从页面提取所有可见行的文本数据"""
    rows_data = page.evaluate(
        """
() => {
    const rows = [];
    const allRows = document.querySelectorAll('tbody tr.el-table__row');

    for (const row of allRows) {
        let el = row;
        let hidden = false;
        for (let i = 0; i < 8; i++) {
            if (!el) break;
            el = el.parentElement;
        }
        if (el && el.style.display === 'none') {
            hidden = true;
        }
        if (!hidden && !(row.getAttribute('style') || '').includes('display: none')) {
            rows.push(row);
        }
    }

    return rows.map(row => {
        const cells = Array.from(row.querySelectorAll('td'));
        return cells.map(cell => cell.innerText.trim());
    }).filter(cells => cells.length >= 18);
}
"""
    )
    return rows_data


# ===================== 页面导航 =====================
def navigate_and_wait(page, tag: str = "private") -> dict:
    """
    跳转到目标页面，切换标签，等待表格加载，提取位置/表格信息/文本数据。

    返回 dict:
      - has_data: bool
      - tag: str
      - fund_positions: list
      - table_info: dict | None
      - rows_data: list
    """
    from config import SIMU_URL as _SIMU_URL

    try:
        page.goto(_SIMU_URL, wait_until=CRAWL.PAGE_LOAD_WAIT, timeout=GOTO_TIMEOUT)
    except Exception as e:
        raise PageLoadError(f"页面加载失败: {e}", url=_SIMU_URL, timeout=GOTO_TIMEOUT)

    page.set_viewport_size(
        {"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT}
    )

    try:
        page.wait_for_selector(CRAWL.TABLE_ROW_SELECTOR, timeout=SELECTOR_TIMEOUT)
    except Exception:
        raise ElementNotFoundError(
            "表格行未找到，可能页面结构变化或数据为空",
            selector=CRAWL.TABLE_ROW_SELECTOR,
        )

    page.wait_for_timeout(VIEWPORT_WAIT_TIME)

    from config import get_fund_type_lists as _get_tag_list
    _tag_key_list = _get_tag_list()[0]

    if tag != "private":
        if not _ensure_tag_exists(page, tag):
            raise TagNotFoundError(tag=tag, available_tags=_tag_key_list)
        if not _switch_to_tag(page, tag):
            raise TagNotFoundError(tag=tag, available_tags=_tag_key_list)
        try:
            page.wait_for_selector(
                f"{CRAWL.TABLE_ROW_SELECTOR}:visible",
                timeout=SELECTOR_TIMEOUT,
            )
            page.wait_for_timeout(PAGE_WAIT_TIME)
        except Exception:
            pass

    fund_positions = extract_fund_positions(page)
    table_info = get_table_info(page)
    rows_data = extract_text_data(page)

    return {
        "has_data": True,
        "tag": tag,
        "fund_positions": fund_positions,
        "table_info": table_info,
        "rows_data": rows_data,
    }


# ===================== 基准指数提取 =====================
def extract_benchmark_index(page) -> str:
    """
    从基金详情页提取基准指数名称（如"沪深300"）。
    返回纯文本，失败返回空字符串。

    HTML 结构：
    <div class="dropdown-modify">
      <span class="el-tooltip__trigger">沪深300<svg>▼</svg></span>
    </div>
    策略：找到 dropdown-modify 下的 el-tooltip__trigger，取其直接文本（排除 svg 子元素）。
    """
    import re

    # 方法1：用 Playwright locator + 直接文本提取
    try:
        loc = page.locator(config.BENCHMARK_SELECTOR).first
        text = loc.inner_text(timeout=5000)
        # innerText 包含 svg 等子元素的文本，需要过滤掉 ▼ 等字符
        text = re.sub(r"[\s▼\(\)]", "", text).strip()
        if text:
            return text
    except Exception:
        pass

    # 方法2兜底：直接在 DOM 里找包含"沪深"、"中证"等关键词的元素
    try:
        raw = page.evaluate(
            """
            () => {
                const triggers = document.querySelectorAll('.el-tooltip__trigger');
                for (const el of triggers) {
                    const clone = el.cloneNode(true);
                    const svgs = clone.querySelectorAll('svg');
                    svgs.forEach(s => s.remove());
                    const t = clone.innerText.trim();
                    if (t) return t;
                }
                return '';
            }
            """
        )
        if raw:
            return re.sub(r"[\s▼\(\)]", "", raw).strip()
    except Exception:
        pass

    return ""


# ===================== 截图 =====================
def capture_table_screenshot(page, table_info: dict | None, date_str: str = "", tag: str = "") -> str:
    """截取表格区域并保存，返回截图路径。table_info 为 None 时跳过。"""
    if table_info is None:
        return ""

    clip_x = max(0, table_info["x"] - CROP_MARGIN)
    clip_y = max(0, table_info["y"] - CROP_MARGIN)
    clip_w = table_info["width"] + CROP_MARGIN * 2
    clip_h = table_info["height"] + CROP_MARGIN * 2

    import os
    if date_str:
        tag_dir = os.path.join(config.SCREENSHOT_DIR, date_str, tag)
    else:
        tag_dir = config.SCREENSHOT_DIR
    os.makedirs(tag_dir, exist_ok=True)

    try:
        screenshot_bytes = page.screenshot(
            type="png",
            clip={"x": clip_x, "y": clip_y, "width": clip_w, "height": clip_h},
        )
        screenshot_path = os.path.join(tag_dir, "table_full_screenshot.png")
        with open(screenshot_path, "wb") as f:
            f.write(screenshot_bytes)
        return screenshot_path
    except Exception as e:
        raise ScreenshotError(f"截图保存失败: {e}")


def capture_table_screenshot_bytes(page, table_info: dict | None) -> bytes | None:
    """截取表格区域，返回 bytes（用于内存中 OCR）。table_info 为 None 时返回 None。"""
    if table_info is None:
        return None

    clip_x = max(0, table_info["x"] - CROP_MARGIN)
    clip_y = max(0, table_info["y"] - CROP_MARGIN)
    clip_w = table_info["width"] + CROP_MARGIN * 2
    clip_h = table_info["height"] + CROP_MARGIN * 2

    try:
        return page.screenshot(
            type="png",
            clip={"x": clip_x, "y": clip_y, "width": clip_w, "height": clip_h},
        )
    except Exception as e:
        raise ScreenshotError(f"截图失败: {e}")
