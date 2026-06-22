# 墨语后端 Dockerfile
FROM python:3.12-slim AS backend

WORKDIR /app

# 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制代码
COPY . .

# 数据目录
RUN mkdir -p /app/data/chroma_db

# Embedding 模型说明（不预下载，运行时首次使用自动下载）
# 模型缓存通过 docker-compose 的 volume 持久化
# 模型: jina-embeddings-v2-base-zh(~300MB) 或 bge-small-zh-v1.5(~100MB)
# 如需预下载（离线环境），取消下面注释：
# RUN python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='jinaai/jina-embeddings-v2-base-zh')"

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
