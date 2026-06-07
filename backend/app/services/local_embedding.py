"""本地 Embedding 引擎（fastembed + ONNX，零 API 成本）。

使用 BAAI/bge-small-zh-v1.5（512维，中文专用，ONNX 格式）。
- 首次加载下载模型（~100MB），之后常驻内存
- 生成速度极快（~8ms/条），完全本地，不调任何 API
- 支持批量生成

设计：单例懒加载（首次使用时初始化），提供 sync 的 embed 方法。
与 MemoryVectorService 配合：优先本地，本地不可用时回退 API。
"""
import logging
import threading

logger = logging.getLogger(__name__)

# 模型配置
DEFAULT_MODEL = "BAAI/bge-small-zh-v1.5"  # 512维，中文专用，ONNX 格式
# 备选模型（更大的中文模型，768维，质量更高但更慢）
# "jinaai/jina-embeddings-v2-base-zh"  # 768维，中英混合
# "intfloat/multilingual-e5-large"     # 1024维，多语言

_model = None
_model_lock = threading.Lock()
_init_error = None


def _get_model():
    """懒加载 fastembed 模型（线程安全单例）。"""
    global _model, _init_error
    if _model is not None:
        return _model
    if _init_error is not None:
        # 之前初始化失败过，不再重试（避免每次请求都尝试加载）
        return None
    with _model_lock:
        if _model is not None:
            return _model
        try:
            from fastembed import TextEmbedding
            logger.info(f"[embedding] 正在加载本地模型 {DEFAULT_MODEL}（首次需下载）...")
            _model = TextEmbedding(model_name=DEFAULT_MODEL)
            logger.info(f"[embedding] 本地模型加载完成，维度 512")
            return _model
        except ImportError:
            _init_error = "fastembed 未安装（pip install fastembed）"
            logger.warning(f"[embedding] {_init_error}，将回退到 API 模式")
            return None
        except Exception as e:
            _init_error = str(e)
            logger.warning(f"[embedding] 本地模型加载失败: {e}，将回退到 API 模式")
            return None


def embed_texts_sync(texts: list[str]) -> list[list[float]]:
    """同步批量生成向量（本地模型）。

    Returns:
        向量列表，每个是 float 列表。失败返回空列表。
    """
    model = _get_model()
    if model is None or not texts:
        return []
    try:
        # fastembed 的 embed 返回生成器，转 list
        vectors = list(model.embed(texts))
        return [v.tolist() for v in vectors]
    except Exception as e:
        logger.warning(f"[embedding] 本地向量生成失败: {e}")
        return []


def embed_one_sync(text: str) -> list[float]:
    """同步生成单条向量（本地模型）。失败返回空列表。"""
    results = embed_texts_sync([text])
    return results[0] if results else []


def is_local_available() -> bool:
    """检查本地 embedding 是否可用（不触发加载）。"""
    return _model is not None or (_init_error is None and _model is None)


def get_status() -> dict:
    """获取 embedding 引擎状态（供前端展示）。"""
    if _model is not None:
        return {"mode": "local", "model": DEFAULT_MODEL, "dim": 512, "available": True}
    if _init_error is not None:
        return {"mode": "api", "model": "API embedding", "error": _init_error, "available": False}
    return {"mode": "uninitialized", "model": DEFAULT_MODEL, "available": None}
