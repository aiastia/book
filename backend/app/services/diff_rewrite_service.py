"""Diff Rewrite：扫描 cleaner 没改干净的 AI 指纹句，交给小模型改写。

流程：
  1. 扫描器找出问题句（意识到/试图/仿佛/像是在/不是A而是B 等带整句的）
  2. 每句带前后1句上下文打包成一个 batch
  3. 调润色 API（gpt-4o-mini），要求只改 AI 味、不扩写、不新增
  4. 四道闸校验后回填原文

cleaner 处理的是「能安全删除/替换」的词级口癖。
Diff Rewrite 处理的是「需要改句式但不能丢信息」的句子。
"""

import json
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

_R = r"[他她它]"

# ====================================================================
# 扫描器：找出 cleaner 没改干净的 AI 指纹句
# ====================================================================
_SCAN_PATTERNS: list[re.Pattern] = [
    # "她意识到/发现/知道/明白/觉得 + 整句"（cleaner 只删句末声明，不碰整句）
    re.compile(rf"{_R}(?:意识到|发现|知道|明白|觉得|认为)[^。！？]{{5,80}}[。！？]"),
    # "，试图/表示 + 动作"
    re.compile(r"[，。]\s*(?:试图|表示)[^。！？]{2,40}"),
    # "仿佛/似乎 + 整句"（cleaner 只降频，不删意思）
    re.compile(r"(?:^|[。！？\n])(?:[^。！？\n]{0,5})?(?:仿佛|似乎)[^。！？]{5,80}[。！？]"),
    # "像是在/似乎是在/仿佛是在 + X"
    re.compile(r"[，。]\s*(?:像是在|似乎是在|仿佛是在)[^。！？]{2,40}"),
    # "不是因为X，而是因为Y"（复杂版，cleaner 只处理简单版）
    re.compile(r"不是(?:因为)?[^，。]{2,15}[，。]\s*(?:而是?|而是?因为)[^。！？]{5,50}"),
]


def scan_fingerprint_sentences(text: str) -> list[dict]:
    """扫描正文，返回命中 AI 指纹的句子列表。

    返回: [{start, end, sentence, reason}, ...]
    """
    hits = []
    for pat in _SCAN_PATTERNS:
        for m in pat.finditer(text):
            sentence = m.group(0).strip()
            if len(sentence) < 8:
                continue
            # 去重：同一位置不重复报
            start = m.start()
            if any(abs(h["start"] - start) < 5 for h in hits):
                continue
            hits.append({
                "start": start,
                "end": m.end(),
                "sentence": sentence,
                "reason": pat.pattern[:30],
            })
    # 按位置排序
    hits.sort(key=lambda h: h["start"])
    return hits


# ====================================================================
# 打包：带上下文
# ====================================================================
def _extract_context(text: str, start: int, end: int) -> tuple[str, str]:
    """提取问题句的前一句和后一句作为上下文。"""
    # 前一句：往前找最近的句号
    before = text[:start].rstrip()
    last_break = max(before.rfind("。"), before.rfind("！"), before.rfind("？"), before.rfind("\n"))
    prev_sentence = before[last_break + 1:].strip() if last_break >= 0 else ""
    # 后一句：往后找下一个句号
    after = text[end:].lstrip()
    next_break = -1
    for punct in ["。", "！", "？", "\n"]:
        idx = after.find(punct)
        if idx >= 0 and (next_break < 0 or idx < next_break):
            next_break = idx
    next_sentence = after[:next_break + 1].strip() if next_break >= 0 else ""
    return prev_sentence, next_sentence


# ====================================================================
# 调润色 API
# ====================================================================
async def _call_rewrite_api(
    base_url: str,
    api_key: str,
    model: str,
    sentences: list[dict],
) -> Optional[list[dict]]:
    """调用润色 API，返回改写结果 [{i, t}]。失败返回 None。"""
    import httpx

    # 构造请求
    items = []
    for idx, s in enumerate(sentences):
        prev, nxt = s.get("ctx_prev", ""), s.get("ctx_next", "")
        context = ""
        if prev:
            context += f"上文：{prev}\n"
        context += f"原句：{s['sentence']}\n"
        if nxt:
            context += f"下文：{nxt}"
        items.append({"i": idx, "c": context})

    system_prompt = (
        "你是一个文本编辑器。下面每条包含上文、原句、下文。\n"
        "对每个「原句」，只改掉 AI 味（过度解释/心理说明/连接词/解释性从句），"
        "保持意思不变，禁止扩写，禁止新增内容，禁止改变人称。\n"
        "如果原句已经够好，原样返回。\n"
        "严格输出 JSON 数组：[{\"i\": 编号, \"t\": \"改后句子\"}]，不要任何其他文字。"
    )

    url = base_url.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(items, ensure_ascii=False)},
        ],
        "temperature": 0.3,
        "max_tokens": 2000,
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=body, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
        # 解析 JSON
        from app.services.json_helper import clean_json_response, parse_json
        cleaned = clean_json_response(content)
        parsed = parse_json(cleaned)
        if isinstance(parsed, list):
            return parsed
        logger.warning(f"[rewrite] API 返回非数组: {content[:200]}")
        return None
    except Exception as e:
        logger.warning(f"[rewrite] API 调用失败: {e}")
        return None


# ====================================================================
# 四道闸校验
# ====================================================================
def _validate_rewrite(original: str, rewritten: str) -> bool:
    """四道闸：空值/长度变化>50%/专名丢失/无变化 → False（不通过）。"""
    if not rewritten or not rewritten.strip():
        return False
    # 无变化
    if rewritten.strip() == original.strip():
        return False
    # 长度变化超过 50%
    orig_len = len(original.strip())
    new_len = len(rewritten.strip())
    if orig_len > 0:
        ratio = new_len / orig_len
        if ratio < 0.5 or ratio > 1.5:
            return False
    # 专名检测：原句中的 2~4 字连续中文词（粗略），改写后不应全丢
    # 只检查"人名/地名"——简化为：原句里出现 2 次以上的 2 字词
    _NAME_RE = re.compile(r"[\u4e00-\u9fff]{2,4}")
    orig_names = set(_NAME_RE.findall(original))
    # 过滤掉太常见的词
    orig_names = {n for n in orig_names if len(n) >= 2 and original.count(n) >= 1}
    if orig_names:
        lost = [n for n in orig_names if n not in rewritten]
        # 如果超过一半的专名丢了，不通过
        if len(lost) > len(orig_names) / 2:
            return False
    return True


# ====================================================================
# 主函数
# ====================================================================
async def diff_rewrite(
    text: str,
    base_url: str,
    api_key: str,
    model: str,
) -> tuple[str, dict]:
    """对 cleaner 处理后的正文执行 Diff Rewrite。

    返回 (rewritten_text, stats)
    stats: {改写句数, 跳过句数, API失败}
    """
    # 1. 扫描
    hits = scan_fingerprint_sentences(text)
    if not hits:
        return text, {"命中": 0}

    # 2. 加上下文
    for h in hits:
        prev, nxt = _extract_context(text, h["start"], h["end"])
        h["ctx_prev"] = prev
        h["ctx_next"] = nxt

    logger.info(f"[rewrite] 扫描到 {len(hits)} 个指纹句")

    # 3. 调 API
    results = await _call_rewrite_api(base_url, api_key, model, hits)
    if results is None:
        return text, {"命中": len(hits), "API失败": True}

    # 4. 回填 + 四道闸
    rewritten_count = 0
    skipped = 0
    # 从后往前替换，避免位置偏移
    replacements = []
    for r in results:
        idx = r.get("i")
        new_text = r.get("t", "")
        if idx is None or idx >= len(hits):
            continue
        hit = hits[idx]
        original = hit["sentence"]
        if _validate_rewrite(original, new_text):
            replacements.append((hit["start"], hit["end"], new_text))
            rewritten_count += 1
        else:
            skipped += 1

    # 从后往前应用替换
    for start, end, new_text in sorted(replacements, key=lambda x: -x[0]):
        text = text[:start] + new_text + text[end:]

    stats = {
        "命中": len(hits),
        "改写": rewritten_count,
        "跳过": skipped,
    }
    return text, stats
