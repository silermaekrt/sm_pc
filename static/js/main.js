// main.js - 私募基金监控平台前端逻辑

let latestTag = '';
let latestSearchTimeout = null;
let latestCurrentPage = 1;
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
            latestTag = data.tags[0].key;
            renderTabs('latestTagTabs', latestTag);
            loadDateFilterForSection();
            loadLatestFunds(1);
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
    latestTag = btn.dataset.tag;
    renderTabs('latestTagTabs', latestTag);
    loadDateFilterForSection();
    loadLatestFunds(1);
}

function loadDateFilterForSection() {
    fetch(`/api/funds/dates?tag=${latestTag}`)
        .then(r => r.json())
        .then(data => {
            document.getElementById('latestDateFilter').innerHTML =
                '<option value="">全部日期</option>' +
                data.available_dates.reverse().map(d => `<option value="${d}">${d}</option>`).join('');
        })
        .catch(err => console.error('加载日期筛选失败:', err));
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

    fetch(`/api/funds/latest?${params}`)
        .then(r => r.json())
        .then(data => {
            renderLatestTable(data.items);
            renderPagination('latestPagination', data.page, data.pages, 'loadLatestFunds');
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
        tbody.innerHTML = '<tr><td colspan="19" class="empty-cell">暂无数据</td></tr>';
        return;
    }
    tbody.innerHTML = funds.map(f =>
        `<tr>
            <td><strong>${escapeHtml(f.基金名称 || f.fund_name)}</strong></td>
            <td>${f.基金代码 || '-'}</td>
            <td>${f.策略 || '-'}</td>
            <td>${f.净值日期 || '-'}</td>
            <td><strong>${f.最新净值 || '-'}</strong></td>
            <td>${f.净值变动 || '-'}</td>
            <td>${f.成立来年化 || '-'}</td>
            <td class="${getReturnClass(f['今年来'])}">${f['今年来'] || '-'}</td>
            <td>${f['上周'] || '-'}</td>
            <td>${f['近一月'] || '-'}</td>
            <td>${f['近三月'] || '-'}</td>
            <td>${f['近半年'] || '-'}</td>
            <td class="${getReturnClass(f['近一年'])}">${f['近一年'] || '-'}</td>
            <td>${f['近两年'] || '-'}</td>
            <td class="${getReturnClass(f['近三年'])}">${f['近三年'] || '-'}</td>
            <td>${f['近五年'] || '-'}</td>
            <td>${f['成立来'] || '-'}</td>
            <td>${f['本周'] || '-'}</td>
            <td class="${getDrawdownClass(f['回撤'])}">${f['回撤'] || '-'}</td>
        </tr>`
    ).join('');
}

// ==================== 导出功能 ====================
function exportLatestData(format) {
    const menu = document.getElementById('latestExportMenu');
    if (menu) menu.style.display = 'none';
    const dateFilter = document.getElementById('latestDateFilter').value;
    const search = document.getElementById('latestSearchInput').value;
    const params = new URLSearchParams({ format, tag: latestTag });
    if (dateFilter) params.set('date', dateFilter);
    if (search) params.set('name', search);
    window.location.href = `/api/export?${params}`;
}
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
    toggleDropdown('latestExportMenu');
}

function exportLatestData(format) {
    const menu = document.getElementById('latestExportMenu');
    if (menu) menu.style.display = 'none';
    const dateFilter = document.getElementById('latestDateFilter').value;
    const search = document.getElementById('latestSearchInput').value;
    const params = new URLSearchParams({ format, tag: latestTag });
    if (dateFilter) params.set('date', dateFilter);
    if (search) params.set('name', search);
    window.location.href = `/api/export?${params}`;
}

document.addEventListener('click', e => {
    const latestDropdown = document.getElementById('latestExportDropdown');
    if (latestDropdown && !latestDropdown.contains(e.target))
        document.getElementById('latestExportMenu').style.display = 'none';
    if (e.target === document.getElementById('crawlModal')) closeCrawlModal();
});

document.addEventListener('keydown', e => {
    if (e.key === 'Escape') closeCrawlModal();
});

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
