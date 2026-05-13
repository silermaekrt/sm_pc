/**
 * static/js/services/crawl-api.js - 爬取 API 封装
 * 
 * 统一封装所有爬取相关的 API 调用。
 */

const CrawlAPI = {
    /**
     * 获取标签列表
     */
    async getTags() {
        const res = await fetch('/api/crawl/tags');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
    },
    
    /**
     * 触发爬取
     */
    async triggerCrawl(tags, sync = false) {
        const res = await fetch('/api/crawl', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ tags, sync })
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
    },
    
    /**
     * 获取爬取状态
     */
    async getStatus() {
        const res = await fetch('/api/crawl/status');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
    },
    
    /**
     * 获取爬取记录
     */
    async getRecords(tag = '', page = 1, perPage = 10) {
        const query = new URLSearchParams({ page, per_page: perPage });
        if (tag) query.set('tag', tag);
        
        const res = await fetch(`/api/crawl/records?${query}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
    },
    
    /**
     * 删除爬取记录
     */
    async deleteRecords(ids) {
        const res = await fetch('/api/crawl/records', {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ids })
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
    },
    
    /**
     * 单基金爬取
     */
    async crawlFund(params = {}) {
        const { tag = 'private', fund_name } = params;
        const query = new URLSearchParams({ tag, fund_name });
        
        const res = await fetch(`/api/crawl/fund?${query}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({})
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
    }
};


// ==================== 导出 ====================

window.CrawlAPI = CrawlAPI;
