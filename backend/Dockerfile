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

# 预下载 embedding 模型（构建时下载，运行时无需联网）
# 模型: BAAI/bge-small-zh-v1.5 (~100MB)，缓存在镜像层
RUN python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='BAAI/bge-small-zh-v1.5')" || echo "⚠️ 模型预下载失败，运行时会在首次使用时下载"

# 复制代码
COPY . .

# 数据目录
RUN mkdir -p /app/data/chroma_db

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
