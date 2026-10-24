"""
memory/vector.py - 可选的本地向量嵌入后端

设计约束（对齐本项目“零新依赖 / 可离线验证”原则）：
  - 默认关闭（config: memory_vector_enabled=False），关闭时所有检索走原关键词路径；
  - 依赖 fastembed 为**可选**：未安装或初始化失败时静默降级，绝不报错、绝不影响主流程；
  - 不做任何网络 API 调用（fastembed 为本地 ONNX 推理）；
  - 纯函数 cosine/embed 接口便于单测（不依赖模型是否可用）。
"""

import threading
from collections import OrderedDict
from typing import List, Optional

from ..config import get_config
from ..logs import get_logger

logger = get_logger("memory.vector")

_lock = threading.Lock()
_model = None
_unavailable = False

# 文本 → 向量 的进程内 LRU 缓存（有界，防内存增长）
_embed_cache: "OrderedDict[str, List[float]]" = OrderedDict()
_CACHE_MAX = 512


def cosine(a: List[float], b: List[float]) -> float:
    """余弦相似度（纯函数，可独立单测）。任一向量为零向量返回 0。"""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return dot / (na ** 0.5 * nb ** 0.5)


def _get_model():
    """惰性初始化 fastembed 模型；不可用则置 _unavailable 并返回 None"""
    global _model, _unavailable
    if _unavailable:
        return None
    if _model is not None:
        return _model
    with _lock:
        if _model is not None or _unavailable:
            return _model
        try:
            from fastembed import TextEmbedding  # 可选依赖
        except Exception as e:  # ImportError 等：静默降级
            _unavailable = True
            logger.info("向量后端不可用（未安装 fastembed？）: %s", e)
            return None
        try:
            name = str(get_config("memory_vector_model", "Xenova/all-MiniLM-L6-v2"))
            _model = TextEmbedding(name)
        except Exception as e:
            _unavailable = True
            logger.info("向量模型初始化失败，降级关键词检索: %s", e)
            return None
    return _model


def enabled() -> bool:
    """向量增强是否开启且后端可用（供调用方快速判断）"""
    if not get_config("memory_vector_enabled", False):
        return False
    return _get_model() is not None


def embed(texts: List[str]) -> Optional[List[List[float]]]:
    """把文本编码为向量列表。未开启或后端不可用/失败时返回 None（调用方据此降级）。"""
    if not get_config("memory_vector_enabled", False):
        return None
    model = _get_model()
    if model is None or not texts:
        return None

    results: List[Optional[List[float]]] = [None] * len(texts)
    to_encode: List[str] = []
    positions: List[int] = []
    for i, t in enumerate(texts):
        cached = _embed_cache.get(t)
        if cached is not None:
            results[i] = cached
        else:
            to_encode.append(t)
            positions.append(i)

    if to_encode:
        try:
            embs = list(model.embed(to_encode))
        except Exception as e:
            logger.info("向量编码失败，本次降级: %s", e)
            return None
        for text, pos, emb in zip(to_encode, positions, embs):
            vec = [float(x) for x in emb]
            results[pos] = vec
            _embed_cache[text] = vec
            _embed_cache.move_to_end(text)
            while len(_embed_cache) > _CACHE_MAX:
                _embed_cache.popitem(last=False)

    return results  # type: ignore[return-value]
