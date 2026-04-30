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
d:\program\pc\sm_pc\
├── app.py                  # Flask Web 服务入口
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
│   └── crawl_task.py      # 爬虫任务 + 统一调度器
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
├── .env                    # 环境变量配置（Cookie、功能开关）
├── funds.db               # SQLite 数据库别名（指向 instance/）
└── instance/
    └── funds.db           # SQLite 数据库（自动创建）
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
python run_ocr.py --tag private # 只爬取私募标签
python run_ocr.py --tag public  # 只爬取公募标签
python run_ocr.py --tag money   # 只爬取货币标签
```

## 功能开关配置

系统提供两个重要的功能开关，通过修改 `.env` 文件来控制。

### 关闭/打开数据库保存功能（SAVE_DB）

数据库保存功能负责将爬取的基金数据导入 SQLite 数据库。

| 配置值 | 行为 |
|--------|------|
| `SAVE_DB=true` | 爬取完成后自动将数据导入数据库（默认） |
| `SAVE_DB=false` | 仅保存 CSV 文件，不导入数据库 |

**修改方法：**

编辑项目根目录的 `.env` 文件：

```bash
# 关闭数据库保存（仅保存 CSV）
SAVE_DB=false

# 打开数据库保存（同时保存 CSV 和导入数据库）
SAVE_DB=true
```

**适用场景：**
- 关闭：当仅需要 CSV 文件进行备份或分析，不需要 Web 页面查询功能
- 打开：需要通过 Web 界面查询、筛选、导出数据时

**注意事项：**
- 关闭数据库保存后，Web 界面的基金列表可能为空
- CSV 文件始终会被保存到 `data/日期/` 目录，与数据库开关无关

### 关闭/打开截图功能（SAVE_SCREENSHOT）

截图功能会在爬取时保存表格截图和每个基金的净值图片，用于调试和排查 OCR 识别问题。

| 配置值 | 行为 |
|--------|------|
| `SAVE_SCREENSHOT=true` | 保存表格截图和基金净值裁剪图（默认） |
| `SAVE_SCREENSHOT=false` | 不保存任何截图，减少磁盘占用 |

**修改方法：**

编辑 `.env` 文件：

```bash
# 关闭截图功能
SAVE_SCREENSHOT=false

# 打开截图功能
SAVE_SCREENSHOT=true
```

**截图保存位置：**
- 表格截图: `screenshots/日期/标签/table_full_screenshot.png`
- 净值图片: `screenshots/日期/标签/基金名称.png`

**适用场景：**
- 关闭：日常运行，减少磁盘占用，OCR 识别已稳定
- 打开：调试 OCR 识别问题、排查数据抓取异常

**注意事项：**
- 关闭截图功能不影响 OCR 识别的准确性
- 截图文件会占用较多磁盘空间，建议定期清理 `screenshots/` 目录

### 完整 .env 配置示例

```bash
# Cookie 配置
SIMU_COOKIES=your_cookie_here

# 功能开关
SAVE_SCREENSHOT=true   # 是否保存截图（true/false）
SAVE_DB=true           # 是否导入数据库（true/false）

# 可选配置
SIMU_SAVE_DIR=data                      # 数据保存目录
SIMU_SCREENSHOT_DIR=screenshots          # 截图保存目录
TESSERACT_PATH=D:\tools\tesseract_ocr   # Tesseract 安装路径
```

## 使用方式详解

### 方式一：Web 界面管理（推荐）

启动 Web 服务后，可通过浏览器访问以下地址：

| 地址 | 功能 |
|------|------|
| http://127.0.0.1:5000/ | 基金列表页面（查看、搜索、排序） |
| http://127.0.0.1:5000/stats | 统计页面（数据汇总） |
| http://127.0.0.1:5000/auth | 登录凭证管理（配置账号密码） |

### 方式二：命令行直接运行爬虫

不启动 Web 服务，直接运行爬虫脚本：

```bash
# 爬取所有标签（私募、公募、货币）
python run_ocr.py

# 仅爬取私募基金
python run_ocr.py --tag private

# 仅爬取公募基金
python run_ocr.py --tag public

# 仅爬取货币基金
python run_ocr.py --tag money
```

### 方式三：API 接口调用

通过 HTTP 请求触发爬虫：

```bash
# 触发爬虫（私募）
curl -X POST http://127.0.0.1:5000/api/crawl/trigger?tag=private

# 触发爬虫（公募）
curl -X POST http://127.0.0.1:5000/api/crawl/trigger?tag=public

# 导出数据
curl -O http://127.0.0.1:5000/api/export?format=csv
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

- **SQLite 数据库**: `instance/funds.db`（项目根目录）
- **CSV 备份**: `data/YYYYMMDD/tag.csv`（如 `data/20260429/private.csv`）

## 定时任务

| 任务 | 执行时间 | 说明 |
|------|---------|------|
| 每日爬取 | 每天 09:00 | 抓取全部自选基金 |
| 每周爬取 | 每周一 09:30 | 额外执行一次 |
| Cookie 自动刷新 | 每 60 分钟 | 检查是否需要刷新 Cookie |

**注意事项：**
- 定时任务需要 Web 服务保持运行状态
- Windows 下可将 `python app.py` 设为开机启动

## 配置选项

修改 `config.py` 或设置环境变量（推荐在 `.env` 文件中设置）：

| 配置项 | 环境变量 | 默认值 | 说明 |
|--------|---------|--------|------|
| `SIMU_SAVE_DIR` | 数据保存目录 | `data` | CSV 文件保存位置 |
| `SIMU_SCREENSHOT_DIR` | 截图目录 | `screenshots` | 截图保存位置 |
| `TESSERACT_PATH` | OCR 路径 | `D:\tools\tesseract_ocr` | Tesseract 安装目录 |
| `SIMU_URL` | 抓取页面 | simuwang.com/user/option | 目标网址 |
| `GOTO_TIMEOUT` | 页面超时 | 60000ms | 页面加载超时时间 |
| `SELECTOR_TIMEOUT` | 选择器超时 | 30000ms | 元素等待超时时间 |
| `SAVE_SCREENSHOT` | 保存截图 | `true` | `false` 关闭截图 |
| `SAVE_DB` | 导入数据库 | `true` | `false` 关闭数据库导入 |

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

**Q: Web 界面没有数据显示**
A: 检查 `SAVE_DB` 是否为 `true`，以及爬虫是否成功执行。可查看 `data/` 目录是否有 CSV 文件。

**Q: 如何清理旧数据？**
A:
- CSV 文件：删除 `data/` 下对应日期的文件夹
- 数据库：删除 `instance/funds.db`，重启服务会自动创建空数据库
- 截图：删除 `screenshots/` 目录或其中不需要的子目录

**Q: 如何修改定时任务的执行时间？**
A: 编辑 `tasks/crawl_task.py`，修改 `init_scheduler` 函数中的 CronTrigger 参数。

**Q: 关闭截图功能后还能调试 OCR 问题吗？**
A: 可以，但需要临时开启 `SAVE_SCREENSHOT=true`，重新运行爬虫获取截图后再分析。

## License

MIT
