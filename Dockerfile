# UniLLM Platform —— 容器镜像
#
# ⚠️ 构建需要**外网**：`pip install` 会从 PyPI 拉取依赖。
#    离线内网环境请见 README「离线构建替代方案」（pip download 预置 wheel / 内网离线基础镜像）。
#
# SQLite 单文件数据库：运行时请固定使用 1 个 uvicorn worker，
# 多 worker 会加剧写锁竞争（见 docker-compose.yml 的 --workers 1）。

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# 1) 先装依赖，充分利用层缓存（requirements 不变时不重复安装）
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 2) 再复制应用代码与配置（app/web 随之进入镜像）
COPY app ./app
COPY config.yaml ./config.yaml
COPY scripts ./scripts

# 3) 运行期数据与日志目录（建议用 volume 挂载以持久化，尤其是 data/.api_token）
RUN mkdir -p /app/data /app/logs

EXPOSE 8000

# 单 worker：SQLite 场景下的既定约束
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
