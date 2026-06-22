"""文本切分工具：按自然段切分章节正文为向量检索用的 chunk。

策略：
- 按段落（空行分隔）切分
- 每个 chunk 控制在 250-400 字（适配 bge-small-zh 的 512 token 上限）
- 相邻 chunk 重叠 80 字（保证语义连续性）
- 不在句子中间截断（对齐到句号/段落边界）

模型上限参考：
- bge-small-zh-v1.5: 512 tokens ≈ 340 中文字（chunk 必须 < 400 字）
- jina-v2-base-zh: 8192 tokens（不受限，但小 chunk 检索更精确）
"""
import re
from typing import List

DEFAULT_MIN_CHUNK = 250
DEFAULT_MAX_CHUNK = 400
DEFAULT_OVERLAP = 80


def split_text_to_chunks(
    text: str,
    min_chunk_size: int = DEFAULT_MIN_CHUNK,
    max_chunk_size: int = DEFAULT_MAX_CHUNK,
    overlap_size: int = DEFAULT_OVERLAP,
) -> List[str]:
    """将长文本切分为重叠的 chunk。

    Args:
        text: 原始文本（章节正文）
        min_chunk_size: 最小 chunk 字数（默认 250）
        max_chunk_size: 最大 chunk 字数（默认 400）
        overlap_size: 相邻 chunk 重叠字数（默认 80）

    Returns:
        chunk 字符串列表
    """
    if not text or not text.strip():
        return []

    if len(text) <= max_chunk_size:
        return [text.strip()]

    # 1. 按段落切分
    paragraphs = _split_paragraphs(text)
    if not paragraphs:
        return [text.strip()]

    # 2. 按段落累积，达到目标长度就切一个 chunk
    chunks = []
    current = ""
    current_len = 0

    for para in paragraphs:
        # 单段超过 max → 按句子进一步切
        if len(para) > max_chunk_size:
            if current:
                chunks.append(current.strip())
                current = ""
                current_len = 0
            sentences = _split_sentences(para)
            for sent in sentences:
                if current_len + len(sent) > max_chunk_size and current_len >= min_chunk_size:
                    chunks.append(current.strip())
                    current = _get_overlap(current, overlap_size) + sent
                    current_len = len(current)
                else:
                    current += sent
                    current_len += len(sent)
            continue

        # 正常段落累积
        if current_len + len(para) > max_chunk_size and current_len >= min_chunk_size:
            chunks.append(current.strip())
            current = _get_overlap(current, overlap_size) + para
            current_len = len(current)
        else:
            current += "\n" + para if current else para
            current_len = len(current)

    if current.strip():
        chunks.append(current.strip())

    return chunks


def _split_paragraphs(text: str) -> List[str]:
    """按空行/换行切分段落。"""
    parts = re.split(r'\n\s*\n', text)
    if len(parts) <= 1:
        parts = text.split('\n')
    return [p.strip() for p in parts if p.strip()]


def _split_sentences(text: str) -> List[str]:
    """按句号/问号/感叹号切分句子。"""
    sentences = re.split(r'(?<=[。！？!?…\n])', text)
    return [s for s in sentences if s.strip()]


def _get_overlap(text: str, overlap_size: int) -> str:
    """从文本末尾取 overlap_size 字作为重叠（对齐到句号边界）。"""
    if len(text) <= overlap_size:
        return text
    tail = text[-overlap_size:]
    for i, ch in enumerate(tail):
        if ch in '。！？!?\n':
            return tail[i + 1:]
    return tail


def estimate_chunks(text: str, max_chunk_size: int = DEFAULT_MAX_CHUNK) -> int:
    """估算文本会被切成多少个 chunk。"""
    if not text:
        return 0
    total = len(text)
    effective = max_chunk_size - DEFAULT_OVERLAP
    return max(1, (total + effective - 1) // effective)
