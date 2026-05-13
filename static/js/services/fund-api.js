/**
 * static/js/services/fund-api.js - 基金 API 封装
 * 
 * 统一封装所有基金相关的 API 调用。
 */

const FundAPI = {
    /**
     * 获取基金列表
     */
    async getFunds(params = {}) {
        const { tag = 'private', page = 1, per_page = 20, search = '', sort = 'crawl_time', order = 'desc' } = params;
        const query = new URLSearchParams({ tag, page, per_page, sort, order });
        if (search) query.set('name', search);
        
        const res = await fetch(`/api/funds?${query}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
    },
    
    /**
     * 获取最新基金列表
     */
    async getLatestFunds(params = {}) {
        const { tag = 'private', page = 1, per_page = 20, search = '', sort = 'crawl_time', order = 'desc' } = params;
        const query = new URLSearchParams({ tag, page, per_page, sort, order });
        if (search) query.set('name', search);
        
        const res = await fetch(`/api/funds/latest?${query}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
    },
    
    /**
     * 获取基金详情
     */
    async getFundDetail(tag, fundName, page = 1, perPage = 20) {
        const query = new URLSearchParams({ tag, page, per_page: perPage });
        const encodedName = encodeURIComponent(fundName);
        const res = await fetch(`/api/fund/${encodedName}?${query}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
    },
    
    /**
     * 获取可用日期范围
     */
    async getFundDates(tag, fundName = '') {
        const query = new URLSearchParams({ tag });
        if (fundName) query.set('fund_name', fundName);
        
        const res = await fetch(`/api/funds/dates?${query}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
    },
    
    /**
     * 获取全局最早日期
     */
    async getGlobalMinDate() {
        const res = await fetch('/api/funds/global-min-date');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
    },
    
    /**
     * 获取累计净值基金列表
     */
    async getCumulativeFundList() {
        const res = await fetch('/api/funds/cumulative-list');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
    },
    
    /**
     * 获取基准指数列表
     */
    async getBenchmarks() {
        const res = await fetch('/api/funds/benchmarks');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
    },
    
    /**
     * 获取基金时序数据
     */
    async getTimeseries(params = {}) {
        const { tag = 'private', fund_name, start = '', end = '', benchmark = '' } = params;
        const query = new URLSearchParams({ tag, fund_name, start, end });
        if (benchmark) query.set('benchmark', benchmark);
        
        const res = await fetch(`/api/funds/timeseries?${query}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
    },
    
    /**
     * 获取风险指标
     */
    async getRiskMetrics(params = {}) {
        const { tag = 'private', fund_name, start = '', end = '', rf = 0.03, benchmark = '' } = params;
        const query = new URLSearchParams({ tag, fund_name, start, end, rf });
        if (benchmark) query.set('benchmark', benchmark);
        
        const res = await fetch(`/api/funds/risk-metrics?${query}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
    },
    
    /**
     * 获取统计摘要
     */
    async getStatsSummary(tag = '') {
        const query = tag ? new URLSearchParams({ tag }) : '';
        const res = await fetch(`/api/stats/summary${query ? '?' + query : ''}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
    },
    
    /**
     * 健康检查
     */
    async healthCheck() {
        const res = await fetch('/api/health');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
    }
};


// ==================== 导出 ====================

window.FundAPI = FundAPI;
