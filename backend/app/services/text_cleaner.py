"""AI 生成正文的后处理管道：多层流水线去 AI 指纹。

设计原则：
  - 会改变剧情信息的规则 → 不自动删，只统计
  - 削弱 AI 套话/连接词/重复表达 → 自动处理
  - 低频词不动，超阈值才降频

模式：
  safe      — 只做安全替换（词级 + 统计）
  normal    — 安全 + 句式变换（默认）
  aggressive — 全部启用，含叙事去重
"""

import re
from collections import Counter
from dataclasses import dataclass, field

_R = r"[他她它]"


@dataclass
class CleanResult:
    cleaned_text: str
    stats: dict = field(default_factory=dict)


# ====================================================================
# 第一层：Lexical（词级）— 仅替换不删除，避免改变语义强度
# ====================================================================
LEXICAL_SAFE: list[tuple[str, str]] = [
    # 注意："突然/忽然/骤然/猛地/瞬间" 不在这里无条件删除——
    # 它们有时承载节奏转折（"脚步猛地快了"/"婴儿突然又哭了"），一刀切会误伤。
    # 改为交给第四层频率统计：一章内超阈值才删多余的，前几次保留。
    # "某种/一种/一丝/一缕" → 删
    (r"某种([^，。；]{1,10})", r"\1"),
    (r"一种([^，。；]{1,10})", r"\1"),
    (r"一丝([^，。；]{1,10})", r"\1"),
    (r"一缕([^，。；]{1,10})", r"\1"),
    # "显得" → 删
    (r"显得([^，。；]{1,15})", r"\1"),
]

LEXICAL_NORMAL: list[tuple[str, str]] = [
    # "甚至" → 删
    (r"[，]?甚至[，]?", "，"),
    # "像是" → "像"
    (r"像是([一一一个只条根片阵股把张座])", r"像\1"),
]

LEXICAL_AGGRESSIVE: list[tuple[str, str]] = [
    # "几乎" → 删（aggressive 才做，safe/normal 只统计）
    (r"[，]?几乎[，]?", ""),
    # "完全" → 删（aggressive 才做）
    (r"完全([^，。]{2,8})", r"\1"),
    # "整个" → "整"（可能不自然，aggressive 才做）
    (r"整个([^，。]{1,8})", r"整\1"),
]


# ====================================================================
# 第二层：Pattern（句式）— 识别并缩短 AI 句式
# ====================================================================
PATTERNS_SAFE: list[tuple[str, str]] = [
    # "不是A，而是B" → 只保留 B
    (r"不是([^，。；]{2,20})[，。]*而是\s*([^，。]{2,50})", r"\2"),
    (r"并不是([^，。；]{2,20})[，。]*而是\s*([^，。]{2,50})", r"\2"),
    # "直到这一刻/这一瞬/现在" → 删
    (r"(?:^|[，。])\s*直到(?:这一刻|这一瞬|现在|此时)[，。]?", "."),
    # "那一刻/这一瞬/这一刻" → 删
    (r"(?:^|[，。])\s*(?:那一刻|这一瞬|这一刻)[，。]?", ""),
    # 引语前缀 → 删
    (rf"{_R}开口[，。]", ""),
    # "不是比喻" → 删
    (r"不是比喻[，。]", ""),
    # "现在不是X的时候" → 删
    (r"现在不是(?:回忆|感慨|犹豫|害怕)的时候[，。]", ""),
    # 逻辑连接词 → 删（真人写作很少用）
    (r"(?:^|[，。])\s*因此[，]?", "。"),
    (r"(?:^|[，。])\s*于是[，]?", "。"),
    (r"(?:^|[，。])\s*所以[，]?", "。"),
    (r"(?:^|[，。])\s*因为[，]?", "。"),
    (r"(?:^|[，。])\s*然而[，]?", "。"),
    (r"(?:^|[，。])\s*继而[，]?", "。"),
    # "XX地" 副词结构 → 删掉副词（慢慢地、轻轻地、冷冷地 等）
    # ⚠️ 只删"动词/形容词+地+动词"这种副词结构，不删名词性的"地"
    # 错误示例（不能删）：磨得地砖、一地的、地上、地面
    # 正确示例（应该删）：慢慢地说、轻轻地走、冷冷地看
    # 用白名单方式：列出要删的常见副词，避免误伤
    (r"(?:慢慢地|轻轻地|悄悄地|默默地|静静地|冷冷地|淡淡地|缓缓地|微微地|渐渐})", ""),
    # "两个人都X" → "两人X"
    (r"两个人(?:都|同时)(.{2,20})", r"两人\1"),
]

PATTERNS_NORMAL: list[tuple[str, str]] = [
    # "这意味着/这说明/这代表" → 删整句
    (r"[，。]这(?:意味着|说明|代表|表示)[^。]{5,40}[。]", "。"),
    # 感官声明 → 删
    (rf"{_R}(?:感觉得到|感觉到|能感到)[，。]", ""),
    # 叙事捷径 → 删
    (rf"{_R}当然知道[。，]", ""),
    # "仿佛" → "像"
    (r"仿佛连([^，。]{3,20})", r"像连\1"),
    (r"仿佛整个([^，。]{3,20})", r"像整个\1"),
    (r"仿佛([^，。]{2,20})", r"像\1"),
    # "像是" → "像"
    (r"像是([^，。]{2,25})", r"像\1"),
]

PATTERNS_AGGRESSIVE: list[tuple[str, str]] = [
    # "不是因为X——而是因为Y" → "因为Y"
    (r"不是因为(.{2,20})[，。]*而是因为\s*([^，。]{2,50})", r"因为\2"),
    # "现在不是X的时候"
    (r"现在不是(?:回忆|感慨|犹豫|害怕)的时候[，。]", ""),
]


# ====================================================================
# 同义词轮换池
# ====================================================================
_BODY_PATTERNS: list[tuple[re.Pattern, list[str]]] = []
_body_counts: dict[str, int] = {}

_BODY_TRIGGERS: dict[str, list[str]] = {
    "打了个冷战":   ["后颈一紧", "尾椎一麻", "肩胛一僵"],
    "打了个颤":     ["小臂绷紧", "虎口发麻", "指尖发凉"],
    "指节发白":     ["指节泛青", "虎口发麻", "指尖用力"],
    "呼吸一滞":     ["呼吸顿住", "喉头发紧", "胸口一闷"],
    "心跳漏了一拍": ["心跳重了一拍", "太阳穴一跳", "胃里一沉"],
    "喉结滚动":     ["喉头微动", "咽了一下", "喉间一紧"],
    "瞳孔微缩":     ["瞳孔一敛", "目光收紧", "眼神一闪"],
    "后背发凉":     ["脊背一寒", "背脊绷紧", "后颈一麻"],
    "头皮发麻":     ["头皮一紧", "颅顶发凉", "发根倒竖"],
    "太阳穴突突直跳": ["太阳穴一胀", "额角一跳", "鬓边发紧"],
}


def _rotate_body_word(match: re.Match) -> str:
    raw = match.group(0)
    # 去掉尾随的"了一下/了起来/了一下子/了/着"等
    suffix = ""
    raw_stripped = re.sub(r"(?:了一[下子]|了起[来]|了一下子|[了着])$", "", raw)
    if raw_stripped != raw:
        suffix = raw[len(raw_stripped):]
    raw = raw_stripped
    key = re.sub(rf"^{_R}", "", raw)
    for pat, pool in _BODY_PATTERNS:
        if pat.fullmatch(raw):
            idx = _body_counts.get(key, 0) % len(pool)
            _body_counts[key] = _body_counts.get(key, 0) + 1
            replacement = pool[idx]
            # 替换词若以"动"等动词结尾，suffix 里的"了"可接；但避免"一动了"
            if suffix and suffix.startswith("了") and replacement.endswith("动"):
                suffix = ""
            return replacement + suffix
    return match.group(0)


def _init_body_patterns():
    _BODY_PATTERNS.clear()
    for trigger, pool in _BODY_TRIGGERS.items():
        pat = re.compile(rf"(?:{_R})?{re.escape(trigger)}")
        _BODY_PATTERNS.append((pat, pool))


def _reset_body_counts():
    _body_counts.clear()


_init_body_patterns()

# ====================================================================
# 第三层：Narrative（叙事模式）— 连续同类项去重
# ====================================================================
def _dedupe_consecutive_likes(text: str) -> str:
    """连续比喻去重：2 段留 1，3+ 段只留最后一段。
    只匹配句首或逗号后的"像"，不匹配"画像/雕像/像素/好像"。"""
    lines = text.split("\n")
    like_streak = 0
    like_indices = []
    for i, line in enumerate(lines):
        # 只匹配句首或逗号后的"像"（比喻），排除"画像/雕像/像素/好像"
        if re.match(r"^(?:[，。]?\s*|[^，。]{0,3}[，。]\s*)像", line) and "好像" not in line[:5]:
            like_streak += 1
            like_indices.append(i)
        else:
            if like_streak >= 3:
                for j in like_indices[:-1]:
                    lines[j] = ""
            elif like_streak == 2:
                lines[like_indices[0]] = ""
            like_streak = 0
            like_indices = []
    if like_streak >= 3:
        for j in like_indices[:-1]:
            lines[j] = ""
    elif like_streak == 2:
        lines[like_indices[0]] = ""
    return "\n".join(line for line in lines if line.strip() or line == "")


def _dedupe_consecutive_negations(text: str) -> str:
    """连续'X没有Y'句式 → 只保留第一个。"""
    return re.sub(
        rf"({_R}没有[^。]{{5,40}}[。])\s*({_R}没有[^。]{{5,40}}[。])",
        r"\1",
        text,
    )


def _dedupe_consecutive_psych(text: str) -> dict:
    """检测连续心理说明句（意识到/发现/知道/明白/觉得），返回统计。"""
    pattern = rf"({_R}(?:意识到|发现|知道|明白|觉得|认为)[^。]{{3,60}}[。])"
    matches = [m.group(1) for m in re.finditer(pattern, text)]
    streaks = []
    streak = 0
    for i in range(len(matches)):
        if i > 0 and text.index(matches[i]) - text.index(matches[i - 1]) < 800:
            streak += 1
        else:
            if streak >= 3:
                streaks.append(streak)
            streak = 1
    if streak >= 3:
        streaks.append(streak)
    return {"count": len(matches), "max_streak": max(streaks) if streaks else 0}


# ====================================================================
# 第四层：Statistics（频率统计）— 超阈值才降频
# ====================================================================
_STATS_THRESHOLD: dict[str, int] = {
    "仿佛": 5,  "似乎": 5,  "好像": 5,  "像是": 5,
    "几乎": 5,  "完全": 4,  "彻底": 3,  "整个": 4,
    "无比": 3,  "前所未有": 1, "突然": 5, "忽然": 5,
    "甚至": 6,  "意识到": 6, "发现": 8,  "试图": 5,
    "表示": 5,  "那一刻": 3, "这一瞬": 3, "这一刻": 3,
}

_STATS_REPLACEMENTS: dict[str, str] = {
    "仿佛": "像",   "似乎": "像",   "好像": "像",   "像是": "像",
    "几乎": "",      "完全": "",     "彻底": "",     "整个": "整",
    "无比": "极",   "前所未有": "", "突然": "",     "忽然": "",
    "甚至": "",      "那一刻": "",  "这一瞬": "",   "这一刻": "",
}


def _apply_stats(text: str) -> tuple[str, dict]:
    """统计高频 AI 词，超阈值时按比例替换。返回 (cleaned_text, stats_report)。"""
    report = {}
    for word, threshold in _STATS_THRESHOLD.items():
        # 用 finditer 避免匹配子串（"像"不匹配"画像/雕像/像素"）
        pattern = re.compile(rf"(?<!\w){re.escape(word)}(?!\w)")
        matches = list(pattern.finditer(text))
        count = len(matches)
        report[word] = count
        if count <= threshold:
            continue
        replacement = _STATS_REPLACEMENTS.get(word, "")
        kept = 0
        def _replace(m, _threshold=threshold, _replacement=replacement):
            nonlocal kept
            kept += 1
            if kept <= _threshold:
                return m.group(0)
            return _replacement
        text = pattern.sub(_replace, text)
    return text, report


def _strip_xml_like_tags(text: str) -> tuple[str, int]:
    """移除 DSML/XML 风格的工具调用标签及内容，防止泄漏到正文。

    策略：先移除完整标签对（含嵌套内容），再清理残留的孤立标签。
    返回 (cleaned_text, removed_count)
    """
    removed = 0

    # ---- Pass 1: 完整标签对（含内容） ----
    # DSML invoke 块：<｜DSML｜invoke ...> ... </｜DSML｜invoke>
    dsml_invoke = re.compile(
        r"<[｜\|]DSML[｜\|]invoke\b[^>]*>.*?</[｜\|]DSML[｜\|]invoke\s*>",
        re.DOTALL,
    )
    while dsml_invoke.search(text):
        text, n = dsml_invoke.subn("", text)
        removed += n
        if n == 0:
            break

    # DSML parameter 块：<｜DSML｜parameter ...> ... </｜DSML｜parameter>
    dsml_param = re.compile(
        r"<[｜\|]DSML[｜\|]parameter\b[^>]*>.*?</[｜\|]DSML[｜\|]parameter\s*>",
        re.DOTALL,
    )
    while dsml_param.search(text):
        text, n = dsml_param.subn("", text)
        removed += n
        if n == 0:
            break

    # Kimi tool_call 完整块
    kimi_tool = re.compile(
        r"<\|tool_call_begin\|>.*?<\|tool_call_end\|>",
        re.DOTALL,
    )
    text, n = kimi_tool.subn("", text)
    removed += n

    # Kimi section 完整块
    kimi_section = re.compile(
        r"<\|tool_calls_section_begin\|>.*?<\|tool_calls_section_end\|>",
        re.DOTALL,
    )
    text, n = kimi_section.subn("", text)
    removed += n

    # DSML tool_calls 最外层（兜底）
    dsml_outer = re.compile(
        r"<[｜\|]DSML[｜\|]tool_calls\s*>.*?</[｜\|]DSML[｜\|]tool_calls\s*>",
        re.DOTALL,
    )
    while dsml_outer.search(text):
        text, n = dsml_outer.subn("", text)
        removed += n
        if n == 0:
            break

    # ---- Pass 2: 孤立标签（无内容或已拆散的标签碎片） ----
    _TOOL_TAG = re.compile(
        r"</?[｜\|]DSML[｜\|][^>]*/?>|"         # DSML 孤立标签
        r"</?\|tool_call[^>]*\|>|"              # Kimi tool_call 标签
        r"</?\|tool_calls_section[^>]*\|>",     # Kimi section 标签
    )
    text, n = _TOOL_TAG.subn("", text)
    removed += n

    # ---- 清理残留 ----
    text = re.sub(r"\n{3,}", "\n\n", text)
    # 删除纯空白行开头/结尾
    text = text.strip()

    return text, removed


# ====================================================================
# 主清理函数
# ====================================================================
def _dedupe_repeated_paragraphs(text: str) -> tuple[str, dict]:
    """检测并删除连续重复的大段文字（AI 偶尔会复制粘贴整段）。
    策略：按空行分段，检测相邻段是否高度相似（>80% 相同）。"""
    paragraphs = re.split(r"\n\s*\n", text)
    if len(paragraphs) < 2:
        return text, {}
    kept = []
    removed = 0
    for para in paragraphs:
        para_stripped = para.strip()
        if not para_stripped:
            kept.append(para)
            continue
        # 和上一段比对
        is_dup = False
        if kept:
            prev = kept[-1].strip()
            if prev and len(prev) > 30:
                # 取两段较短的那个长度的 80% 作为阈值
                min_len = min(len(prev), len(para_stripped))
                _threshold = min_len * 0.8
                # 简单方法：短段是否是长段的子串，或长段包含短段 80% 的字符
                if para_stripped in prev or prev in para_stripped:
                    is_dup = True
                elif _text_similarity(prev, para_stripped) > 0.8:
                    is_dup = True
        if is_dup:
            removed += 1
        else:
            kept.append(para)
    result = "\n\n".join(kept)
    stats = {"删除重复段落": removed} if removed else {}
    return result, stats


def _text_similarity(a: str, b: str) -> float:
    """简单相似度：公共字符占比（Jaccard 系数，基于 3-gram）。"""
    def _grams(s):
        return set(s[i:i+3] for i in range(max(0, len(s) - 2)))
    ga, gb = _grams(a), _grams(b)
    if not ga or not gb:
        return 0.0
    return len(ga & gb) / len(ga | gb)


def clean_generated_text(text: str, mode: str = "normal") -> CleanResult:
    """对 AI 生成的正文执行多层清理管道。

    mode: safe | normal | aggressive
    """
    if not text:
        return CleanResult(cleaned_text=text, stats={})

    _reset_body_counts()
    stats_report: dict = {}

    # ---- 第负一层：移除 DSML/XML 工具调用标签（安全网） ----
    text, xml_removed = _strip_xml_like_tags(text)
    if xml_removed:
        stats_report["移除工具调用标签"] = xml_removed

    # ---- 第零层：删除连续重复段落（最严重的硬伤，先于一切处理） ----
    text, dup_stats = _dedupe_repeated_paragraphs(text)
    stats_report.update(dup_stats)

    # ---- 第一层：Lexical ----
    for pattern, replacement in LEXICAL_SAFE:
        text = re.sub(pattern, replacement, text)
    if mode in ("normal", "aggressive"):
        for pattern, replacement in LEXICAL_NORMAL:
            text = re.sub(pattern, replacement, text)
    if mode == "aggressive":
        for pattern, replacement in LEXICAL_AGGRESSIVE:
            text = re.sub(pattern, replacement, text)

    # ---- 第二层：Pattern ----
    for pattern, replacement in PATTERNS_SAFE:
        text = re.sub(pattern, replacement, text)
    if mode in ("normal", "aggressive"):
        for pattern, replacement in PATTERNS_NORMAL:
            text = re.sub(pattern, replacement, text)
    if mode == "aggressive":
        for pattern, replacement in PATTERNS_AGGRESSIVE:
            text = re.sub(pattern, replacement, text)

    # ---- 第三层：Narrative ----
    if mode == "aggressive":
        text = _dedupe_consecutive_likes(text)
        text = _dedupe_consecutive_negations(text)
    psych = _dedupe_consecutive_psych(text)
    if psych["max_streak"] >= 3:
        stats_report["连续心理说明"] = f"×{psych['max_streak']}（共计{psych['count']}次）"

    for pat, _ in _BODY_PATTERNS:
        text = pat.sub(_rotate_body_word, text)
    rotated = sum(1 for v in _body_counts.values() if v > 0)
    if rotated:
        stats_report["身体反应轮换"] = rotated

    # ---- 第四层：Statistics ----
    text, freq_report = _apply_stats(text)
    for word, count in freq_report.items():
        threshold = _STATS_THRESHOLD.get(word, 999)
        if count > threshold:
            stats_report[word] = f"{count}→{threshold}"

    # ---- 残留清理 ----
    text = re.sub(r"，{2,}", "，", text)
    text = re.sub(r"。{2,}", "。", text)
    text = re.sub(r" {2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"——{2,}", "——", text)
    text = re.sub(r"^\s*[，。]", "", text, flags=re.MULTILINE)

    return CleanResult(cleaned_text=text.strip(), stats=stats_report)
