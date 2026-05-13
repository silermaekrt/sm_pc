# 私募基金监控平台

私募排排网（simuwang.com）基金数据自动抓取与监控平台。

## 功能特性

- **自动登录抓取** - 使用 Playwright 模拟浏览器登录，获取"我的自选"基金数据
- **OCR 净值识别** - 通过 Tesseract OCR 识别网页中的净值数字
- **累计净值追踪** - 爬取并存储基金历史累计净值数据
- **基准指数对比** - 支持沪深300、中证500、中证1000等基准指数对比分析
- **风险指标计算** - 夏普比率、索提诺比率、卡玛比率、最大回撤等
- **数据持久化** - CSV 文件存储，支持历史数据查询
- **Web 监控面板** - 浏览器查看基金数据、分页、搜索、排序
- **定时任务** - 每日 09:00/10:00 自动抓取，每周定期执行
- **多格式导出** - 支持 CSV / JSON / XLSX 从 Web 直接下载

## 项目结构

```
sm_pc/
├── app.py                      # Flask Web 服务入口
├── run.py                      # 运行入口（开发环境）
├── run_ocr.py                  # 命令行爬虫（最新净值）
├── run_ocr_cumulative.py       # 命令行爬虫（累计净值）
│
├── config/                     # 配置模块（模块化拆分）
│   ├── __init__.py
│   ├── app.py                  # Flask/路径配置
│   ├── crawler.py              # 爬虫行为配置
│   ├── fund.py                 # 基金类型配置
│   ├── ocr.py                  # OCR 配置
│   └── site.py                 # 站点配置
│
├── routes/                     # API 路由模块
│   ├── __init__.py            # 路由注册
│   ├── _shared.py             # 共享路由函数
│   ├── fund.py                # 基金数据 API
│   ├── crawl.py               # 爬虫控制 API
│   ├── export.py              # 数据导出 API
│   └── benchmark.py            # 基准指数 API
│
├── services/                   # 业务逻辑服务层
│   ├── __init__.py           # DataService 导出
│   ├── data_service.py       # 统一数据访问层
│   ├── period_stats.py        # 区间统计分析（基准收益、回撤）
│   ├── metrics.py             # 风险指标计算
│   ├── csv_store.py           # CSV 存储
│   ├── benchmark/             # 基准指数服务
│   │   └── __init__.py
│   └── crawler/               # 爬虫核心模块
│       ├── __init__.py
│       ├── browser.py        # 浏览器控制
│       ├── nav_crawler.py    # 净值爬取
│       ├── ocr.py            # OCR 识别
│       ├── parser.py         # 页面解析
│       ├── runner.py         # 爬取调度
│       └── storage.py        # 数据存储
│
├── tasks/                      # 后台任务模块
│   └── crawl_task.py          # 爬虫任务 + 统一调度器
│
├── utils/                      # 工具函数
│   ├── __init__.py
│   ├── file.py                # 文件操作
│   └── http.py                # HTTP 工具
│
├── tools/                      # 辅助工具
│   ├── max_drawdown_matrix.py  # 最大回撤矩阵
│   └── plot_benchmark.py       # 基准对比绘图
│
├── templates/
│   ├── index.html             # 基金列表页面
│   └── stats.html             # 统计页面
│
├── static/
│   ├── css/style.css          # 样式
│   └── js/
│       ├── main.js            # 主逻辑
│       ├── utils.js           # 工具函数
│       ├── components/        # UI 组件
│       ├── pages/             # 页面脚本
│       └── services/          # API 调用
│
├── data/                       # 每日快照 CSV（data/YYYYMMDD/tag.csv）
├── screenshots/                # 爬虫调试截图
├── cumulative/                 # 累计净值数据（cumulative/tag/fund/*.csv）
├── base/                       # 基准指数日线数据（base/yyyy/m/d/QT_INDEXQUOTE.txt）
├── logs/                       # 应用日志
│
├── app_state.py                # 应用状态管理
├── app_logging.py              # 日志配置
├── exceptions.py               # 自定义异常
└── requirements.txt            # Python 依赖
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 安装 Playwright 浏览器

```bash
python -m playwright install chromium
```

### 3. 配置 Cookie

在项目根目录创建 `.env` 文件：

```bash
SIMU_COOKIES=your_cookie_here
```

Cookie 获取方法：
1. 浏览器登录 [私募排排网](https://www.simuwang.com)
2. 按 F12 打开开发者工具
3. 切换到 Network（网络）标签
4. 刷新页面，找到任意请求
5. 复制 Request Headers 中的 Cookie 值

### 4. 启动服务

```bash
python run.py
```

访问：
- **本地**: http://127.0.0.1:5000
- **统计页面**: http://127.0.0.1:5000/stats

## 爬虫使用

### 命令行爬取最新净值

```bash
python run_ocr.py                  # 全部标签
python run_ocr.py --tag private    # 只爬私募
python run_ocr.py --tag exp        # 只爬私募（实验）
```

### 命令行爬取累计净值

```bash
python run_ocr.py --cumulative --tag private    # 爬私募累计净值
python run_ocr.py --cumulative --tag exp       # 爬实验组累计净值
```

### API 触发爬虫

```bash
curl -X POST http://127.0.0.1:5000/api/crawl/trigger?tag=private
```

## 功能开关配置

通过 `.env` 文件控制：

```bash
# 功能开关
SAVE_SCREENSHOT=true    # 是否保存截图

# 目录配置
SIMU_SAVE_DIR=data
CUMULATIVE_DIR=cumulative
```

## 数据说明

### 目录结构

| 目录 | 说明 |
|------|------|
| `data/YYYYMMDD/` | 每日爬取快照（最新净值） |
| `cumulative/tag/fund/` | 累计净值历史数据 |
| `base/yyyy/m/d/` | 基准指数日线数据 |
| `screenshots/` | 调试截图 |

### 支持的基准指数

- 沪深300 (H00300.CSI)
- 中证500 (H00905.CSI)
- 中证1000 (H00852.CSI)
- 中证800 (H00906.CSI)
- 上证50 (H00016.CSI)

## 定时任务

| 任务 | 执行时间 | 说明 |
|------|---------|------|
| 每日爬取 | 每天 09:00 | 抓取全部自选基金 |
| 每日累计净值 | 每天 10:00 | 爬取累计净值数据 |
| 每周爬取 | 每周一 09:30 | 额外执行一次 |

## API 接口

### 基金数据

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/funds` | GET | 基金列表（分页、搜索、排序） |
| `/api/funds/latest` | GET | 每个基金最新一条 |
| `/api/funds/dates` | GET | 可用日期范围 |
| `/api/funds/cumulative-list` | GET | 累计净值基金列表 |
| `/api/funds/timeseries` | GET | 时序数据（含基准对比） |
| `/api/funds/risk-metrics` | GET | 风险指标 |
| `/api/funds/compare` | GET | 多基金对比 |
| `/api/funds/benchmarks` | GET | 基准指数列表 |

### 爬虫控制

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/crawl/status` | GET | 爬虫运行状态 |
| `/api/crawl/trigger` | POST | 触发爬虫 |
| `/api/crawl/records` | GET | 爬取记录 |

### 数据导出

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/export` | GET | 导出 CSV/JSON/XLSX |

## 技术栈

| 组件 | 技术 |
|------|------|
| Web 框架 | Flask |
| 爬虫 | Playwright |
| OCR | Tesseract + OpenCV |
| 定时任务 | APScheduler |
| 前端 | Vanilla JS + Chart.js |

## 常见问题

**Q: Cookie 过期后爬虫失败**
A: Cookie 有时效性，手动更新 `.env` 文件中的 `SIMU_COOKIES`。

**Q: 基准指数数据缺失**
A: 基准数据自动回退到最近可用日期，前端会显示提示。

**Q: 如何清理旧数据？**
A: 删除对应目录：`data/`、`cumulative/`、`screenshots/`、`logs/`

## License

MIT
