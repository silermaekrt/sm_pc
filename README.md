# 私募基金监控平台

私募排排网（simuwang.com）基金数据自动抓取与监控平台。

## 功能特性

- **自动登录抓取** - 使用 Playwright 模拟浏览器登录，获取"我的自选"基金数据
- **OCR 净值识别** - 通过 Tesseract OCR 识别网页中的净值数字
- **自动 Cookie 刷新** - 保存账号密码，后台定时自动模拟登录刷新 Cookie，无需手动更新
- **数据持久化** - SQLite 数据库存储，支持历史数据查询
- **Web 监控面板** - 浏览器查看基金数据、分页、搜索、排序
- **定时任务** - 每日 09:00 自动抓取，每周一定期执行
- **多格式导出** - 支持 CSV / JSON / XLSX 从 Web 直接下载，无需打开文件目录

## 项目结构

```
d:\program\pc\
├── app.py                  # Flask Web 服务入口（52 行）
├── config.py               # 全局配置（Cookie、路径、超时等）
├── models.py               # 数据库模型（Fund、CrawlRecord、LoginCredential）
├── run_ocr.py              # 爬虫主程序（命令行可单独运行）
├── requirements.txt        # Python 依赖
│
├── routes/                 # API 路由模块
│   ├── __init__.py        # 路由注册
│   ├── page.py            # 页面路由（/、/stats）
│   ├── fund.py            # 基金数据 API
│   ├── crawl.py           # 爬虫控制 API
│   ├── export.py          # 数据导出 API（CSV/JSON/XLSX）
│   └── auth.py            # 登录凭证管理 API
│
├── tasks/                  # 后台任务模块
│   ├── __init__.py
│   └── crawl_task.py       # 爬虫任务 + 统一调度器
│
├── auth/                   # 认证模块
│   ├── __init__.py
│   └── cookie.py          # 自动登录 + Cookie 刷新
│
├── templates/
│   ├── index.html          # 基金列表页面
│   └── stats.html          # 统计页面
├── static/
│   ├── css/style.css       # 样式
│   └── js/main.js          # 前端逻辑
├── data/                   # CSV 数据文件目录
├── screenshots/            # 爬虫调试截图
└── funds.db               # SQLite 数据库（自动创建）
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

**方式一：手动配置 Cookie（可选）**

在项目根目录创建 `.env` 文件，或设置环境变量：

```bash
# .env 文件方式
SIMU_COOKIES=your_cookie_here
```

Cookie 获取方法：
1. 浏览器登录 [私募排排网](https://www.simuwang.com)
2. 按 F12 打开开发者工具
3. 切换到 Network（网络）标签
4. 刷新页面，找到任意请求
5. 复制 Request Headers 中的 Cookie 值

**方式二：Web 界面配置账号密码（推荐，自动刷新 Cookie）**

启动服务后访问 http://127.0.0.1:5000/auth，进入登录凭证管理页面：
- 输入私募排排网用户名和密码
- 系统自动模拟登录获取 Cookie
- 后台每分钟检查一次，到期自动刷新，无需手动管理

### 4. 启动服务

```bash
python app.py
```

启动后访问：
- **本地**: http://127.0.0.1:5000
- **局域网**: http://192.168.x.x:5000

### 5. 单独运行爬虫（不启动 Web 服务）

```bash
python run_ocr.py               # 爬取全部标签（默认）
python run_ocr.py --tag public  # 只爬取公募标签
python run_ocr.py --tag money   # 只爬取货币标签
```

## 数据说明

### 数据库字段

| 字段 | 说明 |
|------|------|
| fund_name | 基金名称 |
| fund_code | 基金代码（如 SNxxx） |
| strategy | 投资策略 |
| net_value | 最新净值（OCR 识别） |
| net_change | 净值变动 |
| this_year | 今年来收益率 |
| one_year | 近一年收益率 |
| three_year | 近三年收益率 |
| since_inception | 成立来收益率 |
| drawdown | 历史最大回撤 |
| crawl_date | 爬取日期 |

### 存储位置

- **SQLite 数据库**: `funds.db`（项目根目录）
- **CSV 备份**: `data/YYYYMMDD/tag.csv`（如 `data/20260429/private.csv`）

## 定时任务

| 任务 | 执行时间 | 说明 |
|------|---------|------|
| 每日爬取 | 每天 09:00 | 抓取全部自选基金 |
| 每周爬取 | 每周一 09:30 | 额外执行一次 |
| Cookie 自动刷新 | 每 1 分钟 | 检查是否需要刷新 Cookie |

## 配置选项

修改 `config.py` 或设置环境变量：

| 配置项 | 环境变量 | 默认值 | 说明 |
|--------|---------|--------|------|
| `SIMU_SAVE_DIR` | 数据保存目录 | `data` | |
| `SIMU_SCREENSHOT_DIR` | 截图目录 | `screenshots` | |
| `TESSERACT_PATH` | OCR 路径 | `D:\tools\tesseract_ocr` | |
| `SIMU_URL` | 抓取页面 | simuwang.com/user/option | |
| `GOTO_TIMEOUT` | 页面超时 | 60000ms | |
| `SELECTOR_TIMEOUT` | 选择器超时 | 30000ms | |
| `SAVE_SCREENSHOT` | 保存截图 | `true` | `false` 关闭截图，OCR 仍正常工作 |
| `SAVE_DB` | 导入数据库 | `true` | `false` 关闭数据库导入，仅保存 CSV |

## 技术栈

| 组件 | 技术 |
|------|------|
| Web 框架 | Flask |
| 数据库 | SQLite + SQLAlchemy |
| 爬虫 | Playwright |
| OCR | Tesseract |
| 定时任务 | APScheduler |
| 图像处理 | OpenCV、Pillow |
| HTTP 请求 | requests |

## API 接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 基金列表页面 |
| `/stats` | GET | 统计页面 |
| `/api/funds` | GET | 基金列表（分页、搜索、排序） |
| `/api/funds/<name>` | GET | 单个基金详情（按名称） |
| `/api/stats/summary` | GET | 统计数据汇总 |
| `/api/crawl/status` | GET | 爬虫运行状态 |
| `/api/crawl/trigger` | POST | 手动触发爬虫 |
| `/api/export` | GET | 导出数据（CSV/JSON/XLSX） |
| `/api/auth/credentials` | GET | 获取登录凭证列表 |
| `/api/auth/credentials` | POST | 添加/更新登录凭证 |
| `/api/auth/credentials/<id>` | DELETE | 删除登录凭证 |
| `/api/auth/refresh` | POST | 手动刷新 Cookie |
| `/api/auth/status` | GET | Cookie 刷新状态 |

## 数据导出

访问 `/api/export` 从 Web 直接下载数据文件，支持以下格式：

```
/api/export                  # CSV（默认）
/api/export?format=json     # JSON
/api/export?format=xlsx     # Excel
/api/export?crawl_date=20260426           # 指定日期
/api/export?search=量化&format=csv        # 筛选后导出
```

## 常见问题

**Q: Cookie 过期后爬虫失败**
A: Cookie 有时效性，推荐在 Web 界面（/auth）保存账号密码，系统会自动刷新 Cookie。也可手动更新 `.env` 文件中的 `SIMU_COOKIES`。

**Q: OCR 识别成功率低**
A: 确保 Tesseract 已安装且路径正确，截图清晰度会影响识别效果。

**Q: 定时任务没执行**
A: 确保服务保持运行状态，Windows 下可将 `python app.py` 设为开机启动。

## License

MIT
