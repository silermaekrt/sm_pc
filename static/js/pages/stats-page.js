/**
 * static/js/pages/stats-page.js - 统计分析页逻辑
 * 
 * 封装统计页的所有交互逻辑，提供模块化的页面控制器。
 */

class StatsPage {
    constructor(options = {}) {
        this.options = {
            navChartContainer: 'navChart',
            drawdownChartContainer: 'drawdownAnalysisChart',
            ...options
        };
        
        // 状态
        this.navChart = null;
        this.drawdownChart = null;
        this.statsTag = '';
        this.allStatsTags = [];
        this.analysisTag = '';
        this.currentProcessedData = null;
        this.currentRecordsPage = 1;
        this.chartWarningTimeout = null;
    }
    
    /**
     * 初始化页面
     */
    async init() {
        await Promise.all([
            this.loadStatsTags(),
            this.loadBenchmarkList()
        ]);
    }
    
    // ==================== 初始化 ====================
    
    async loadStatsTags() {
        const data = await CrawlAPI.getTags();
        if (!data.tags || data.tags.length === 0) return;
        
        this.statsTag = data.tags[0].key;
        this.analysisTag = data.tags[0].key;
        this.allStatsTags = data.tags;
        
        this.renderStatsTabs(data.tags);
        this.renderAnalysisTagSelect(data.tags);
        
        // 加载日期范围
        try {
            const dateData = await FundAPI.getFundDates(this.analysisTag);
            this.initDatesFromRange(dateData);
            this.applyGlobalMinDate();
        } catch (e) {
            this.initDefaultDates();
        }
        
        this.loadCrawlRecords(1);
        this.initAnalysisCharts();
        this.loadFundsForTag(this.analysisTag);
    }
    
    loadBenchmarkList() {
        return FundAPI.getBenchmarks().then(data => {
            const benchmarks = data.benchmarks || [];
            const select = document.getElementById('benchmarkSelect');
            select.innerHTML = '<option value="">-- 默认（基金配置）--</option>';
            benchmarks.forEach(b => {
                const opt = document.createElement('option');
                opt.value = b.name;
                opt.textContent = b.name;
                select.appendChild(opt);
            });
        }).catch(() => {});
    }
    
    // ==================== 标签相关 ====================
    
    renderStatsTabs(tags) {
        this.allStatsTags = tags;
        const container = document.getElementById('statsTagTabs');
        container.innerHTML = tags.map(t =>
            `<button class="tag-tab ${t.key === this.statsTag ? 'active' : ''}"
                data-tag="${t.key}"
                onclick="statsPage.onStatsTagChange(this)">${t.name}</button>`
        ).join('');
    }
    
    onStatsTagChange(btn) {
        this.statsTag = btn.dataset.tag;
        this.renderStatsTabs(this.allStatsTags);
        
        FundAPI.getFundDates(this.statsTag)
            .then(dateData => this.initDatesFromRange(dateData))
            .catch(() => this.initDefaultDates());
        this.applyGlobalMinDate();
        this.loadCrawlRecords(1);
    }
    
    renderAnalysisTagSelect(tags) {
        const sel = document.getElementById('analysisTagSelect');
        sel.innerHTML = tags.map(t =>
            `<option value="${t.key}" ${t.key === this.analysisTag ? 'selected' : ''}>${t.name}</option>`
        ).join('');
    }
    
    onAnalysisTagChange() {
        this.analysisTag = document.getElementById('analysisTagSelect').value;
        this.loadFundsForTag(this.analysisTag);
        FundAPI.getFundDates(this.analysisTag)
            .then(dateData => this.initDatesFromRange(dateData))
            .catch(() => this.initDefaultDates());
    }
    
    // ==================== 日期相关 ====================
    
    initDefaultDates() {
        const today = new Date();
        const twoMonthsAgo = new Date(today);
        twoMonthsAgo.setMonth(today.getMonth() - 2);
        const fmt = d => d.toISOString().slice(0, 10);
        this.setAnalysisDateRange(fmt(twoMonthsAgo), fmt(today));
    }
    
    setAnalysisDateRange(start, end) {
        document.getElementById('analysisStartDate').value = start;
        document.getElementById('analysisEndDate').value = end;
    }
    
    initDatesFromRange(dateData) {
        const today = new Date();
        const fmt = d => d.toISOString().slice(0, 10);
        let end = fmt(today);
        if (dateData.max_date) {
            end = dateData.max_date;
        }
        let start = fmt(new Date(today.getTime() - 2 * 30 * 86400000));
        if (dateData.min_date) {
            const minDate = new Date(dateData.min_date);
            const proposed = new Date(minDate);
            proposed.setMonth(proposed.getMonth() + 2);
            if (proposed <= today) {
                start = fmt(proposed);
            } else {
                start = fmt(today);
            }
        }
        this.setAnalysisDateRange(start, end);
        this.initDateConstraints();
    }
    
    initDateConstraints() {
        const today = new Date().toISOString().split('T')[0];
        const startEl = document.getElementById('analysisStartDate');
        const endEl = document.getElementById('analysisEndDate');
        startEl.max = today;
        endEl.max = today;
    }
    
    applyGlobalMinDate() {
        FundAPI.getGlobalMinDate().then(data => {
            if (!data.global_min_date) return;
            const ids = ['analysisStartDate', 'analysisEndDate'];
            ids.forEach(id => {
                const el = document.getElementById(id);
                if (el) el.min = data.global_min_date;
            });
        }).catch(() => {});
    }
    
    applyFundDateConstraints(tag, fundName) {
        const today = new Date().toISOString().split('T')[0];
        const startEl = document.getElementById('analysisStartDate');
        const endEl = document.getElementById('analysisEndDate');
        startEl.max = today;
        endEl.max = today;
        
        FundAPI.getFundDates(tag, fundName).then(data => {
            if (!data.min_date) return;
            if (!startEl.min || data.min_date > startEl.min) startEl.min = data.min_date;
            if (data.min_date > startEl.value) startEl.value = data.min_date;
        }).catch(() => {});
    }
    
    onAnalysisStartDateChange() {
        const startEl = document.getElementById('analysisStartDate');
        const endEl = document.getElementById('analysisEndDate');
        if (!startEl.value) return;
        const startVal = startEl.value;
        if (endEl.value && endEl.value < startVal) endEl.value = startVal;
        endEl.min = startVal;
    }
    
    // ==================== 图表初始化 ====================
    
    initAnalysisCharts() {
        this.navChart = echarts.init(document.getElementById(this.options.navChartContainer));
        this.drawdownChart = echarts.init(document.getElementById(this.options.drawdownChartContainer));
        
        const emptyOpt = {
            title: { 
                text: '请选择基金后点击"查询"', 
                left: 'center', 
                top: 'center',
                textStyle: { color: '#999', fontSize: 14, fontWeight: 'normal' } 
            },
            xAxis: { show: false }, 
            yAxis: { show: false }, 
            series: []
        };
        this.navChart.setOption(emptyOpt);
        this.drawdownChart.setOption(emptyOpt);
        
        window.addEventListener('resize', () => {
            this.navChart.resize();
            this.drawdownChart.resize();
        });
    }
    
    // ==================== 基金选择 ====================
    
    loadFundsForTag(tag) {
        const select = document.getElementById('fundSelect');
        select.innerHTML = '<option value="">加载中...</option>';
        
        FundAPI.getLatestFunds({ tag, per_page: 200 }).then(data => {
            if (!data.items || data.items.length === 0) {
                select.innerHTML = '<option value="">该标签下暂无基金</option>';
                this.showNoData('该标签下暂无基金数据');
                return;
            }
            select.innerHTML = '<option value="">-- 选择基金 --</option>' +
                data.items.map(f => `<option value="${f.基金名称 || f.fund_name}">${f.基金名称 || f.fund_name}</option>`).join('');
            const firstFund = data.items[0].基金名称 || data.items[0].fund_name;
            select.value = firstFund;
            this.applyFundDateConstraints(tag, firstFund);
        }).catch(err => {
            console.error('加载基金列表失败:', err);
            select.innerHTML = '<option value="">加载失败</option>';
            this.showNoData('加载基金列表失败');
        });
    }
    
    // ==================== 区间分析 ====================
    
    applyAnalysis() {
        const fundName = document.getElementById('fundSelect').value;
        if (!fundName) { alert('请先选择基金'); return; }
        const startDate = document.getElementById('analysisStartDate').value;
        const endDate = document.getElementById('analysisEndDate').value;
        if (!startDate || !endDate) { alert('请选择日期范围'); return; }
        if (startDate > endDate) { alert('开始日期不能晚于结束日期'); return; }
        
        const benchmark = document.getElementById('benchmarkSelect').value;
        this.loadTimeSeriesData(this.analysisTag, fundName, startDate, endDate, benchmark);
        this.loadRiskMetrics(this.analysisTag, fundName, startDate, endDate, benchmark);
    }
    
    loadTimeSeriesData(tag, fundName, startDate, endDate, benchmark) {
        this.setStatCardsLoading(true);
        document.getElementById('statCardBenchmark').textContent = '';
        
        this.navChart.showLoading('default', { text: '加载中...', color: '#4a90d9', textColor: '#999' });
        this.drawdownChart.showLoading('default', { text: '加载中...', color: '#4a90d9', textColor: '#999' });
        
        FundAPI.getTimeseries({ tag, fund_name: fundName, start: startDate, end: endDate, benchmark })
            .then(data => {
                if (data.error || !data.dates || data.dates.length === 0) {
                    this.showNoData(data.error || '该基金暂无历史净值数据');
                    this.setStatCardsLoading(false);
                    document.getElementById('statCardRange').textContent = '（日期区间错误）';
                    return;
                }
                
                const rangeEl = document.getElementById('statCardRange');
                if (data.date_corrected) {
                    rangeEl.innerHTML = `<span style="color:#e67e22;">实际：${data.corrected_start} ~ ${data.corrected_end}</span>　<span style="color:#999;font-size:11px;">（原始：${data.original_start} ~ ${data.original_end} 已修正）</span>`;
                } else {
                    rangeEl.textContent = `${data.corrected_start} ~ ${data.corrected_end}`;
                }
                
                const processed = this.processTimeSeriesData(data);
                this.currentProcessedData = processed;
                this.renderStatCards(processed);
                this.renderNavChart(processed);
                this.renderDrawdownAnalysisChart(processed);
                
                if (processed && processed.warning) {
                    this.showChartWarning(processed.warning);
                }
            })
            .catch(err => { this.showNoData('加载失败: ' + err.message); })
            .finally(() => {
                this.navChart.hideLoading();
                this.drawdownChart.hideLoading();
            });
    }
    
    loadRiskMetrics(tag, fundName, startDate, endDate, benchmark) {
        FundAPI.getRiskMetrics({ tag, fund_name: fundName, start: startDate, end: endDate, benchmark })
            .then(data => {
                console.log('[risk-metrics] response:', JSON.stringify(data));
                if (data.error) { this.setRiskCardsEmpty(); return; }
                this.renderRiskCards(data);
            })
            .catch(err => {
                console.error('[risk-metrics] fetch error:', err);
                this.setRiskCardsEmpty();
            });
    }
    
    // ==================== 数据处理 ====================
    
    computeDrawdownFromReturns(returns) {
        const dd = [];
        let peak = 0;
        let firstPeak = 0;
        for (const v of returns) {
            if (v !== null) {
                if (v >= firstPeak) {
                    firstPeak = v;
                    peak = v;
                }
                dd.push(v - peak);
            } else {
                dd.push(null);
            }
        }
        return dd;
    }
    
    processTimeSeriesData(data) {
        const n = data.dates.length;
        if (n === 0) return null;
        
        const fundNav = data.nav_values.map(v => parseFloat(v) || 0);
        const baseNav = fundNav[0] || 1;
        const navReturns = fundNav.map(v => ((v / baseNav) - 1) * 100);
        
        let benchReturns = null;
        if (data.benchmark_values && data.benchmark_values.length > 0) {
            const bv = data.benchmark_values.filter(v => v !== null).map(v => parseFloat(v) || 0);
            if (bv.length > 0) {
                const bb = data.benchmark_start_value ? parseFloat(data.benchmark_start_value) : bv[0];
                if (bb && bb !== 0) {
                    benchReturns = data.benchmark_values.map(v => {
                        if (v === null) return null;
                        return ((parseFloat(v) / bb) - 1) * 100;
                    });
                }
            }
        }
        
        let excess = null;
        if (benchReturns) {
            excess = navReturns.map((v, i) =>
                benchReturns[i] !== null ? v - benchReturns[i] : null
            );
        }
        
        let drawdown = null;
        if (data.fund_drawdown && data.fund_drawdown.length > 0) {
            drawdown = data.fund_drawdown;
        } else {
            drawdown = [];
            let peak = 0;
            let firstPeak = 0;
            for (const v of navReturns) {
                if (v >= firstPeak) {
                    firstPeak = v;
                    peak = v;
                }
                drawdown.push(v - peak);
            }
        }
        
        let benchDD = null;
        let excessDD = null;
        if (data.benchmark_drawdown && data.benchmark_drawdown.length > 0) {
            benchDD = data.benchmark_drawdown;
        } else if (benchReturns) {
            benchDD = this.computeDrawdownFromReturns(benchReturns);
        }
        
        if (data.excess_drawdown && data.excess_drawdown.length > 0) {
            excessDD = data.excess_drawdown;
        } else if (excess && benchDD) {
            excessDD = [];
            for (let i = 0; i < navReturns.length; i++) {
                const fd = drawdown[i];
                const bd = benchDD && benchDD[i] !== null ? benchDD[i] : null;
                excessDD.push((fd !== null && bd !== null) ? fd - bd : null);
            }
        }
        
        const fundReturn = navReturns[navReturns.length - 1];
        let benchReturn = null;
        if (benchReturns) {
            const bvFiltered = benchReturns.filter(v => v !== null);
            if (bvFiltered.length >= 2) {
                benchReturn = bvFiltered[bvFiltered.length - 1] - bvFiltered[0];
            }
        }
        const excessReturn = benchReturn !== null ? fundReturn - benchReturn : null;
        
        const maxDD = data.fund_max_drawdown !== null && data.fund_max_drawdown !== undefined
            ? data.fund_max_drawdown
            : Math.min(...drawdown);
        const maxBenchDD = data.benchmark_max_drawdown !== null && data.benchmark_max_drawdown !== undefined
            ? data.benchmark_max_drawdown
            : (benchDD ? Math.min(...benchDD.filter(v => v !== null)) : null);
        
        let maxExcessDD = null;
        if (excessDD && excessDD.length > 0) {
            const validExcessDD = excessDD.filter(v => v !== null);
            if (validExcessDD.length > 0) {
                maxExcessDD = Math.min(...validExcessDD);
            }
        } else if (maxDD !== null && maxBenchDD !== null) {
            maxExcessDD = maxDD - maxBenchDD;
        }
        
        const benchmarkAvailable = data.benchmark_available !== false && benchReturn !== null;
        
        return {
            dates: data.dates,
            navReturns,
            benchReturns,
            excess,
            drawdown,
            benchDD,
            excessDD,
            fundReturn,
            benchReturn,
            excessReturn,
            maxDD,
            maxBenchDD,
            maxExcessDD,
            benchmarkName: data.benchmark_name || '',
            benchmarkAvailable,
            warning: data.warning || null,
        };
    }
    
    // ==================== 卡片渲染 ====================
    
    renderStatCards(p) {
        this.setStatCardsLoading(false);
        if (!p) return;
        
        const benchmarkLabel = document.getElementById('statCardBenchmark');
        if (p.warning) {
            benchmarkLabel.innerHTML = `<span style="color:#e67e22;font-size:12px;">${p.warning}</span>`;
        } else {
            benchmarkLabel.textContent = p.benchmarkName;
        }
        
        const fmt = (val) => {
            if (val === null || val === undefined || !isFinite(val)) return { text: '--', cls: 'neutral' };
            const sign = val >= 0 ? '+' : '';
            return { text: sign + val.toFixed(2) + '%', cls: val >= 0 ? 'positive' : 'negative' };
        };
        
        this.setCard('cardFundReturn', fmt(p.fundReturn));
        this.setCard('cardBenchmarkReturn', p.benchmarkAvailable ? fmt(p.benchReturn) : { text: '--', cls: 'neutral' });
        this.setCard('cardExcessReturn', p.benchmarkAvailable ? fmt(p.excessReturn) : { text: '--', cls: 'neutral' });
        this.setCard('cardMaxDrawdown', fmt(p.maxDD));
        this.setCard('cardBenchmarkDrawdown', p.benchmarkAvailable ? fmt(p.maxBenchDD) : { text: '--', cls: 'neutral' });
        this.setCard('cardExcessDrawdown', p.benchmarkAvailable ? fmt(p.maxExcessDD) : { text: '--', cls: 'neutral' });
    }
    
    setCard(id, data) {
        const el = document.getElementById(id);
        el.textContent = data.text;
        el.className = 'stat-card-value ' + data.cls;
    }
    
    setStatCardsLoading(loading) {
        ['cardFundReturn','cardBenchmarkReturn','cardExcessReturn',
         'cardMaxDrawdown','cardBenchmarkDrawdown','cardExcessDrawdown'].forEach(id => {
            const el = document.getElementById(id);
            el.textContent = loading ? '...' : '--';
            el.className = 'stat-card-value' + (loading ? '' : ' neutral');
        });
    }
    
    setRiskCardsEmpty() {
        ['cardSharpe','cardSortino','cardCalmar','cardVolatility','cardAnnReturn'].forEach(id => {
            const el = document.getElementById(id);
            el.textContent = '--';
            el.className = 'stat-card-value neutral';
        });
    }
    
    renderRiskCards(data) {
        const fmt = (val, decimals = 2, suffix = '') => {
            if (val === null || val === undefined || !isFinite(val)) return { text: '--', cls: 'neutral' };
            const sign = val >= 0 ? '+' : '';
            return { text: sign + val.toFixed(decimals) + suffix, cls: val >= 0 ? 'positive' : 'negative' };
        };
        
        const fmtPct = (val, decimals = 2) => {
            if (val === null || val === undefined || !isFinite(val)) return { text: '--', cls: 'neutral' };
            return { text: val.toFixed(decimals) + '%', cls: val >= 0 ? 'positive' : 'negative' };
        };
        
        const sr = fmt(data.sharpe_ratio);
        const sor = { text: '待修正', cls: 'neutral' };
        const cr = fmt(data.calmar_ratio);
        const vol = fmtPct(data.annualized_vol);
        const ar = fmtPct(data.annualized_return);
        const bm = data.benchmark || {};
        const exDD = fmt(bm.excess_max_drawdown);
        
        this.setCard('cardSharpe', { text: sr.text, cls: sr.cls });
        this.setCard('cardSortino', { text: sor.text, cls: sor.cls });
        this.setCard('cardCalmar', { text: cr.text, cls: cr.cls });
        this.setCard('cardVolatility', vol);
        this.setCard('cardAnnReturn', ar);
        this.setCard('cardExcessDrawdown', { text: exDD.text, cls: exDD.cls });
    }
    
    // ==================== 图表渲染 ====================
    
    renderNavChart(p) {
        if (!p) return;
        const dates = p.dates;
        const series = [];
        
        series.push({
            name: '基金收益',
            type: 'line',
            symbol: 'none',
            lineStyle: { width: 2, color: '#3498db' },
            itemStyle: { color: '#3498db' },
            data: p.navReturns,
            tooltip: {
                formatter: function(params) {
                    const i = params.dataIndex;
                    const v = params.data;
                    if (v == null) return '';
                    const sign = v >= 0 ? '+' : '';
                    let html = `${dates[i]}<br/>基金收益: <b>${sign}${v.toFixed(2)}%</b>`;
                    if (p.benchReturns && p.benchReturns[i] !== null) {
                        const bv = p.benchReturns[i];
                        const bs = bv >= 0 ? '+' : '';
                        html += `<br/>${p.benchmarkName}: <b>${bs}${bv.toFixed(2)}%</b>`;
                    }
                    return html;
                }
            }
        });
        
        if (p.benchReturns) {
            series.push({
                name: p.benchmarkName || '基准指数',
                type: 'line',
                symbol: 'none',
                lineStyle: { width: 2, color: '#e67e22', type: 'dashed' },
                itemStyle: { color: '#e67e22' },
                data: p.benchReturns,
                tooltip: {
                    formatter: function(params) {
                        const i = params.dataIndex;
                        const v = params.data;
                        if (v == null) return '';
                        const sign = v >= 0 ? '+' : '';
                        return `${dates[i]}<br/>${p.benchmarkName}: <b>${sign}${v.toFixed(2)}%</b>`;
                    }
                }
            });
        }
        
        if (p.excess) {
            series.push({
                name: '超额收益',
                type: 'line',
                symbol: 'none',
                lineStyle: { width: 1.5, color: '#9b59b6' },
                itemStyle: { color: '#9b59b6' },
                data: p.excess,
                tooltip: {
                    formatter: function(params) {
                        const i = params.dataIndex;
                        const v = p.excess[i];
                        if (v == null) return '';
                        const sign = v >= 0 ? '+' : '';
                        return `${dates[i]}<br/>超额收益: <b>${sign}${v.toFixed(2)}%</b>`;
                    }
                }
            });
        }
        
        const option = {
            tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
            legend: { data: series.map(s => s.name), top: 0 },
            grid: { left: '3%', right: '4%', bottom: '10%', top: series.length > 0 ? 36 : '3%', containLabel: true },
            xAxis: {
                type: 'category', 
                data: dates, 
                boundaryGap: false,
                axisLabel: { 
                    rotate: dates.length > 60 ? 30 : 0, 
                    fontSize: 11,
                    formatter: v => v.slice(0, 10) 
                }
            },
            yAxis: {
                type: 'value', 
                name: '收益率 (%)',
                axisLabel: { formatter: v => { const s = v >= 0 ? '+' : ''; return s + v.toFixed(2) + '%'; } }
            },
            dataZoom: [
                { type: 'inside', start: 0, end: 100 },
                { type: 'slider', start: 0, end: 100, height: 20, bottom: 0 }
            ],
            series
        };
        this.navChart.setOption(option, true);
    }
    
    renderDrawdownAnalysisChart(p) {
        if (!p) return;
        const dates = p.dates;
        const series = [];
        
        if (p.drawdown && p.drawdown.length > 0) {
            series.push({
                name: '基金回撤',
                type: 'line', 
                symbol: 'none',
                lineStyle: { width: 1.5, color: '#3498db' },
                itemStyle: { color: '#3498db' },
                areaStyle: {
                    color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                        { offset: 0, color: 'rgba(52, 152, 219, 0.25)' },
                        { offset: 1, color: 'rgba(52, 152, 219, 0.02)' }
                    ])
                },
                data: p.drawdown,
                tooltip: {
                    formatter: function(params) {
                        const v = params.data;
                        if (v == null) return '';
                        return `${dates[params.dataIndex]}<br/>基金回撤: <b>${v.toFixed(2)}%</b>`;
                    }
                }
            });
        }
        
        if (p.benchDD && p.benchDD.length > 0) {
            series.push({
                name: '基准回撤',
                type: 'line', 
                symbol: 'none',
                lineStyle: { width: 1.5, color: '#e67e22', type: 'dashed' },
                itemStyle: { color: '#e67e22' },
                data: p.benchDD,
                tooltip: {
                    formatter: function(params) {
                        const v = params.data;
                        if (v == null) return '';
                        return `${dates[params.dataIndex]}<br/>基准回撤: <b>${v.toFixed(2)}%</b>`;
                    }
                }
            });
        }
        
        if (p.excessDD && p.excessDD.length > 0) {
            series.push({
                name: '超额回撤',
                type: 'line', 
                symbol: 'none',
                lineStyle: { width: 1.5, color: '#9b59b6' },
                itemStyle: { color: '#9b59b6' },
                areaStyle: {
                    color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                        { offset: 0, color: 'rgba(155, 89, 182, 0.15)' },
                        { offset: 1, color: 'rgba(155, 89, 182, 0.02)' }
                    ])
                },
                data: p.excessDD,
                tooltip: {
                    formatter: function(params) {
                        const v = params.data;
                        if (v == null) return '';
                        const sign = v >= 0 ? '+' : '';
                        return `${dates[params.dataIndex]}<br/>超额回撤: <b>${sign}${v.toFixed(2)}%</b>`;
                    }
                }
            });
        }
        
        const option = {
            tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
            legend: { data: series.map(s => s.name), top: 0 },
            grid: { left: '3%', right: '4%', bottom: '10%', top: series.length > 0 ? 36 : '3%', containLabel: true },
            xAxis: {
                type: 'category', 
                data: dates, 
                boundaryGap: false,
                axisLabel: { 
                    rotate: dates.length > 60 ? 30 : 0, 
                    fontSize: 11,
                    formatter: v => v.slice(0, 10) 
                }
            },
            yAxis: {
                type: 'value', 
                name: '回撤 (%)',
                max: 0,
                axisLabel: { formatter: v => v.toFixed(2) + '%' }
            },
            dataZoom: [
                { type: 'inside', start: 0, end: 100 },
                { type: 'slider', start: 0, end: 100, height: 20, bottom: 0 }
            ],
            series
        };
        this.drawdownChart.setOption(option, true);
    }
    
    showNoData(msg) {
        this.setStatCardsLoading(false);
        this.setRiskCardsEmpty();
        const empty = {
            title: { 
                text: msg, 
                left: 'center', 
                top: 'center',
                textStyle: { color: '#999', fontSize: 14, fontWeight: 'normal' } 
            },
            xAxis: { show: false }, 
            yAxis: { show: false }, 
            series: []
        };
        this.navChart.setOption(empty, true);
        this.drawdownChart.setOption(empty, true);
    }
    
    showChartWarning(msg) {
        const chartContainer = document.querySelector('#' + this.options.navChartContainer).parentElement;
        let warningEl = document.getElementById('chartWarning');
        if (!warningEl) {
            warningEl = document.createElement('div');
            warningEl.id = 'chartWarning';
            warningEl.style.cssText = 'background:#fff3cd;border:1px solid #ffc107;border-radius:4px;padding:8px 12px;margin-bottom:8px;font-size:13px;color:#856404;';
            chartContainer.parentElement.insertBefore(warningEl, chartContainer);
        }
        warningEl.textContent = msg;
        warningEl.style.display = 'block';
        if (this.chartWarningTimeout) clearTimeout(this.chartWarningTimeout);
        this.chartWarningTimeout = setTimeout(() => {
            if (warningEl) warningEl.style.display = 'none';
        }, 5000);
    }
    
    // ==================== 爬取记录 ====================
    
    loadCrawlRecords(page = 1) {
        this.currentRecordsPage = page;
        CrawlAPI.getRecords(this.statsTag, page, 10).then(data => {
            this.renderCrawlRecords(data.items);
            renderPagination('crawlRecordsPagination', data.page, data.pages, 'statsPage.loadCrawlRecords');
        }).catch(() => {});
    }
    
    deleteRecord(id) {
        if (!confirm('确定删除这条记录？')) return;
        CrawlAPI.deleteRecords([id]).then(() => this.loadCrawlRecords(this.currentRecordsPage));
    }
    
    renderCrawlRecords(records) {
        const tbody = document.getElementById('crawlRecordsBody');
        if (records.length === 0) {
            tbody.innerHTML = '<tr><td colspan="9" class="empty-cell">暂无记录</td></tr>';
            return;
        }
        tbody.innerHTML = records.map(r => `
            <tr>
                <td>${r.id}</td>
                <td>${r.crawl_date}</td>
                <td>${r.start_time ? r.start_time.substring(11, 19) : '-'}</td>
                <td>${r.end_time ? r.end_time.substring(11, 19) : '-'}</td>
                <td><span class="status-badge status-${r.status}">${this.getStatusText(r.status)}</span></td>
                <td>${r.total_funds}</td>
                <td>${r.ocr_success || '-'}</td>
                <td class="error-text">${r.error_message || '-'}</td>
                <td><button class="btn-danger btn-sm" onclick="statsPage.deleteRecord(${r.id})">删除</button></td>
            </tr>
        `).join('');
    }
    
    getStatusText(status) {
        const map = { 'running': '运行中', 'success': '成功', 'failed': '失败' };
        return map[status] || status;
    }
    
    // ==================== 爬取功能 ====================
    
    crawlSingleFund() {
        const fundName = document.getElementById('fundSelect').value;
        if (!fundName) { alert('请先选择基金'); return; }
        const btn = document.getElementById('btnCrawl');
        btn.disabled = true;
        btn.textContent = '爬取中...';
        
        CrawlAPI.crawlFund({ tag: this.analysisTag, fund_name: fundName })
            .then(data => {
                if (data.status === 'running') {
                    throw new Error(data.message);
                }
                this.pollCrawlStatus(0);
            })
            .catch(err => {
                alert('爬取失败: ' + err.message);
                btn.disabled = false;
                btn.textContent = '爬取';
            });
    }
    
    pollCrawlStatus(attempt) {
        CrawlAPI.getStatus().then(data => {
            if (!data.is_running) {
                const btn = document.getElementById('btnCrawl');
                btn.disabled = false;
                btn.textContent = '爬取';
                if (data.last_error) {
                    alert('爬取完成但有错误: ' + data.last_error);
                } else {
                    this.applyAnalysis();
                }
                return;
            }
            if (attempt >= 120) {
                const btn = document.getElementById('btnCrawl');
                btn.disabled = false;
                btn.textContent = '爬取';
                alert('爬取超时，请稍后重试');
                return;
            }
            setTimeout(() => this.pollCrawlStatus(attempt + 1), 1000);
        }).catch(() => {
            setTimeout(() => this.pollCrawlStatus(attempt + 1), 2000);
        });
    }
    
    // ==================== 导出功能 ====================
    
    toggleStatsExportMenu() {
        toggleDropdown('statsExportMenu');
    }
    
    exportStatsData(format) {
        document.getElementById('statsExportMenu').style.display = 'none';
        const params = new URLSearchParams({ format: format, tag: this.statsTag });
        window.location.href = `/api/export?${params.toString()}`;
    }
}


// ==================== 全局辅助函数 ====================

function _fmtRet(v) {
    if (v == null || !isFinite(v)) return '--';
    const s = v >= 0 ? '+' : '';
    return s + v.toFixed(2) + '%';
}

function _fmtNum(v) {
    if (v == null || !isFinite(v)) return '--';
    return v.toFixed(2);
}

function _retColor(v) {
    return (v != null && isFinite(v) && v >= 0) ? '#27ae60' : (v != null && isFinite(v) ? '#e74c3c' : '');
}


// ==================== 全局初始化 ====================

let statsPage;

document.addEventListener('DOMContentLoaded', async function() {
    statsPage = new StatsPage({
        navChartContainer: 'navChart',
        drawdownChartContainer: 'drawdownAnalysisChart'
    });
    await statsPage.init();
});


// ==================== 导出 ====================

window.StatsPage = StatsPage;
