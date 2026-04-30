// main.js - 私募基金监控平台前端逻辑

let latestTag = '';
let fundListTag = '';
let latestSearchTimeout = null;
let latestCurrentPage = 1;
let fundSearchTimeout = null;
let fundCurrentPage = 1;
let pollingInterval = null;
let isCrawlRunning = false;
let allTags = [];

const POLL_INTERVALS = { IDLE: 3000, RUNNING: 10000, COMPLETE: 500 };

function init() {
    fetch('/api/crawl/tags')
        .then(r => r.json())
        .then(data => {
            if (!data.tags || !data.tags.length) return;
            allTags = data.tags;
            latestTag = fundListTag = data.tags[0].key;
            renderTabs('latestTagTabs', latestTag);
            renderTabs('fundListTagTabs', fundListTag);
            loadDateFilterForBothSections();
            loadLatestFunds(1);
            loadFunds(1);
            startStatusPolling();
        })
        .catch(err => console.error('加载标签失败:', err));
}

function renderTabs(containerId, activeTag) {
    document.getElementById(containerId).innerHTML = allTags.map(t =>
        `<button class="tag-tab ${t.key === activeTag ? 'active' : ''}"
            data-tag="${t.key}" onclick="onSectionTagChange(this)">${t.name}</button>`
    ).join('');
}

function onSectionTagChange(btn) {
    const containerId = btn.parentElement.id;
    const tagKey = btn.dataset.tag;
    if (containerId === 'latestTagTabs') {
        latestTag = tagKey;
        loadLatestFunds(1);
        loadDateFilterForSection('latest');
        renderTabs('latestTagTabs', latestTag);
    } else {
        fundListTag = tagKey;
        loadFunds(1);
        loadDateFilterForSection('fundList');
        renderTabs('fundListTagTabs', fundListTag);
    }
}

function loadDateFilterForBothSections() {
    loadDateFilterForSection('latest');
    loadDateFilterForSection('fundList');
}

function loadDateFilterForSection(section) {
    const tag = section === 'latest' ? latestTag : fundListTag;
    const targetId = section === 'latest' ? 'latestDateFilter' : 'dateFilter';
    fetch(`/api/crawl/records?per_page=30&tag=${tag}`)
        .then(r => r.json())
        .then(data => {
            const dates = [...new Set(data.items.map(r => r.crawl_date))];
            document.getElementById(targetId).innerHTML =
                '<option value="">全部日期</option>' + dates.map(d => `<option value="${d}">${d}</option>`).join('');
        })
        .catch(err => console.error('加载日期筛选失败:', err));
}

function onCardToggleChange() {
    document.getElementById('latestDataCard').style.display =
        document.getElementById('showLatestCard').checked ? 'block' : 'none';
    document.getElementById('fundListCard').style.display =
        document.getElementById('showFundListCard').checked ? 'block' : 'none';
}

// ==================== 最新数据 ====================
function debounceLatestSearch() {
    clearTimeout(latestSearchTimeout);
    latestSearchTimeout = setTimeout(latestSearch, 300);
}

function latestSearch() {
    latestCurrentPage = 1;
    loadLatestFunds(1);
}

function loadLatestFunds(page = 1) {
    latestCurrentPage = page;
    const search = document.getElementById('latestSearchInput').value.trim();
    const dateFilter = document.getElementById('latestDateFilter').value;
    const [sort, order] = document.getElementById('latestSortSelect').value.split('-');
    const params = new URLSearchParams({ page, per_page: 20, tag: latestTag, sort, order });
    if (search) params.append('name', search);
    if (dateFilter) params.append('crawl_date', dateFilter);

    document.getElementById('latestTableBody').innerHTML =
        '<tr><td colspan="20" class="loading-cell"><div class="loading"></div></td></tr>';

    fetch(`/api/funds?${params}`)
        .then(r => r.json())
        .then(data => {
            renderLatestTable(data.items);
            renderLatestPagination(data.page, data.pages);
            document.getElementById('latestCount').textContent = `共 ${data.total} 条`;
        })
        .catch(() => {
            document.getElementById('latestTableBody').innerHTML =
                '<tr><td colspan="20" class="empty-cell">加载失败</td></tr>';
        });
}

function renderLatestTable(funds) {
    const tbody = document.getElementById('latestTableBody');
    if (!funds.length) {
        tbody.innerHTML = '<tr><td colspan="20" class="empty-cell">暂无数据</td></tr>';
        return;
    }
    tbody.innerHTML = funds.map(f =>
        `<tr>
            <td><strong>${escapeHtml(f.fund_name)}</strong></td>
            <td>${f.fund_code || '-'}</td>
            <td>${f.strategy || '-'}</td>
            <td>${f.net_value_date || '-'}</td>
            <td><strong>${f.net_value || '-'}</strong></td>
            <td>${f.net_change || '-'}</td>
            <td>${f.annual_return || '-'}</td>
            <td class="${getReturnClass(f.this_year)}">${f.this_year || '-'}</td>
            <td>${f.last_week || '-'}</td>
            <td>${f.one_month || '-'}</td>
            <td>${f.three_month || '-'}</td>
            <td>${f.six_month || '-'}</td>
            <td class="${getReturnClass(f.one_year)}">${f.one_year || '-'}</td>
            <td>${f.two_year || '-'}</td>
            <td class="${getReturnClass(f.three_year)}">${f.three_year || '-'}</td>
            <td>${f.five_year || '-'}</td>
            <td>${f.since_inception || '-'}</td>
            <td>${f.this_week || '-'}</td>
            <td class="${getDrawdownClass(f.drawdown)}">${f.drawdown || '-'}</td>
            <td>${f.crawl_time ? f.crawl_time.substring(0, 16) : '-'}</td>
        </tr>`
    ).join('');
}

function renderLatestPagination(current, total) {
    const container = document.getElementById('latestPagination');
    if (total <= 1) { container.innerHTML = ''; return; }
    let html = '';
    if (current > 1) html += `<button onclick="loadLatestFunds(${current - 1})">&laquo;</button>`;
    const maxVisible = 5;
    let start = Math.max(1, current - Math.floor(maxVisible / 2));
    let end = Math.min(total, start + maxVisible - 1);
    if (end - start + 1 < maxVisible) start = Math.max(1, end - maxVisible + 1);
    if (start > 1) {
        html += `<button onclick="loadLatestFunds(1)">1</button>`;
        if (start > 2) html += `<button disabled>...</button>`;
    }
    for (let i = start; i <= end; i++)
        html += `<button class="${i === current ? 'active' : ''}" onclick="loadLatestFunds(${i})">${i}</button>`;
    if (end < total) {
        if (end < total - 1) html += `<button disabled>...</button>`;
        html += `<button onclick="loadLatestFunds(${total})">${total}</button>`;
    }
    if (current < total) html += `<button onclick="loadLatestFunds(${current + 1})">&raquo;</button>`;
    container.innerHTML = html;
}

// ==================== 基金列表 ====================
function debounceFundSearch() {
    clearTimeout(fundSearchTimeout);
    fundSearchTimeout = setTimeout(fundSearch, 300);
}

function fundSearch() {
    fundCurrentPage = 1;
    loadFunds(1);
}

function loadFunds(page = 1) {
    fundCurrentPage = page;
    const search = document.getElementById('fundSearchInput').value.trim();
    const dateFilter = document.getElementById('dateFilter').value;
    const [sort, order] = document.getElementById('sortSelect').value.split('-');
    const params = new URLSearchParams({ page, per_page: 20, tag: fundListTag, sort, order });
    if (search) params.append('name', search);
    if (dateFilter) params.append('crawl_date', dateFilter);

    document.getElementById('fundTableBody').innerHTML =
        '<tr><td colspan="20" class="loading-cell"><div class="loading"></div></td></tr>';

    fetch(`/api/funds?${params}`)
        .then(r => r.json())
        .then(data => {
            renderFundsTable(data.items);
            renderPagination(data.page, data.pages);
            document.getElementById('recordCount').textContent = `共 ${data.total} 条记录`;
        })
        .catch(() => {
            document.getElementById('fundTableBody').innerHTML =
                '<tr><td colspan="20" class="empty-cell">加载失败</td></tr>';
        });
}

function renderFundsTable(funds) {
    const tbody = document.getElementById('fundTableBody');
    if (!funds.length) {
        tbody.innerHTML = '<tr><td colspan="20" class="empty-cell">暂无数据</td></tr>';
        return;
    }
    tbody.innerHTML = funds.map(f =>
        `<tr>
            <td><strong>${escapeHtml(f.fund_name)}</strong></td>
            <td>${f.fund_code || '-'}</td>
            <td>${f.strategy || '-'}</td>
            <td>${f.net_value_date || '-'}</td>
            <td><strong>${f.net_value || '-'}</strong></td>
            <td>${f.net_change || '-'}</td>
            <td>${f.annual_return || '-'}</td>
            <td class="${getReturnClass(f.this_year)}">${f.this_year || '-'}</td>
            <td>${f.last_week || '-'}</td>
            <td>${f.one_month || '-'}</td>
            <td>${f.three_month || '-'}</td>
            <td>${f.six_month || '-'}</td>
            <td class="${getReturnClass(f.one_year)}">${f.one_year || '-'}</td>
            <td>${f.two_year || '-'}</td>
            <td class="${getReturnClass(f.three_year)}">${f.three_year || '-'}</td>
            <td>${f.five_year || '-'}</td>
            <td>${f.since_inception || '-'}</td>
            <td>${f.this_week || '-'}</td>
            <td class="${getDrawdownClass(f.drawdown)}">${f.drawdown || '-'}</td>
            <td>${f.crawl_time ? f.crawl_time.substring(0, 16) : '-'}</td>
        </tr>`
    ).join('');
}

function renderPagination(current, total) {
    const container = document.getElementById('pagination');
    if (total <= 1) { container.innerHTML = ''; return; }
    let html = '';
    if (current > 1) html += `<button onclick="loadFunds(${current - 1})">&laquo;</button>`;
    const maxVisible = 5;
    let start = Math.max(1, current - Math.floor(maxVisible / 2));
    let end = Math.min(total, start + maxVisible - 1);
    if (end - start + 1 < maxVisible) start = Math.max(1, end - maxVisible + 1);
    if (start > 1) {
        html += `<button onclick="loadFunds(1)">1</button>`;
        if (start > 2) html += `<button disabled>...</button>`;
    }
    for (let i = start; i <= end; i++)
        html += `<button class="${i === current ? 'active' : ''}" onclick="loadFunds(${i})">${i}</button>`;
    if (end < total) {
        if (end < total - 1) html += `<button disabled>...</button>`;
        html += `<button onclick="loadFunds(${total})">${total}</button>`;
    }
    if (current < total) html += `<button onclick="loadFunds(${current + 1})">&raquo;</button>`;
    container.innerHTML = html;
}

// ==================== 抓取控制 ====================
function showCrawlModal() {
    const group = document.getElementById('crawlTagsGroup');
    if (group.children.length > 0) {
        document.getElementById('crawlModal').classList.add('show');
        return;
    }
    fetch('/api/crawl/tags')
        .then(r => r.json())
        .then(data => {
            group.innerHTML = data.tags.map(t =>
                `<label><input type="checkbox" class="crawl-tag-checkbox" value="${t.key}"> ${t.name}</label>`
            ).join('');
            const cb = group.querySelector(`input[value="${latestTag}"]`);
            if (cb) cb.checked = true;
            document.getElementById('crawlModal').classList.add('show');
        })
        .catch(() => alert('加载标签失败，请重试'));
}

function closeCrawlModal() {
    document.getElementById('crawlModal').classList.remove('show');
}

function submitCrawl() {
    const tags = [...document.querySelectorAll('.crawl-tag-checkbox:checked')].map(cb => cb.value);
    if (!tags.length) { alert('请至少选择一个标签'); return; }
    closeCrawlModal();
    updateCrawlStatus('running');
    switchPollingMode('running');
    fetch('/api/crawl', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tags, sync: false })
    })
        .then(r => r.json())
        .then(data => alert(data.message))
        .catch(() => { alert('触发失败，请检查服务器状态'); updateCrawlStatus('idle'); });
}

function switchPollingMode(mode) {
    let interval;
    if (mode === 'running') { isCrawlRunning = true; interval = POLL_INTERVALS.RUNNING; }
    else if (mode === 'complete') { interval = POLL_INTERVALS.COMPLETE; }
    else { isCrawlRunning = false; interval = POLL_INTERVALS.IDLE; }
    restartPolling(interval);
}

function restartPolling(interval) {
    if (pollingInterval) clearInterval(pollingInterval);
    pollingInterval = setInterval(() => {
        fetch('/api/crawl/status')
            .then(r => r.json())
            .then(data => {
                const wasRunning = isCrawlRunning;
                const isRunning = data.is_running;
                updateCrawlStatus(isRunning ? 'running' : 'success');
                if (wasRunning && !isRunning) {
                    switchPollingMode('complete');
                    setTimeout(() => {
                        switchPollingMode('idle');
                        loadLatestFunds(latestCurrentPage);
                        loadFunds(fundCurrentPage);
                    }, 2000);
                }
            })
            .catch(err => console.error('获取状态失败:', err));
    }, interval);
}

function startStatusPolling() {
    switchPollingMode('idle');
}

function updateCrawlStatus(status) {
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

// ==================== 导出功能 ====================
function toggleLatestExportMenu() {
    const menu = document.getElementById('latestExportMenu');
    menu.style.display = menu.style.display === 'none' ? 'block' : 'none';
    document.getElementById('fundListExportMenu').style.display = 'none';
}

function toggleFundListExportMenu() {
    const menu = document.getElementById('fundListExportMenu');
    menu.style.display = menu.style.display === 'none' ? 'block' : 'none';
    document.getElementById('latestExportMenu').style.display = 'none';
}

function exportLatestData(format) {
    document.getElementById('latestExportMenu').style.display = 'none';
    const dateFilter = document.getElementById('latestDateFilter').value;
    const search = document.getElementById('latestSearchInput').value;
    const params = new URLSearchParams({ format, tag: latestTag });
    if (dateFilter) params.set('date', dateFilter);
    if (search) params.set('name', search);
    window.location.href = `/api/export?${params}`;
}

function exportFundListData(format) {
    document.getElementById('fundListExportMenu').style.display = 'none';
    const dateFilter = document.getElementById('dateFilter').value;
    const search = document.getElementById('fundSearchInput').value;
    const params = new URLSearchParams({ format, tag: fundListTag });
    if (dateFilter) params.set('date', dateFilter);
    if (search) params.set('name', search);
    window.location.href = `/api/export?${params}`;
}

document.addEventListener('click', e => {
    const latestDropdown = document.getElementById('latestExportDropdown');
    const fundListDropdown = document.getElementById('fundListExportDropdown');
    if (latestDropdown && !latestDropdown.contains(e.target))
        document.getElementById('latestExportMenu').style.display = 'none';
    if (fundListDropdown && !fundListDropdown.contains(e.target))
        document.getElementById('fundListExportMenu').style.display = 'none';
    if (e.target === document.getElementById('loginModal')) closeLoginModal();
    if (e.target === document.getElementById('crawlModal')) closeCrawlModal();
});

document.addEventListener('keydown', e => {
    if (e.key === 'Escape') { closeLoginModal(); closeCrawlModal(); }
});

// ==================== 登录设置 ====================
function showLoginModal() {
    document.getElementById('loginModal').classList.add('show');
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
            document.getElementById('loginUsername').value = data.username || '';
            document.getElementById('loginInterval').value = data.refresh_interval || 60;
            let html = '<span class="hint-success">✓ 凭证已保存</span>';
            if (data.last_refresh) html += ` &nbsp;上次刷新: ${data.last_refresh.substring(0, 16)}`;
            if (data.last_error) html += `<br><span class="hint-error">上次错误: ${data.last_error}</span>`;
            statusEl.innerHTML = html;
        })
        .catch(() => {
            document.getElementById('loginStatus').innerHTML = '<span class="hint-error">加载状态失败</span>';
        });
}

function submitLogin(event) {
    event.preventDefault();
    const statusEl = document.getElementById('loginStatus');
    statusEl.innerHTML = '<span class="hint-info">保存中...</span>';
    fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            username: document.getElementById('loginUsername').value.trim(),
            password: document.getElementById('loginPassword').value,
            refresh_interval: parseInt(document.getElementById('loginInterval').value) || 60
        })
    })
        .then(r => r.json())
        .then(data => {
            if (data.error) statusEl.innerHTML = `<span class="hint-error">${data.error}</span>`;
            else {
                statusEl.innerHTML = '<span class="hint-success">✓ ' + data.message + '</span>';
                setTimeout(closeLoginModal, 1500);
            }
        })
        .catch(() => statusEl.innerHTML = '<span class="hint-error">请求失败，请重试</span>');
}

function manualRefreshCookies() {
    const statusEl = document.getElementById('loginStatus');
    statusEl.innerHTML = '<span class="hint-info">正在刷新 Cookie...</span>';
    fetch('/api/auth/refresh', { method: 'POST' })
        .then(r => r.json())
        .then(data => {
            if (data.error) statusEl.innerHTML = `<span class="hint-error">${data.error}</span>`;
            else {
                statusEl.innerHTML = '<span class="hint-success">✓ ' + data.message + '</span>';
                setTimeout(loadCredentialStatus, 2000);
            }
        })
        .catch(() => statusEl.innerHTML = '<span class="hint-error">请求失败</span>');
}

// ==================== 工具函数 ====================
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function getReturnClass(value) {
    if (!value) return '';
    const num = parseFloat(value.replace('%', ''));
    if (isNaN(num) || num <= 0) return '';
    return 'positive';
}

function getDrawdownClass(value) {
    if (!value) return '';
    const num = parseFloat(value.replace('%', ''));
    if (isNaN(num) || num <= 20) return '';
    return 'negative';
}
