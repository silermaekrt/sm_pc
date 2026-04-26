// main.js - 私募基金监控平台前端逻辑

// ==================== 全局变量 ====================
let currentPage = 1;
let searchTimeout = null;
let pollingInterval = null;
let isPollingActive = true;         // 轮询总开关
let isCrawlRunning = false;         // 爬虫是否运行中

// 轮询间隔配置（毫秒）
const POLL_INTERVALS = {
    IDLE: 3000,        // 空闲时：3秒
    RUNNING: 10000,     // 爬取中：10秒
    COMPLETE: 500,      // 刚完成：0.5秒快速刷新
};

// ==================== 初始化 ====================
function init() {
    loadStats();
    loadFunds(1);
    loadDateFilter();
    startStatusPolling();
}

// ==================== 统计信息 ====================
function loadStats() {
    fetch('/api/stats/summary')
        .then(r => r.json())
        .then(data => {
            // 基金总数
            document.getElementById('totalFunds').textContent = data.total_funds || 0;

            // 今日爬取
            if (data.today_crawl) {
                const todayStatus = data.today_crawl.status === 'success' ? '✓ 成功' : data.today_crawl.status;
                document.getElementById('todayCrawl').textContent = todayStatus;
            } else {
                document.getElementById('todayCrawl').textContent = '未爬取';
            }

            // 最近爬取
            if (data.latest_crawl) {
                const time = data.latest_crawl.start_time || '';
                const date = time.substring(0, 10) || '';
                const hour = time.substring(11, 16) || '';
                document.getElementById('lastCrawl').textContent = `${date} ${hour}`;
            } else {
                document.getElementById('lastCrawl').textContent = '-';
            }

            // 总爬取次数
            document.getElementById('totalCrawls').textContent = data.total_crawls || 0;
        })
        .catch(err => console.error('加载统计信息失败:', err));
}

// ==================== 基金列表 ====================
function loadFunds(page = 1) {
    currentPage = page;

    const search = document.getElementById('searchInput').value;
    const dateFilter = document.getElementById('dateFilter').value;
    const sortSelect = document.getElementById('sortSelect').value;
    const [sort, order] = sortSelect.split('-');

    const params = new URLSearchParams({
        page: page,
        per_page: 20,
        sort: sort,
        order: order
    });

    if (search) params.append('search', search);
    if (dateFilter) params.append('crawl_date', dateFilter);

    // 显示加载状态
    document.getElementById('fundTableBody').innerHTML = `
        <tr>
            <td colspan="11" class="loading-cell">
                <div class="loading"></div>
            </td>
        </tr>
    `;

    fetch(`/api/funds?${params.toString()}`)
        .then(r => r.json())
        .then(data => {
            renderFundsTable(data.items);
            renderPagination(data.page, data.pages);
            document.getElementById('recordCount').textContent = `共 ${data.total} 条记录`;
        })
        .catch(err => {
            console.error('加载基金列表失败:', err);
            document.getElementById('fundTableBody').innerHTML = `
                <tr>
                    <td colspan="11" class="empty-cell">加载失败，请重试</td>
                </tr>
            `;
        });
}

function renderFundsTable(funds) {
    const tbody = document.getElementById('fundTableBody');

    if (funds.length === 0) {
        tbody.innerHTML = '<tr><td colspan="11" class="empty-cell">暂无数据，请先触发抓取</td></tr>';
        return;
    }

    tbody.innerHTML = funds.map(f => {
        // 解析收益率数值，用于着色
        const thisYearClass = getReturnClass(f.this_year);
        const oneYearClass = getReturnClass(f.one_year);
        const threeYearClass = getReturnClass(f.three_year);
        const drawdownClass = getDrawdownClass(f.drawdown);

        return `
            <tr>
                <td><strong>${escapeHtml(f.fund_name)}</strong></td>
                <td>${f.fund_code || '-'}</td>
                <td>${f.strategy || '-'}</td>
                <td>${f.net_value_date || '-'}</td>
                <td><strong>${f.net_value || '-'}</strong></td>
                <td class="${thisYearClass}">${f.this_year || '-'}</td>
                <td class="${oneYearClass}">${f.one_year || '-'}</td>
                <td class="${threeYearClass}">${f.three_year || '-'}</td>
                <td>${f.since_inception || '-'}</td>
                <td class="${drawdownClass}">${f.drawdown || '-'}</td>
                <td>
                    <button class="btn btn-small btn-secondary" onclick="showFundDetail('${encodeURIComponent(f.fund_name)}')">
                        详情
                    </button>
                </td>
            </tr>
        `;
    }).join('');
}

// ==================== 分页 ====================
function renderPagination(current, total) {
    const container = document.getElementById('pagination');

    if (total <= 1) {
        container.innerHTML = '';
        return;
    }

    let html = '';

    // 上一页
    if (current > 1) {
        html += `<button onclick="loadFunds(${current - 1})">&laquo;</button>`;
    }

    // 页码
    const maxVisible = 5;
    let start = Math.max(1, current - Math.floor(maxVisible / 2));
    let end = Math.min(total, start + maxVisible - 1);

    if (end - start + 1 < maxVisible) {
        start = Math.max(1, end - maxVisible + 1);
    }

    if (start > 1) {
        html += `<button onclick="loadFunds(1)">1</button>`;
        if (start > 2) {
            html += `<button disabled>...</button>`;
        }
    }

    for (let i = start; i <= end; i++) {
        html += `<button class="${i === current ? 'active' : ''}" onclick="loadFunds(${i})">${i}</button>`;
    }

    if (end < total) {
        if (end < total - 1) {
            html += `<button disabled>...</button>`;
        }
        html += `<button onclick="loadFunds(${total})">${total}</button>`;
    }

    // 下一页
    if (current < total) {
        html += `<button onclick="loadFunds(${current + 1})">&raquo;</button>`;
    }

    container.innerHTML = html;
}

// ==================== 日期筛选 ====================
function loadDateFilter() {
    fetch('/api/crawl/records?per_page=30')
        .then(r => r.json())
        .then(data => {
            const select = document.getElementById('dateFilter');
            const dates = [...new Set(data.items.map(r => r.crawl_date))];

            select.innerHTML = '<option value="">全部日期</option>';
            dates.forEach(date => {
                select.innerHTML += `<option value="${date}">${date}</option>`;
            });
        })
        .catch(err => console.error('加载日期筛选失败:', err));
}

// ==================== 搜索 ====================
function debounceSearch() {
    if (searchTimeout) {
        clearTimeout(searchTimeout);
    }
    searchTimeout = setTimeout(() => {
        loadFunds(1);
    }, 300);
}

// ==================== 抓取控制 ====================
function triggerCrawl() {
    const btn = document.getElementById('triggerCrawlBtn');
    btn.disabled = true;
    btn.textContent = '抓取中...';

    fetch('/api/crawl/trigger', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ use_ocr: true })
    })
    .then(r => r.json())
    .then(data => {
        updateCrawlStatus('running', '抓取任务已启动');
        // 切换到爬取中模式：降低轮询频率
        switchPollingMode('running');
        alert(data.message);
    })
    .catch(err => {
        console.error('触发抓取失败:', err);
        alert('触发失败，请检查服务器状态');
        btn.disabled = false;
        btn.textContent = '触发抓取';
    });
}

/**
 * 切换轮询模式
 * @param {string} mode - 'idle' | 'running' | 'complete'
 */
function switchPollingMode(mode) {
    const intervals = POLL_INTERVALS;
    let newInterval;

    switch (mode) {
        case 'running':
            isCrawlRunning = true;
            newInterval = intervals.RUNNING;
            break;
        case 'complete':
            newInterval = intervals.COMPLETE;
            break;
        case 'idle':
        default:
            isCrawlRunning = false;
            newInterval = intervals.IDLE;
            break;
    }

    // 重启轮询定时器
    restartPolling(newInterval);
}

/**
 * 重启轮询定时器
 * @param {number} interval - 新的轮询间隔（毫秒）
 */
function restartPolling(interval) {
    if (pollingInterval) {
        clearInterval(pollingInterval);
    }

    pollingInterval = setInterval(() => {
        fetch('/api/crawl/status')
            .then(r => r.json())
            .then(data => {
                const wasRunning = isCrawlRunning;
                const isRunning = data.is_running;

                updateCrawlStatus(isRunning ? 'running' : 'success');

                // 状态从运行中变为完成
                if (wasRunning && !isRunning) {
                    // 切换到快速刷新模式
                    switchPollingMode('complete');

                    // 2秒后切换回正常模式
                    setTimeout(() => {
                        switchPollingMode('idle');
                        loadStats();
                        loadFunds(currentPage);
                    }, 2000);
                }

                // 如果爬虫未运行且当前不是空闲模式，更新数据
                if (!isRunning && !isCrawlRunning) {
                    // 已在 idle 模式，无需额外操作
                }
            })
            .catch(err => console.error('获取状态失败:', err));
    }, interval);
}

function startStatusPolling() {
    // 初始启动轮询
    switchPollingMode('idle');
}

function updateCrawlStatus(status, text) {
    const indicator = document.getElementById('crawlStatus');
    const btn = document.getElementById('triggerCrawlBtn');

    indicator.className = 'status-indicator ' + status;

    if (status === 'running') {
        indicator.querySelector('.status-text').textContent = '抓取中...';
        btn.disabled = true;
        btn.textContent = '抓取中...';
    } else {
        indicator.querySelector('.status-text').textContent = '空闲';
        btn.disabled = false;
        btn.textContent = '触发抓取';
    }
}

// ==================== 基金详情 ====================
function showFundDetail(fundName) {
    fundName = decodeURIComponent(fundName);

    fetch(`/api/fund/${encodeURIComponent(fundName)}`)
        .then(r => r.json())
        .then(data => {
            if (data.error) {
                alert(data.error);
                return;
            }

            document.getElementById('modalFundName').textContent = data.fund_name;

            const body = document.getElementById('modalBody');
            if (data.records.length === 0) {
                body.innerHTML = '<p class="empty-cell">暂无历史数据</p>';
            } else {
                const latest = data.records[0];
                const historyHtml = data.records.slice(0, 10).map((r, i) => `
                    <tr style="${i === 0 ? 'background:#e8f4fd' : ''}">
                        <td>${r.crawl_time ? r.crawl_time.substring(0, 19) : '-'}</td>
                        <td><strong>${r.net_value || '-'}</strong></td>
                        <td>${r.this_year || '-'}</td>
                        <td>${r.one_year || '-'}</td>
                        <td>${r.three_year || '-'}</td>
                        <td>${r.drawdown || '-'}</td>
                    </tr>
                `).join('');

                body.innerHTML = `
                    <h4 style="margin-bottom:12px;">最新数据</h4>
                    <table class="detail-table" style="margin-bottom:20px;">
                        <tr><th>净值日期</th><td>${latest.net_value_date || '-'}</td></tr>
                        <tr><th>基金代码</th><td>${latest.fund_code || '-'}</td></tr>
                        <tr><th>策略</th><td>${latest.strategy || '-'}</td></tr>
                        <tr><th>净值变动</th><td>${latest.net_change || '-'}</td></tr>
                        <tr><th>成立来年化</th><td>${latest.annual_return || '-'}</td></tr>
                        <tr><th>近一月</th><td>${latest.one_month || '-'}</td></tr>
                        <tr><th>近三月</th><td>${latest.three_month || '-'}</td></tr>
                        <tr><th>近半年</th><td>${latest.six_month || '-'}</td></tr>
                        <tr><th>近两年</th><td>${latest.two_year || '-'}</td></tr>
                        <tr><th>近五年</th><td>${latest.five_year || '-'}</td></tr>
                        <tr><th>本周</th><td>${latest.this_week || '-'}</td></tr>
                        <tr><th>上周</th><td>${latest.last_week || '-'}</td></tr>
                    </table>

                    <h4 style="margin-bottom:12px;">历史净值记录（最近10条）</h4>
                    <table class="data-table">
                        <thead>
                            <tr>
                                <th>爬取时间</th>
                                <th>最新净值</th>
                                <th>今年来</th>
                                <th>近一年</th>
                                <th>近三年</th>
                                <th>回撤</th>
                            </tr>
                        </thead>
                        <tbody>${historyHtml}</tbody>
                    </table>
                `;
            }

            document.getElementById('fundDetailModal').classList.add('show');
        })
        .catch(err => {
            console.error('加载详情失败:', err);
            alert('加载失败，请重试');
        });
}

function closeModal() {
    document.getElementById('fundDetailModal').classList.remove('show');
}

// ==================== 导出功能 ====================
function toggleExportMenu() {
    const menu = document.getElementById('exportMenu');
    menu.style.display = menu.style.display === 'none' ? 'block' : 'none';
}

// 点击外部关闭导出菜单
document.addEventListener('click', function(e) {
    const dropdown = document.querySelector('.export-dropdown');
    if (dropdown && !dropdown.contains(e.target)) {
        const menu = document.getElementById('exportMenu');
        if (menu) menu.style.display = 'none';
    }
});

function exportData(format) {
    document.getElementById('exportMenu').style.display = 'none';

    const dateFilter = document.getElementById('dateFilter').value;
    const search = document.getElementById('searchInput').value;
    const params = new URLSearchParams({ format: format });
    if (dateFilter) params.set('crawl_date', dateFilter);
    if (search) params.set('search', search);

    const url = `/api/export?${params.toString()}`;
    window.location.href = url;
}

// ==================== 登录设置 ====================
function showLoginModal() {
    const modal = document.getElementById('loginModal');
    modal.classList.add('show');
    loadCredentialStatus();
}

function closeLoginModal() {
    document.getElementById('loginModal').classList.remove('show');
}

function loadCredentialStatus() {
    fetch('/api/auth/credentials')
        .then(r => r.json())
        .then(data => {
            const statusEl = document.getElementById('loginStatus');
            const credEl = document.getElementById('credentialStatus');

            if (!data.has_credentials) {
                statusEl.innerHTML = '<span class="hint-info">尚未保存登录凭证</span>';
                credEl.innerHTML = '';
                return;
            }

            // 填充表单
            document.getElementById('loginUsername').value = data.username || '';
            document.getElementById('loginInterval').value = data.refresh_interval || 60;

            // 显示状态
            let statusHtml = '<span class="hint-success">✓ 凭证已保存</span>';
            if (data.last_refresh) {
                statusHtml += ` &nbsp;上次刷新: ${data.last_refresh.substring(0, 16)}`;
            }
            if (data.last_error) {
                statusHtml += `<br><span class="hint-error">上次错误: ${data.last_error}</span>`;
            }
            statusEl.innerHTML = statusHtml;
        })
        .catch(err => {
            document.getElementById('loginStatus').innerHTML =
                '<span class="hint-error">加载状态失败</span>';
        });
}

function submitLogin(event) {
    event.preventDefault();

    const username = document.getElementById('loginUsername').value.trim();
    const password = document.getElementById('loginPassword').value;
    const refreshInterval = parseInt(document.getElementById('loginInterval').value) || 60;

    const statusEl = document.getElementById('loginStatus');
    statusEl.innerHTML = '<span class="hint-info">保存中...</span>';

    fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password, refresh_interval: refreshInterval })
    })
    .then(r => r.json())
    .then(data => {
        if (data.error) {
            statusEl.innerHTML = `<span class="hint-error">${data.error}</span>`;
        } else {
            statusEl.innerHTML = '<span class="hint-success">✓ ' + data.message + '</span>';
            setTimeout(() => {
                closeLoginModal();
                loadStats();
            }, 1500);
        }
    })
    .catch(err => {
        statusEl.innerHTML = '<span class="hint-error">请求失败，请重试</span>';
    });
}

function manualRefreshCookies() {
    const statusEl = document.getElementById('loginStatus');
    statusEl.innerHTML = '<span class="hint-info">正在刷新 Cookie...</span>';

    fetch('/api/auth/refresh', { method: 'POST' })
        .then(r => r.json())
        .then(data => {
            if (data.error) {
                statusEl.innerHTML = `<span class="hint-error">${data.error}</span>`;
            } else {
                statusEl.innerHTML = '<span class="hint-success">✓ ' + data.message + '</span>';
                setTimeout(() => loadCredentialStatus(), 2000);
            }
        })
        .catch(() => {
            statusEl.innerHTML = '<span class="hint-error">请求失败</span>';
        });
}

// 点击弹窗背景关闭基金详情弹窗
document.addEventListener('click', function(e) {
    const fundModal = document.getElementById('fundDetailModal');
    const loginModal = document.getElementById('loginModal');
    if (e.target === fundModal) {
        closeModal();
    }
    if (e.target === loginModal) {
        closeLoginModal();
    }
});

// ESC 键关闭弹窗
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        closeModal();
    }
});

// ==================== 工具函数 ====================

// HTML 转义
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// 收益率样式
function getReturnClass(value) {
    if (!value) return '';
    const num = parseFloat(value.replace('%', ''));
    if (isNaN(num)) return '';
    if (num > 0) return 'positive';
    if (num < 0) return 'negative';
    return '';
}

// 回撤样式（回撤越小越好，负数且绝对值越大越不好）
function getDrawdownClass(value) {
    if (!value) return '';
    const num = parseFloat(value.replace('%', ''));
    if (isNaN(num)) return '';
    if (num > 20) return 'negative';  // 回撤超过20%标记
    if (num > 30) return 'negative';
    return '';
}
