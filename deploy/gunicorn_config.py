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
