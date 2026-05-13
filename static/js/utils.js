/**
 * static/js/utils.js - 前端公共工具函数
 * 提供分页、菜单等可复用组件
 */

// ==================== 分页组件 ====================

/**
 * 渲染分页控件（支持省略号和首页/末页）
 * @param {string} containerId - 分页容器元素ID
 * @param {number} current - 当前页码
 * @param {number} total - 总页数
 * @param {function} onPageChange - 页码变更回调，接收新页码参数
 */
function renderPagination(containerId, current, total, onPageChange) {
    const container = document.getElementById(containerId);
    if (!container || total <= 1) {
        if (container) container.innerHTML = '';
        return;
    }

    let html = '';
    if (current > 1) {
        html += `<button onclick="${onPageChange}(${current - 1})">&laquo;</button>`;
    }

    const maxVisible = 5;
    let start = Math.max(1, current - Math.floor(maxVisible / 2));
    let end = Math.min(total, start + maxVisible - 1);
    if (end - start + 1 < maxVisible) {
        start = Math.max(1, end - maxVisible + 1);
    }

    if (start > 1) {
        html += `<button onclick="${onPageChange}(1)">1</button>`;
        if (start > 2) html += `<button disabled>...</button>`;
    }

    for (let i = start; i <= end; i++) {
        html += `<button class="${i === current ? 'active' : ''}" onclick="${onPageChange}(${i})">${i}</button>`;
    }

    if (end < total) {
        if (end < total - 1) html += `<button disabled>...</button>`;
        html += `<button onclick="${onPageChange}(${total})">${total}</button>`;
    }

    if (current < total) {
        html += `<button onclick="${onPageChange}(${current + 1})">&raquo;</button>`;
    }

    container.innerHTML = html;
}

// ==================== 下拉菜单 ====================

/**
 * 切换下拉菜单显示/隐藏
 * @param {string} menuId - 菜单元素ID
 */
function toggleDropdown(menuId) {
    const menu = document.getElementById(menuId);
    if (menu) {
        menu.style.display = menu.style.display === 'none' ? 'block' : 'none';
    }
}

// ==================== 通用表格工具 ====================

/**
 * 通用表格行渲染（用于展示对象数据）
 * @param {object} data - 行数据对象
 * @param {Array} columns - 列配置 [{key, label, formatter?, className?}]
 * @returns {string} HTML tr 字符串
 */
function renderTableRow(data, columns) {
    return columns.map(col => {
        let value = data[col.key];
        if (col.formatter && typeof col.formatter === 'function') {
            value = col.formatter(value, data);
        }
        const className = col.className ? ` class="${col.className}"` : '';
        return `<td${className}>${value !== undefined && value !== null ? value : '-'}</td>`;
    }).join('');
}
