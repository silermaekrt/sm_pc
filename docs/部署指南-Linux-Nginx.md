# 私募基金监控平台 - Linux + Nginx 部署指南

## 环境要求

| 组件 | 版本要求 |
|------|----------|
| Ubuntu 20.04+ / CentOS 8+ | - |
| Python | 3.10+ |
| Nginx | 1.18+ |
| Redis | 可选（用于会话存储） |

---

## 一、服务器环境准备

### 1.1 更新系统并安装基础依赖

```bash
# Ubuntu/Debian
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3.10 python3.10-venv python3-pip \
    nginx curl git wget supervisor

# CentOS/RHEL
sudo yum install -y python3 python3-pip nginx curl git wget
sudo yum install -y epel-release
sudo yum install -y supervisor
```

### 1.2 安装 Redis（可选，用于会话共享）

```bash
# Ubuntu/Debian
sudo apt install -y redis-server
sudo systemctl enable redis-server
sudo systemctl start redis-server

# CentOS/RHEL
sudo yum install -y redis
sudo systemctl enable redis
sudo systemctl start redis
```

---

## 二、创建应用用户

```bash
# 创建专用用户（可选但推荐）
sudo useradd -m -s /bin/bash smpc
sudo mkdir -p /opt/smpc
sudo chown smpc:smpc /opt/smpc
```

---

## 三、部署应用代码

### 3.1 上传代码

```bash
# 方式1: Git 拉取
cd /opt/smpc
sudo -u smpc git clone <your-repo-url> .
sudo -u smpc git checkout <tag-or-branch>

# 方式2: SCP/SFTP 上传后解压
sudo cp sm_pc.tar.gz /opt/smpc/
sudo -u smpc tar -xzf sm_pc.tar.gz
```

### 3.2 创建虚拟环境

```bash
cd /opt/smpc
sudo -u smpc python3 -m venv venv
sudo -u smpc ./venv/bin/pip install --upgrade pip
sudo -u smpc ./venv/bin/pip install -r requirements.txt
```

### 3.3 安装 Playwright 浏览器

```bash
sudo -u smpc /opt/smpc/venv/bin/playwright install chromium
```

### 3.4 安装 Tesseract OCR

```bash
# Ubuntu/Debian
sudo apt install -y tesseract-ocr tesseract-ocr-chi-sim

# CentOS/RHEL
sudo yum install -y tesseract tesseract-langpack-chi_sim
```

---

## 四、配置文件

### 4.1 创建 `.env` 文件

```bash
sudo -u smpc nano /opt/smpc/.env
```

```bash
# ============================================
# 私募基金监控平台 - 生产环境配置
# ============================================

# Cookie 配置（从浏览器获取）
SIMU_COOKIES=your_cookie_here

# Tesseract OCR 路径（Linux 通常不需要设置，会自动检测）
# TESSERACT_PATH=/usr/bin

# 目录配置
SIMU_SAVE_DIR=/opt/smpc/data
SIMU_SCREENSHOT_DIR=/opt/smpc/screenshots
CUMULATIVE_DIR=/opt/smpc/cumulative
INDICES_DIR=/opt/smpc/indices

# 日志配置
LOG_LEVEL=INFO
LOG_FILE=/opt/smpc/logs/app.log

# 功能开关
SAVE_SCREENSHOT=false
```

### 4.2 创建日志目录

```bash
sudo -u smpc mkdir -p /opt/smpc/logs
sudo chmod 755 /opt/smpc/logs
```

---

## 五、Gunicorn 配置

### 5.1 安装 Gunicorn

```bash
sudo -u smpc /opt/smpc/venv/bin/pip install gunicorn gevent
```

### 5.2 创建 Gunicorn 配置文件

```bash
sudo nano /opt/smpc/gunicorn_config.py
```

```python
# gunicorn_config.py
import multiprocessing

# 绑定地址
bind = "127.0.0.1:5000"

# 工作进程数（建议 CPU 核心数 * 2 + 1）
workers = multiprocessing.cpu_count() * 2 + 1

# 使用 gevent 异步 worker（适合 I/O 密集型）
worker_class = "gevent"

# 每个 worker 的线程数
threads = 2

# 超时配置
timeout = 120
keepalive = 5

# 日志
accesslog = "/opt/smpc/logs/gunicorn_access.log"
errorlog = "/opt/smpc/logs/gunicorn_error.log"
loglevel = "info"

# 进程名
proc_name = "smpc"

# 预加载应用（共享内存）
preload_app = True

# 优雅重启
graceful_timeout = 30
```

---

## 六、Supervisor 配置

### 6.1 创建 Supervisor 配置

```bash
sudo nano /etc/supervisor/conf.d/smpc.conf
```

```ini
[program:smpc]
command=/opt/smpc/venv/bin/gunicorn -c /opt/smpc/gunicorn_config.py app:app
directory=/opt/smpc
user=smpc
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/opt/smpc/logs/supervisor.log
stopwaitsecs=60
killasgroup=true
stopasgroup=true
```

### 6.2 重新加载 Supervisor

```bash
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start smpc
```

### 6.3 验证服务状态

```bash
sudo supervisorctl status smpc
curl http://127.0.0.1:5000/
```

---

## 七、Nginx 配置

### 7.1 创建 Nginx 站点配置

```bash
sudo nano /etc/nginx/sites-available/smpc
```

```nginx
upstream smpc_backend {
    server 127.0.0.1:5000 fail_timeout=0;
}

server {
    listen 80;
    server_name your-domain.com;  # 替换为你的域名或 IP

    # 重定向到 HTTPS（可选）
    # return 301 https://$server_name$request_uri;

    client_max_body_size 100M;

    # 静态文件
    location /static/ {
        alias /opt/smpc/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # 模板文件（不应直接访问）
    location /templates/ {
        internal;
    }

    # API 代理
    location / {
        proxy_pass http://smpc_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # 超时配置
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;

        # WebSocket 支持（如果需要）
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    # 健康检查
    location /health {
        proxy_pass http://smpc_backend;
        access_log off;
    }
}
```

### 7.2 启用站点

```bash
# Ubuntu/Debian
sudo ln -s /etc/nginx/sites-available/smpc /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default  # 移除默认站点

# CentOS/RHEL（配置在 /etc/nginx/conf.d/）
sudo mv /etc/nginx/conf.d/default.conf /etc/nginx/conf.d/default.conf.bak

# 测试配置
sudo nginx -t

# 重载 Nginx
sudo systemctl reload nginx
sudo systemctl enable nginx
```

---

## 八、SSL/HTTPS 配置（可选但强烈推荐）

### 8.1 使用 Let's Encrypt 免费证书

```bash
# 安装 Certbot
sudo apt install -y certbot python3-certbot-nginx

# 获取证书
sudo certbot --nginx -d your-domain.com

# 自动续期测试
sudo certbot renew --dry-run
```

### 8.2 配置自动续期 Cron

```bash
sudo crontab -e
```

```
# 每天检查证书，必要时自动续期
0 3 * * * /usr/bin/certbot renew --quiet
```

---

## 九、防火墙配置

```bash
# Ubuntu/Debian (UFW)
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS
sudo ufw enable

# CentOS/RHEL (firewalld)
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --permanent --add-service=https
sudo firewall-cmd --reload
```

---

## 十、日志管理

### 10.1 日志轮转配置

```bash
sudo nano /etc/logrotate.d/smpc
```

```
/opt/smpc/logs/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 0640 smpc smpc
    sharedscripts
    postrotate
        supervisorctl restart smpc > /dev/null 2>&1 || true
    endscript
}
```

---

## 十一、常见问题排查

### 11.1 服务无法启动

```bash
# 查看 Supervisor 日志
sudo tail -f /opt/smpc/logs/supervisor.log

# 查看 Gunicorn 错误日志
sudo tail -f /opt/smpc/logs/gunicorn_error.log

# 测试应用是否能正常运行
cd /opt/smpc
sudo -u smpc ./venv/bin/python -c "from app import app; print(app)"
```

### 11.2 Tesseract 未找到

```bash
# 确认安装
which tesseract
tesseract --version

# 如需指定路径，在 .env 中设置
echo "TESSERACT_PATH=/usr/bin" >> /opt/smpc/.env
sudo supervisorctl restart smpc
```

### 11.3 Playwright 浏览器问题

```bash
# 重新安装浏览器
sudo -u smpc /opt/smpc/venv/bin/playwright install chromium

# 检查依赖
sudo -u smpc /opt/smpc/venv/bin/playwright install-deps
```

### 11.4 Nginx 502 Bad Gateway

```bash
# 确认 Gunicorn 正在运行
sudo supervisorctl status smpc

# 确认端口监听
sudo ss -tlnp | grep 5000
```

---

## 十二、更新部署

```bash
# 1. 停止服务
sudo supervisorctl stop smpc

# 2. 更新代码
cd /opt/smpc
sudo -u smpc git pull

# 3. 更新依赖
sudo -u smpc ./venv/bin/pip install -r requirements.txt

# 4. 重启服务
sudo supervisorctl start smpc

# 5. 验证
sudo supervisorctl status smpc
curl http://127.0.0.1:5000/
```

---

## 十三、目录权限汇总

| 目录 | 所有者 | 权限 |
|------|--------|------|
| `/opt/smpc/` | smpc:smpc | 755 |
| `/opt/smpc/venv/` | smpc:smpc | 755 |
| `/opt/smpc/logs/` | smpc:smpc | 755 |
| `/opt/smpc/data/` | smpc:smpc | 755 |
| `/opt/smpc/screenshots/` | smpc:smpc | 755 |
| `/opt/smpc/cumulative/` | smpc:smpc | 755 |

---

## 访问地址

- 本地测试: `http://127.0.0.1:5000`
- 生产访问: `http://your-domain.com`
- 统计页面: `http://your-domain.com/stats`
