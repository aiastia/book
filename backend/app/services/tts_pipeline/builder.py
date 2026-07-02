"""
SSML Builder —— 把 Director 指令 + 配置拼成 Azure 合法 SSML。

设计原则（针对中文小说朗读）:
  1. express-as 管场景氛围 —— 段级,由 scene_change 决定,同一场景内不切换
  2. prosody 管角色特征 —— 句级,rate/pitch 微调,幅度保守(中文大幅变调会不自然)
  3. emphasis 管关键时刻 —— 句级,只有情绪强烈的台词才加,旁白不加

三者分层,不互相覆盖,避免"层层叠加"导致的虚假感。
"""
import os
import re
from typing import List, Dict, Optional, Tuple

import yaml

from app.core.config import settings
from .models import DirectorLine, SceneChange, VoiceParams, DirectorOutput


# Azure TTS 单次请求建议的文本字符数上限
MAX_TEXT_CHARS_PER_REQUEST = 3000

# 默认配置文件路径
_CONFIG_DIR = os.path.join(settings.DATA_DIR, "tts_config")
_DEFAULT_CHARACTERS_PATH = os.path.join(_CONFIG_DIR, "characters.yaml")
_DEFAULT_SCENES_PATH = os.path.join(_CONFIG_DIR, "scenes.yaml")

# ===== 场景 → express-as style 映射（内置,不放在 YAML 里避免用户配错）=====
# 每个场景名直接对应一个 Azure express-as style,切换时变更,持续生效。
# 中文 Azure  voices 支持的 style: calm, cheerful, sad, angry, fearful,
#   serious, depressed, gentle, empathetic, serene, affectionate, embarrassed, envious
_SCENE_STYLE_MAP: Dict[str, str] = {
    "calm":    "calm",
    "night":   "calm",
    "suspense": "serious",
    "battle":  "angry",
    "chase":   "serious",
    "sad":     "sad",
    "comedy":  "cheerful",
    "default": "calm",
}

# ===== 情绪 → 默认强调级别 映射 =====
# 根据中文情绪标签的强度,决定 emphasis 级别。
# "无强调"的情绪(平静/温柔/冷淡等)不输出 emphasis 标签,避免每句都加。
_EMOTION_EMPHASIS_MAP: Dict[str, Optional[str]] = {
    # strong — 强烈情绪,必须强调
    "愤怒": "strong", "暴怒": "strong", "狂怒": "strong",
    "惊恐": "strong", "恐惧": "strong", "尖叫": "strong",
    # moderate — 中等情绪,适度强调
    "悲伤": "moderate", "哀伤": "moderate", "痛苦": "moderate",
    "严肃": "moderate", "郑重": "moderate",
    "沮丧": "moderate", "消沉": "moderate",
    "温柔": "moderate", "亲切": "moderate", "和蔼": "moderate",
    "同情": "moderate", "怜悯": "moderate",
    "兴奋": "moderate", "高兴": "moderate",
    "尴尬": "moderate", "窘迫": "moderate",
    "虚弱": "moderate", "慵懒": "moderate",
    # none — 平静/中性情绪,不加 emphasis
    "平静": None, "安宁": None, "冷静": None,
    "冷淡": None, "冷漠": None, "客观": None,
    "慈爱": None, "宠爱": None, "羡慕": None, "嫉妒": None,
}

# Azure express-as style 白名单
_VALID_EXPRESS_AS_STYLES = {
    "chat", "customerservice", "cheerful", "sad", "angry",
    "fearful", "serious", "newscast", "depressed", "gentle",
    "poetry-reading", "lyrical", "empathetic", "calm",
    "affectionate", "embarrassed", "envious", "serene",
}

# ---- 内置默认配置（首次运行或 Docker 环境自动写入）----
_DEFAULT_CHARACTERS_YAML = """\
# 角色映射配置 ─ speaker(由 Director 分析产出)→ 语音参数
# 字段说明:
#   rate/pitch: prosody 属性值,统一用百分比(避免 dB 坑)。
#               ★ 注意:中文 TTS 的 rate 建议在 -10% ~ +10% 之间,
#               超出范围会听起来不自然(太慢像卡壳,太快像机关枪)。
#   style:      express-as 的 style,如 calm/gentle/sad。
#               ★ 注意:段级 style 由 scene_change 决定,角色的 style
#               仅在场景没有默认 style 时作为兜底。
#   emphasis:   强调级别(strong/moderate/none), 覆盖角色默认。
#               默认 none,只有特定角色(如战斗狂)才设为 strong。
#   volume:     prosody volume,如 soft/loud/x-loud/medium。
Narrator:
  rate: "-2%"
  pitch: "0%"
  style: null
  emphasis: "none"
  volume: null
Messenger:
  rate: "-8%"
  pitch: "-2%"
  style: null
  emphasis: "none"
  volume: null
KailanWeak:
  rate: "-10%"
  pitch: "-3%"
  style: null
  emphasis: "none"
  volume: null
KailanCalm:
  rate: "-5%"
  pitch: "-1%"
  style: null
  emphasis: "none"
  volume: null
Servant:
  rate: "-5%"
  pitch: "-2%"
  style: "gentle"
  emphasis: "none"
  volume: null
default:
  rate: "0%"
  pitch: "0%"
  style: null
  emphasis: "none"
  volume: null
"""

_DEFAULT_SCENES_YAML = """\
# 场景预设 ─ 场景名(Director 的 scene_change 产出)→ 语音参数 + 默认停顿
# ★ express-as style 由 scene_change 自动决定(见 _SCENE_STYLE_MAP),
#   不需要在这里配置 style。
# 角色的 rate/pitch 和场景的 rate/pitch 会叠加(Builder 负责相加)。
# pause 是该场景下句子之间的默认停顿(当 DirectorLine 没指定 pause_after 时使用)。
calm:
  rate: "-2%"
  pitch: "0%"
  pause: "600ms"
night:
  rate: "-3%"
  pitch: "0%"
  pause: "600ms"
suspense:
  rate: "-3%"
  pitch: "0%"
  pause: "700ms"
battle:
  rate: "+5%"
  pitch: "+2%"
  pause: "150ms"
chase:
  rate: "+8%"
  pitch: "+2%"
  pause: "120ms"
sad:
  rate: "-5%"
  pitch: "-2%"
  pause: "800ms"
comedy:
  rate: "+3%"
  pitch: "+3%"
  pause: "400ms"
default:
  rate: "0%"
  pitch: "0%"
  pause: "500ms"
"""


def _ensure_default_configs():
    """首次运行或 Docker 环境无配置文件时，自动写入内置默认配置。"""
    os.makedirs(_CONFIG_DIR, exist_ok=True)
    if not os.path.exists(_DEFAULT_CHARACTERS_PATH):
        with open(_DEFAULT_CHARACTERS_PATH, "w", encoding="utf-8") as f:
            f.write(_DEFAULT_CHARACTERS_YAML)
    if not os.path.exists(_DEFAULT_SCENES_PATH):
        with open(_DEFAULT_SCENES_PATH, "w", encoding="utf-8") as f:
            f.write(_DEFAULT_SCENES_YAML)


_ensure_default_configs()


def _load_yaml_params(path: str) -> Dict[str, VoiceParams]:
    """加载 YAML 配置文件为 {name: VoiceParams} 字典。"""
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return {name: VoiceParams(**params) for name, params in raw.items()}


def _parse_percent(value: str) -> float:
    """解析百分比字符串为浮点数。"""
    value = value.strip()
    if value.endswith("%"):
        return float(value[:-1])
    return float(value)


def _combine_prosody(char_params: VoiceParams, scene_params: VoiceParams) -> Tuple[str, str, Optional[str]]:
    """
    角色参数 + 场景参数相加,返回合并后的 (rate, pitch, volume)。
    ★ rate/pitch 叠加后 clamp 到 [-15%, +15%],防止中文 TTS 不自然。
    """
    rate = _parse_percent(char_params.rate) + _parse_percent(scene_params.rate)
    pitch = _parse_percent(char_params.pitch) + _parse_percent(scene_params.pitch)
    # clamp: 中文 TTS 超出 ±15% 会很不自然
    rate = max(-15, min(15, rate))
    pitch = max(-10, min(10, pitch))
    volume = char_params.volume or scene_params.volume or None
    # 格式化
    def fmt(v: float) -> str:
        v = round(v)
        if v == 0:
            return "0%"
        sign = "+" if v > 0 else ""
        return f"{sign}{v}%"
    return fmt(rate), fmt(pitch), volume


def _resolve_scene_style(scene: Optional[str]) -> Optional[str]:
    """
    根据场景名决定 express-as style。
    只认内置映射,不依赖 YAML 配置,避免用户配出非法值。
    """
    if not scene:
        return _SCENE_STYLE_MAP.get("default", "calm")
    return _SCENE_STYLE_MAP.get(scene, _SCENE_STYLE_MAP.get("default", "calm"))


def _resolve_emphasis(emotion: Optional[str], director_emphasis: Optional[str]) -> Optional[str]:
    """
    决定这一行是否需要 emphasis,以及级别。

    优先级:
      1. Director 显式指定的 emphasis（strong/moderate/none/reduced）
      2. 根据 emotion 标签推断（情绪强烈→strong, 中等→moderate, 平静→none）
      3. 默认 none

    ★ 原则:旁白(无情绪)一律不加 emphasis;只有台词+强烈情绪才加 strong。
    """
    _valid = {"strong", "moderate", "reduced"}
    # 1) Director 显式指定
    if director_emphasis and director_emphasis in _valid:
        return director_emphasis
    if director_emphasis == "none":
        return None
    # 2) 根据情绪推断
    if emotion:
        inferred = _EMOTION_EMPHASIS_MAP.get(emotion)
        if inferred and inferred in _valid:
            return inferred
    # 3) 默认不加
    return None


def _escape_xml_text(text: str) -> str:
    """转义正文里的 XML 特殊字符。"""
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    return text


def _build_prosody_tag(rate: str, pitch: str, volume: Optional[str], inner: str) -> str:
    """构建 <prosody> 标签,包含可选的 volume 属性。"""
    attrs = f'rate="{rate}" pitch="{pitch}"'
    if volume:
        attrs += f' volume="{volume}"'
    return f'<prosody {attrs}>{inner}</prosody>'


def _build_speak_shell(inner_content: str, voice: str, style: Optional[str]) -> str:
    """
    用 <speak><voice><express-as> 外壳包裹内容。
    ★ express-as 放在段级,同一段内所有行共享同一个 style。
    """
    parts = [
        '<speak version="1.0" '
        'xmlns="http://www.w3.org/2001/10/synthesis" '
        'xmlns:mstts="https://www.w3.org/2001/mstts" '
        f'xml:lang="zh-CN">',
        f'<voice name="{voice}">',
    ]
    if style and style in _VALID_EXPRESS_AS_STYLES:
        parts.append(f'<mstts:express-as style="{style}">')
    parts.append(inner_content)
    if style and style in _VALID_EXPRESS_AS_STYLES:
        parts.append('</mstts:express-as>')
    parts.extend(['</voice>', '</speak>'])
    return "\n".join(parts)


def _is_valid_prosody_output(ssml: str) -> Optional[str]:
    """兜底校验:确认 prosody 属性值合法。"""
    for match in re.finditer(r'<prosody\b[^>]*>', ssml, re.IGNORECASE):
        tag = match.group(0)
        for attr in ("volume", "rate", "pitch"):
            am = re.search(rf'{attr}\s*=\s*"([^"]*)"', tag, re.IGNORECASE)
            if not am:
                continue
            value = am.group(1)
            if re.fullmatch(r"[+-]?\d+%", value):
                continue
            if value in ("default", "medium", "silent", "x-soft", "soft",
                         "loud", "x-loud", "x-slow", "slow", "fast", "x-fast",
                         "x-low", "low", "high", "x-high"):
                continue
            return f"配置错误:prosody {attr}='{value}' 不是合法百分比。请检查 characters.yaml / scenes.yaml"
    return None


class SSMLBuilder:
    """
    把 DirectorOutput + 配置 → SSML 字符串列表。

    分层架构:
      - express-as: 段级,由 scene_change 决定,不随每行切换
      - prosody:    句级,角色+场景 rate/pitch 叠加(±15% clamp)
      - emphasis:   句级,仅情绪强烈时出现
    """

    def __init__(
        self,
        characters_path: str = _DEFAULT_CHARACTERS_PATH,
        scenes_path: str = _DEFAULT_SCENES_PATH,
        characters_override: Optional[Dict] = None,
        scenes_override: Optional[Dict] = None,
    ):
        self.characters = _load_yaml_params(characters_path)
        self.scenes = _load_yaml_params(scenes_path)
        if characters_override:
            for name, params in characters_override.items():
                self.characters[name] = VoiceParams(**params)
        if scenes_override:
            for name, params in scenes_override.items():
                self.scenes[name] = VoiceParams(**params)

    def _get_char_params(self, speaker: str) -> VoiceParams:
        """查角色配置,未识别则用 default。"""
        return self.characters.get(speaker) or self.characters.get("default") or VoiceParams()

    def _get_scene_params(self, scene: Optional[str]) -> VoiceParams:
        """查场景配置,未识别则用 default。"""
        return self.scenes.get(scene or "") or self.scenes.get("default") or VoiceParams()

    def build(
        self,
        instructions: DirectorOutput,
        voice: str = "zh-CN-XiaoxiaoNeural",
        max_chars: int = MAX_TEXT_CHARS_PER_REQUEST,
    ) -> List[str]:
        """
        构建 SSML。返回一个或多个 <speak>...</speak> 字符串。

        Args:
            instructions: Director 产出的有序指令列表
            voice: 全书使用的 voice 名
            max_chars: 单个 SSML 的纯文本上限,超出则分段

        Returns:
            SSML 字符串列表
        """
        current_scene: Optional[str] = None
        current_scene_style: Optional[str] = None  # 当前场景的 express-as style
        segments: List[str] = []
        current_lines: List[str] = []
        current_chars: int = 0

        def _flush():
            nonlocal current_lines, current_chars
            if current_lines:
                inner = "\n".join(current_lines)
                ssml = _build_speak_shell(inner, voice, current_scene_style)
                segments.append(ssml)
                current_lines = []
                current_chars = 0

        for instr in instructions:
            # ── 场景切换: flush 当前段,用新场景的 style 开新段 ──
            if isinstance(instr, SceneChange):
                current_scene = instr.scene_change
                current_scene_style = _resolve_scene_style(current_scene)
                scene_params = self._get_scene_params(current_scene)
                # flush 已有内容(场景切换意味着氛围变了,需要新的 express-as)
                if current_lines:
                    _flush()
                # 场景切换时加一个停顿(用场景的 pause)
                if scene_params.pause:
                    current_lines.append(f'<break time="{scene_params.pause}"/>')
                continue

            if not isinstance(instr, DirectorLine):
                continue

            # ── 计算 prosody: 角色参数 + 场景参数叠加 ──
            char_params = self._get_char_params(instr.speaker)
            scene_params = self._get_scene_params(current_scene)
            rate, pitch, volume = _combine_prosody(char_params, scene_params)

            # ── 决定 emphasis ──
            emphasis = _resolve_emphasis(instr.emotion, instr.emphasis)

            # ── 分段检查 ──
            text_chars = len(instr.text)
            if current_chars + text_chars > max_chars and current_lines:
                _flush()

            # ── 构建内容行 ──
            # 结构: [emphasis?] + prosody(rate/pitch[/volume]) + 正文
            escaped = _escape_xml_text(instr.text)

            if emphasis:
                inner = f'<emphasis level="{emphasis}">{escaped}</emphasis>'
            else:
                inner = escaped

            line = _build_prosody_tag(rate, pitch, volume, inner)
            current_lines.append(line)

            # ── 句后停顿 ──
            if instr.pause_after is not None:
                pause_ms = f"{instr.pause_after}ms"
            else:
                pause_ms = scene_params.pause or "500ms"
            current_lines.append(f'<break time="{pause_ms}"/>')

            current_chars += text_chars

        # 收尾
        _flush()

        if not segments:
            return [_build_speak_shell("", voice, "calm")]

        # 兜底校验
        for ssml in segments:
            err = _is_valid_prosody_output(ssml)
            if err:
                raise ValueError(err)

        return segments
