/**
 * static/js/components/chart-component.js - ECharts 图表组件封装
 * 
 * 提供统一的图表渲染接口，简化页面中的 ECharts 使用。
 */

class ChartComponent {
    /**
     * 创建图表组件
     * @param {string} containerId - 图表容器 DOM 元素 ID
     * @param {string} type - 图表类型: 'nav' | 'drawdown'
     */
    constructor(containerId, type = 'nav') {
        this.container = document.getElementById(containerId);
        if (!this.container) {
            console.error(`ChartComponent: 容器 #${containerId} 不存在`);
            return;
        }
        
        this.chart = null;
        this.type = type;
        this.option = {};
        
        this._init();
    }
    
    _init() {
        this.chart = echarts.init(this.container);
        
        // 响应式 resize
        window.addEventListener('resize', () => {
            if (this.chart) {
                this.chart.resize();
            }
        });
    }
    
    /**
     * 渲染净值与基准指数走势图
     */
    renderNavChart(dates, fundNavValues, benchmarkValues, benchmarkName, fundName) {
        // 处理数据
        const fundData = this._processNavData(fundNavValues);
        const benchData = this._processNavData(benchmarkValues);
        
        // 归一化到起始值 = 100
        const normalizedFund = this._normalizeToBase(fundData);
        const normalizedBench = benchmarkValues && benchmarkValues.length > 0 
            ? this._normalizeToBase(benchData) 
            : null;
        
        // 构建系列
        const series = [
            {
                name: fundName || '基金净值',
                type: 'line',
                data: normalizedFund,
                smooth: true,
                symbol: 'none',
                lineStyle: { width: 2, color: '#4a90d9' },
                areaStyle: {
                    color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                        { offset: 0, color: 'rgba(74, 144, 217, 0.3)' },
                        { offset: 1, color: 'rgba(74, 144, 217, 0.05)' }
                    ])
                }
            }
        ];
        
        if (normalizedBench) {
            series.push({
                name: benchmarkName || '基准指数',
                type: 'line',
                data: normalizedBench,
                smooth: true,
                symbol: 'none',
                lineStyle: { width: 2, color: '#e74c3c', type: 'dashed' }
            });
        }
        
        this.option = {
            tooltip: {
                trigger: 'axis',
                formatter: (params) => {
                    let html = `<strong>${params[0].axisValue}</strong><br/>`;
                    params.forEach(p => {
                        const value = p.value !== null ? p.value.toFixed(2) : '--';
                        html += `${p.marker} ${p.seriesName}: ${value}<br/>`;
                    });
                    return html;
                }
            },
            legend: {
                data: [fundName || '基金净值', benchmarkName || '基准指数'].filter(Boolean),
                bottom: 0
            },
            grid: { left: '3%', right: '4%', bottom: '15%', top: '10%', containLabel: true },
            xAxis: {
                type: 'category',
                data: dates,
                boundaryGap: false,
                axisLabel: { rotate: 45 }
            },
            yAxis: {
                type: 'value',
                axisLabel: { formatter: v => v.toFixed(0) }
            },
            dataZoom: [
                { type: 'inside', start: 0, end: 100 },
                { type: 'slider', start: 0, end: 100 }
            ],
            series
        };
        
        this.chart.setOption(this.option, true);
    }
    
    /**
     * 渲染回撤分析图
     */
    renderDrawdownChart(dates, fundDrawdown, benchmarkDrawdown, excessDrawdown) {
        const series = [
            {
                name: '基金回撤',
                type: 'line',
                data: fundDrawdown,
                smooth: true,
                symbol: 'none',
                lineStyle: { width: 2, color: '#e74c3c' },
                areaStyle: {
                    color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                        { offset: 0, color: 'rgba(231, 76, 60, 0.2)' },
                        { offset: 1, color: 'rgba(231, 76, 60, 0)' }
                    ])
                }
            }
        ];
        
        if (benchmarkDrawdown && benchmarkDrawdown.length > 0) {
            series.push({
                name: '基准回撤',
                type: 'line',
                data: benchmarkDrawdown,
                smooth: true,
                symbol: 'none',
                lineStyle: { width: 2, color: '#95a5a6', type: 'dashed' }
            });
        }
        
        if (excessDrawdown && excessDrawdown.length > 0) {
            series.push({
                name: '超额回撤',
                type: 'line',
                data: excessDrawdown,
                smooth: true,
                symbol: 'none',
                lineStyle: { width: 2, color: '#27ae60' }
            });
        }
        
        this.option = {
            tooltip: {
                trigger: 'axis',
                formatter: (params) => {
                    let html = `<strong>${params[0].axisValue}</strong><br/>`;
                    params.forEach(p => {
                        const value = p.value !== null ? p.value.toFixed(2) + '%' : '--';
                        html += `${p.marker} ${p.seriesName}: ${value}<br/>`;
                    });
                    return html;
                }
            },
            legend: {
                data: ['基金回撤', '基准回撤', '超额回撤'].filter((_, i) => {
                    if (i === 0) return true;
                    if (i === 1) return benchmarkDrawdown && benchmarkDrawdown.length > 0;
                    if (i === 2) return excessDrawdown && excessDrawdown.length > 0;
                    return false;
                }),
                bottom: 0
            },
            grid: { left: '3%', right: '4%', bottom: '15%', top: '10%', containLabel: true },
            xAxis: {
                type: 'category',
                data: dates,
                boundaryGap: false,
                axisLabel: { rotate: 45 }
            },
            yAxis: {
                type: 'value',
                axisLabel: { formatter: v => v.toFixed(0) + '%' }
            },
            dataZoom: [
                { type: 'inside', start: 0, end: 100 },
                { type: 'slider', start: 0, end: 100 }
            ],
            series
        };
        
        this.chart.setOption(this.option, true);
    }
    
    /**
     * 清空图表
     */
    clear() {
        if (this.chart) {
            this.chart.clear();
        }
    }
    
    /**
     * 响应窗口大小变化
     */
    resize() {
        if (this.chart) {
            this.chart.resize();
        }
    }
    
    /**
     * 销毁图表实例
     */
    dispose() {
        if (this.chart) {
            this.chart.dispose();
            this.chart = null;
        }
    }
    
    // ==================== 私有方法 ====================
    
    _processNavData(data) {
        if (!data || !Array.isArray(data)) return [];
        return data.map(v => {
            if (v === null || v === undefined || v === '') return null;
            const num = parseFloat(v);
            return isNaN(num) ? null : num;
        });
    }
    
    _normalizeToBase(data) {
        // 找到第一个有效值作为基准
        let baseValue = null;
        let baseIndex = -1;
        
        for (let i = 0; i < data.length; i++) {
            if (data[i] !== null) {
                baseValue = data[i];
                baseIndex = i;
                break;
            }
        }
        
        if (baseValue === null || baseValue === 0) {
            return data.map(() => null);
        }
        
        return data.map((v, i) => {
            if (v === null) return null;
            if (i < baseIndex) return null;
            return (v / baseValue) * 100;
        });
    }
}


// ==================== 工厂函数 ====================

/**
 * 创建净值走势图
 * @param {string} containerId - 容器 ID
 * @returns {ChartComponent}
 */
function createNavChart(containerId) {
    return new ChartComponent(containerId, 'nav');
}

/**
 * 创建回撤分析图
 * @param {string} containerId - 容器 ID
 * @returns {ChartComponent}
 */
function createDrawdownChart(containerId) {
    return new ChartComponent(containerId, 'drawdown');
}


// ==================== 导出 ====================

window.ChartComponent = ChartComponent;
window.createNavChart = createNavChart;
window.createDrawdownChart = createDrawdownChart;
