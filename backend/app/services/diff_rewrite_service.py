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

# ====================================================================
# 扫描器：关键词驱动，匹配后提取整句
# ====================================================================
# 格式: (关键词, 类别标签)
# 越靠前的关键词优先匹配（去重时保留更早出现的）
_SCAN_KEYWORDS: list[tuple[str, str]] = [
    # === 过度心理描写（AI 最爱解释角色内心） ===
    ("意识到", "AI心理动词"),
    ("感觉到", "AI感官动词"),
    ("感受到", "AI感官动词"),
    ("只觉得", "AI感官动词"),
    ("只感觉", "AI感官动词"),
    ("不禁", "AI情绪副词"),
    ("不由得", "AI情绪副词"),
    ("忍不住", "AI情绪副词"),
    ("下意识", "AI心理副词"),
    ("脑海里", "AI心理空间"),
    ("内心深处", "AI心理空间"),
    ("心底", "AI心理空间"),
    # === 模糊/不确定性句式（AI 缺乏叙事确定感） ===
    ("仿佛", "AI模糊副词"),
    ("似乎", "AI模糊副词"),
    ("隐约", "AI模糊副词"),
    ("好像是在", "AI模糊比拟"),
    ("像是在", "AI模糊比拟"),
    # === 冗余解释 ===
    ("这意味着", "AI总结句式"),
    ("也就是说", "AI解释句式"),
    ("某种程度上", "AI解释句式"),
    ("某种意义上", "AI解释句式"),
    ("不是因为他", "AI过度解释"),
    ("而是因为", "AI过度解释"),
    # === 时间锚点（AI 堆砌"在这一刻/此刻"） ===
    ("这一刻", "AI时间锚点"),
    ("就在此时", "AI时间锚点"),
    ("就在此刻", "AI时间锚点"),
    ("就在这时", "AI时间锚点"),
    # === 意图/动作副词（AI 画蛇添足） ===
    ("试图", "AI意图副词"),
    ("表示", "AI意图副词"),
    ("缓缓地", "AI动作副词"),
    ("轻轻地", "AI动作副词"),
    ("慢慢地", "AI动作副词"),
    ("深深地", "AI程度副词"),
    # === 感官公式化 ===
    ("感到一种", "AI感官套话"),
    ("听见自己的", "AI感官套话"),
    ("看见自己的", "AI感官套话"),
]

# 短句最小长度（太短的不值得改写）
_MIN_SENTENCE_LEN = 12


def _extract_sentence(text: str, pos: int) -> tuple[int, int, str]:
    """从关键词位置提取所在整句的起止位置和内容。"""
    # 往前找句首
    start = pos
    while start > 0:
        c = text[start - 1]
        if c in "。！？\n":
            break
        start -= 1
    # 跳过句首空白/标点
    while start < pos and text[start] in "，。！？\n\r\t ":
        start += 1
    # 往后找句尾
    end = pos
    while end < len(text):
        c = text[end]
        if c in "。！？\n":
            end += 1  # 包含句尾标点
            break
        end += 1
    sentence = text[start:end].strip()
    return start, end, sentence


def scan_fingerprint_sentences(text: str) -> list[dict]:
    """扫描正文，返回命中 AI 指纹的句子列表。

    返回: [{start, end, sentence, reason}, ...]
    """
    hits = []
    seen_ranges: list[tuple[int, int]] = []  # 防止同一句子被多个关键词重复命中

    for keyword, category in _SCAN_KEYWORDS:
        pos = 0
        while True:
            pos = text.find(keyword, pos)
            if pos == -1:
                break
            start, end, sentence = _extract_sentence(text, pos)
            if len(sentence) < _MIN_SENTENCE_LEN:
                pos = end
                continue
            # 去重：同一句子最多报一次
            if any(abs(r[0] - start) < 10 for r in seen_ranges):
                pos = end
                continue
            seen_ranges.append((start, end))
            hits.append({
                "start": start,
                "end": end,
                "sentence": sentence,
                "reason": category,
            })
            pos = end
    # 按位置排序
    hits.sort(key=lambda h: h["start"])
    return hits


# "不是A，（而）是B" 扫描：覆盖三种写法
#   1) 不是A，是B / 不是A。是B   （标点分隔）
#   2) 不是A，而是B              （标点+而）
#   3) 不是A而是B                （无标点，必须有"而"，否则会误伤"不是这样的是…"）
_NOT_A_BUT_B_RE = re.compile(
    r"不是[^。！？\n]{1,25}?(?:[，。]\s*(?:而)?是|而是)[^。！？\n]{1,60}"
)


def _scan_not_a_but_b(text: str, existing_hits: list[dict]) -> list[dict]:
    """扫描「不是A，而是B」句式。全章 > 4 次时，第 5 次及以后标记为需改写。"""
    matches = []
    for m in _NOT_A_BUT_B_RE.finditer(text):
        start, end = m.start(), m.end()
        sentence = text[start:end].strip()
        # "不是A是B" 句式天然较短，降低最小长度阈值
        if len(sentence) >= 6:
            matches.append({"start": start, "end": end, "sentence": sentence})

    # 提示词已明确禁止「不是A是B」句式，残留一处就改一处——threshold=0，全标记，一个不留
    threshold = 0
    if len(matches) <= threshold:
        return []

    # 标记第 threshold+1 及以后的（去重）
    extra_hits = []
    seen = {(h["start"], h["end"]) for h in existing_hits}
    for m in matches[threshold:]:  # 跳过前 threshold 个，只标记超出的
        key = (m["start"], m["end"])
        if key not in seen:
            seen.add(key)
            extra_hits.append({
                "start": m["start"],
                "end": m["end"],
                "sentence": m["sentence"],
                "reason": "AI句式密度过高-不是A是B",
            })
    return extra_hits


# 句式重复扫描：连续 3 句以上以同一人称代词开头
def _scan_repeated_subject(text: str, existing_hits: list[dict]) -> list[dict]:
    """扫描连续「她...她...她...」句式。连续 ≥3 句时，标记第 3 句及以后。"""
    # 手动拆句
    sentences = []
    buf = []
    for ch in text:
        buf.append(ch)
        if ch in "。！？\n":
            sent = "".join(buf).strip()
            if sent:
                sentences.append(sent)
            buf = []
    if buf:
        sent = "".join(buf).strip()
        if sent:
            sentences.append(sent)

    # 找连续同代词开头块
    pronoun_runs = []  # [(start_idx, end_idx, pronoun)]
    i = 0
    while i < len(sentences):
        s = sentences[i]
        first_char = s[0] if s else ""
        if first_char not in "他她它":
            i += 1
            continue
        j = i + 1
        while j < len(sentences) and sentences[j] and sentences[j][0] == first_char:
            j += 1
        if j - i >= 3:
            pronoun_runs.append((i, j, first_char))
        i = j

    if not pronoun_runs:
        return []

    # 构建位置映射：句子 → 原文位置
    sent_positions = []
    pos = 0
    for s in sentences:
        start = text.find(s, pos)
        if start == -1:
            sent_positions.append((pos, pos + len(s)))
            pos += len(s)
        else:
            sent_positions.append((start, start + len(s)))
            pos = start + len(s)

    extra_hits = []
    seen = {(h["start"], h["end"]) for h in existing_hits}
    for start_i, end_i, pronoun in pronoun_runs:
        for k in range(start_i + 2, end_i):  # 第 3 句及以后
            sp = sent_positions[k]
            key = (sp[0], sp[1])
            if key not in seen:
                seen.add(key)
                extra_hits.append({
                    "start": sp[0],
                    "end": sp[1],
                    "sentence": sentences[k],
                    "reason": f"句式重复-连续{end_i-start_i}句'{pronoun}'开头",
                })
    return extra_hits


# AI 节奏套路：连续的否定/祈使短句排比（"没有X。没有Y。""不需要X。不需要Y。""不是X。是Y。"）
# 这类句式偶尔用一次有冲击力，连续 2 句以上即沦为 AI 节奏腔。
_NEG_PARALLEL_PATTERNS = [
    re.compile(rf"^(?:没有|无)[^。！？\n]{{1,12}}[。！？]"),      # 没有预警。/ 无声。
    re.compile(rf"^(?:不需要?|不用|不必)[^。！？\n]{{1,12}}[。！？]"),  # 不需要语言。/ 不用翅膀。
    re.compile(rf"^不是[^。！？\n]{{1,12}}[。！？]"),             # 不是死。
    re.compile(rf"^是[^。！？\n]{{1,12}}[。！？]"),               # 是活。（承接上一句"不是…"）
]


def _scan_negation_parallel(text: str, existing_hits: list[dict]) -> list[dict]:
    """扫描连续的否定/祈使短句排比。

    连续 2 句以上匹配套路句式（不论是否同前缀），整组（除第一句外）标记改写。
    例：
      "没有预警。\n没有前摇。" → 第 2 句标记
      "不需要语言。\n不需要翅膀。" → 第 2 句标记
    短句阈值：单句 ≤14 字才算"断句套路"（长句不算）。
    """
    # 手动拆句（与 _scan_repeated_subject 一致）
    sentences = []
    buf = []
    for ch in text:
        buf.append(ch)
        if ch in "。！？\n":
            sent = "".join(buf).strip()
            if sent:
                sentences.append(sent)
            buf = []
    if buf:
        sent = "".join(buf).strip()
        if sent:
            sentences.append(sent)

    # 找出哪些句子是"套路短句"
    flagged_idx = []
    for i, s in enumerate(sentences):
        if len(s) > 14:  # 长句不算断句套路
            continue
        if any(p.search(s) for p in _NEG_PARALLEL_PATTERNS):
            flagged_idx.append(i)

    if len(flagged_idx) < 2:
        return []

    # 找连续段（相邻或间隔 ≤1）：连续 2+ 个 flagged 句算一组套路
    groups = []
    cur = [flagged_idx[0]]
    for i in range(1, len(flagged_idx)):
        if flagged_idx[i] - flagged_idx[i - 1] <= 2:
            cur.append(flagged_idx[i])
        else:
            if len(cur) >= 2:
                groups.append(cur)
            cur = [flagged_idx[i]]
    if len(cur) >= 2:
        groups.append(cur)

    if not groups:
        return []

    # 构建位置映射
    sent_positions = []
    pos = 0
    for s in sentences:
        start = text.find(s, pos)
        if start == -1:
            sent_positions.append((pos, pos + len(s)))
            pos += len(s)
        else:
            sent_positions.append((start, start + len(s)))
            pos = start + len(s)

    extra_hits = []
    seen = {(h["start"], h["end"]) for h in existing_hits}
    for group in groups:
        # 整组连起来作为一条改写（带前一句作为完整上下文），第一句保留、其后标记
        # 把整组拼成一个区间交给模型改写，避免改完前后不连贯
        g_start = sent_positions[group[0]][0]
        g_end = sent_positions[group[-1]][1]
        key = (g_start, g_end)
        if key not in seen:
            seen.add(key)
            joined = "".join(sentences[i] for i in group)
            extra_hits.append({
                "start": g_start,
                "end": g_end,
                "sentence": joined,
                "reason": "AI节奏套路-否定/祈使短句排比",
            })
    return extra_hits


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
) -> list[dict] | None:
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
        "特殊处理1：「不是A，是B」句式改成直接陈述。\n"
        "  例：「不是矿道，是裂隙」→「矿道裂成了一条向下的裂隙」\n"
        "  例：「不是消失，是变形」→「轮廓正在变形」\n"
        "特殊处理2：连续的否定/祈使短句排比（如「没有预警。没有前摇。」「不需要语言。不需要翅膀。」）"
        "是 AI 节奏腔，合并改写成一句自然的陈述，保留冲击力但去掉排比套路。\n"
        "  例：「没有预警。没有前摇。」→「连个预警都没有。」\n"
        "  例：「不需要语言。不需要翅膀。」→「语言和翅膀此刻都是多余。」\n"
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
def _validate_rewrite(original: str, rewritten: str, kind: str = "normal") -> bool:
    """四道闸：空值/长度变化>50%/专名丢失/无变化 → False（不通过）。

    kind:
      - "normal"（默认）：普通指纹句改写，严格校验。
      - "rewrite"：句式重写类（如"不是A是B"），改写本身就会改变长度和用词，
        放宽长度限制到 0.3-2.5，并跳过专名检测（重写后通常没有原句的词）。
    """
    if not rewritten or not rewritten.strip():
        return False
    # 无变化
    if rewritten.strip() == original.strip():
        return False
    # 长度变化
    orig_len = len(original.strip())
    new_len = len(rewritten.strip())
    if orig_len > 0:
        ratio = new_len / orig_len
        if kind == "rewrite":
            # 句式重写会改变长度，放宽到 0.3-2.5
            if ratio < 0.3 or ratio > 2.5:
                return False
        else:
            # 普通改写：长度变化不超过 50%
            if ratio < 0.5 or ratio > 1.5:
                return False
    # 专名检测：原句中的 2~4 字连续中文词（粗略），改写后不应全丢
    # 句式重写类（rewrite）跳过此项——重写后通常不再保留原句的字面用词，
    # 专名检测会把合理的改写误判为"丢信息"。
    if kind != "rewrite":
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
    # 1b. "不是A，是B" 扫描（提示词已禁，残留一处改一处，threshold=0）
    not_a_but_b_hits = _scan_not_a_but_b(text, hits)
    if not_a_but_b_hits:
        logger.warning(f"[rewrite] 「不是A是B」残留: 标记 {len(not_a_but_b_hits)} 句改写")
        hits.extend(not_a_but_b_hits)
        hits.sort(key=lambda h: h["start"])
    # 1c. 句式重复扫描（连续 "她...她...她..."）
    repeated_subject_hits = _scan_repeated_subject(text, hits)
    if repeated_subject_hits:
        logger.warning(f"[rewrite] 句式重复: 标记 {len(repeated_subject_hits)} 句改写")
        hits.extend(repeated_subject_hits)
        hits.sort(key=lambda h: h["start"])
    # 1d. 否定/祈使短句排比扫描（"没有预警。没有前摇。""不需要语言。不需要翅膀。"）
    neg_parallel_hits = _scan_negation_parallel(text, hits)
    if neg_parallel_hits:
        logger.warning(f"[rewrite] 否定/祈使短句排比: 标记 {len(neg_parallel_hits)} 处改写")
        hits.extend(neg_parallel_hits)
        hits.sort(key=lambda h: h["start"])
    if not hits:
        logger.warning("[rewrite] 未命中任何 AI 指纹句，跳过 API 调用（无请求发出）")
        return text, {"命中": 0}

    # 2. 加上下文
    for h in hits:
        prev, nxt = _extract_context(text, h["start"], h["end"])
        h["ctx_prev"] = prev
        h["ctx_next"] = nxt

    logger.warning(f"[rewrite] 扫描到 {len(hits)} 个指纹句，准备调 API")

    # 3. 调 API
    results = await _call_rewrite_api(base_url, api_key, model, hits)
    if results is None:
        return text, {"命中": len(hits), "API失败": True}

    # 4. 回填 + 四道闸
    rewritten_count = 0
    skipped = 0
    # 从后往前替换，避免位置偏移
    replacements = []
    # 句式重写类 reason：这些是改变句式的改写，走宽松校验
    _REWRITE_REASONS = {"AI句式密度过高-不是A是B", "AI节奏套路-否定/祈使短句排比"}
    for r in results:
        idx = r.get("i")
        new_text = r.get("t", "")
        if idx is None or idx >= len(hits):
            continue
        hit = hits[idx]
        original = hit["sentence"]
        # "不是A是B" 等句式重写走宽松闸，避免合理的改写被长度/专名检测误杀
        kind = "rewrite" if hit.get("reason") in _REWRITE_REASONS else "normal"
        if _validate_rewrite(original, new_text, kind=kind):
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
