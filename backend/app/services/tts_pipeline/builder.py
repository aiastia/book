"""
SSML Builder —— 把 Director 指令 + 配置拼成 Azure 合法 SSML。

这是纯程序模块,不调 AI。所有 prosody 值来自 YAML 配置,不接受任意字符串,
从根本上杜绝 +1dB 这类非法值。

核心职责:
  1. 遇到 SceneChange 更新当前场景预设(场景持续生效直到下一次切换)
  2. 对每个 DirectorLine:角色 prosody + 场景 prosody 叠加 → 生成 <prosody>(平铺,不嵌套)
  3. 句后插入 <break>(优先 pause_after,否则用场景默认 pause)
  4. 累计纯文本长度,超过上限则切断开新的 <speak> 外壳
"""
import os
import re
import xml.etree.ElementTree as ET
from typing import List, Dict, Optional, Tuple

import yaml

from app.core.config import settings
from .models import DirectorLine, SceneChange, VoiceParams, DirectorOutput


# Azure TTS 单次请求建议的文本字符数上限
MAX_TEXT_CHARS_PER_REQUEST = 3000

# 默认配置文件路径:放在墨语 data/tts_config/ 下
_CONFIG_DIR = os.path.join(settings.DATA_DIR, "tts_config")
_DEFAULT_CHARACTERS_PATH = os.path.join(_CONFIG_DIR, "characters.yaml")
_DEFAULT_SCENES_PATH = os.path.join(_CONFIG_DIR, "scenes.yaml")

# ---- 内置默认配置（首次运行或 Docker 环境自动写入）----
_DEFAULT_CHARACTERS_YAML = """\
# 角色映射配置 ─ speaker(由 Director 分析产出)→ 语音参数
# 字段说明: rate/pitch 用百分比, style 是 express-as 的 style
Narrator:
  rate: "-2%"
  pitch: "0%"
  style: "calm"
Messenger:
  rate: "-12%"
  pitch: "-6%"
  style: "calm"
default:
  rate: "0%"
  pitch: "0%"
  style: "calm"
"""

_DEFAULT_SCENES_YAML = """\
# 场景预设 ─ 场景名 → 语音参数 + 默认停顿
calm:
  rate: "-2%"
  pitch: "0%"
  pause: "600ms"
night:
  rate: "-5%"
  pitch: "0%"
  pause: "600ms"
suspense:
  rate: "-3%"
  pitch: "0%"
  pause: "700ms"
battle:
  rate: "+8%"
  pitch: "0%"
  pause: "150ms"
sad:
  rate: "-10%"
  pitch: "-3%"
  pause: "800ms"
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
    """
    解析百分比字符串为浮点数。
    支持: "-10%" / "+5%" / "0%" / "-3"
    不支持 dB / Hz(那些不该出现在配置里,若出现说明配置写错了)。
    """
    value = value.strip()
    if value.endswith("%"):
        return float(value[:-1])
    # 纯数字也按百分比处理(配置里 "0" 视为 0%)
    return float(value)


def _combine_prosody(char_params: VoiceParams, scene_params: VoiceParams) -> Tuple[str, str]:
    """
    角色参数 + 场景参数相加,返回合并后的 (rate, pitch)。
    例如 角色 rate=-15% + 场景 rate=-2% = rate=-17%
    """
    rate = _parse_percent(char_params.rate) + _parse_percent(scene_params.rate)
    pitch = _parse_percent(char_params.pitch) + _parse_percent(scene_params.pitch)
    # 格式化:整数不带小数点,负零归零
    def fmt(v: float) -> str:
        v = round(v)
        if v == 0:
            return "0%"
        sign = "+" if v > 0 else ""
        return f"{sign}{v}%"
    return fmt(rate), fmt(pitch)


def _escape_xml_text(text: str) -> str:
    """转义正文里的 XML 特殊字符(不碰我们自己加的标签)。"""
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    return text


def _build_speak_shell(inner_content: str, voice: str, style: Optional[str]) -> str:
    """
    用 <speak><voice><express-as> 外壳包裹内容。
    命名空间声明放在 <speak> 根元素上(Azure 要求)。
    """
    parts = [
        '<speak version="1.0" '
        'xmlns="http://www.w3.org/2001/10/synthesis" '
        'xmlns:mstts="https://www.w3.org/2001/mstts" '
        f'xml:lang="zh-CN">',
        f'<voice name="{voice}">',
    ]
    if style:
        parts.append(f'<mstts:express-as style="{style}">')
    parts.append(inner_content)
    if style:
        parts.append('</mstts:express-as>')
    parts.extend(['</voice>', '</speak>'])
    return "\n".join(parts)


def _is_valid_prosody_output(ssml: str) -> Optional[str]:
    """
    兜底校验:扫一遍生成的 SSML,确认没有 dB/Hz 等非法后缀。
    正常情况下配置正确时永远不会触发;触发说明配置写错了。
    返回错误提示,或 None。
    """
    for match in re.finditer(r'<prosody\b[^>]*>', ssml, re.IGNORECASE):
        tag = match.group(0)
        for attr in ("volume", "rate", "pitch"):
            am = re.search(rf'{attr}\s*=\s*"([^"]*)"', tag, re.IGNORECASE)
            if not am:
                continue
            value = am.group(1)
            # 合法:百分比 / 预设词(这里我们只用百分比)
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

    用法:
        builder = SSMLBuilder(characters_path, scenes_path)
        ssml_parts = builder.build(director_output, voice="zh-CN-XiaoxiaoNeural")
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
        # 允许调用方覆盖配置(API 请求里传入自定义角色/场景)
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
            SSML 字符串列表(通常 1 个,长文本可能多个)
        """
        current_scene: Optional[str] = None
        current_style: Optional[str] = None
        segments: List[str] = []      # 每个 segment 是一段已拼接的内容
        current_lines: List[str] = []  # 当前 segment 的内容行
        current_chars: int = 0         # 当前 segment 的纯文本字数

        def _flush():
            """把当前累积的内容包进 <speak> 外壳,存入 segments。"""
            nonlocal current_lines, current_chars
            if current_lines:
                inner = "\n".join(current_lines)
                ssml = _build_speak_shell(inner, voice, current_style)
                segments.append(ssml)
                current_lines = []
                current_chars = 0

        for instr in instructions:
            # 场景切换
            if isinstance(instr, SceneChange):
                current_scene = instr.scene_change
                scene_params = self._get_scene_params(current_scene)
                # 场景的 style 会覆盖角色的 style?不。style 以场景为主(场景决定整体氛围)
                if scene_params.style:
                    current_style = scene_params.style
                # 场景切换本身加一个稍长的停顿(用场景的 pause)
                if scene_params.pause and current_lines:
                    current_lines.append(f'<break time="{scene_params.pause}"/>')
                continue

            if not isinstance(instr, DirectorLine):
                continue

            # 计算这一行的 prosody:角色参数 + 场景参数叠加
            char_params = self._get_char_params(instr.speaker)
            scene_params = self._get_scene_params(current_scene)
            rate, pitch = _combine_prosody(char_params, scene_params)

            # style 优先用角色的(角色个性 > 场景氛围),角色没指定则用场景的
            line_style = char_params.style or scene_params.style or current_style
            current_style = line_style

            # 纯文本字数统计(用于分段)
            text_chars = len(instr.text)
            if current_chars + text_chars > max_chars and current_lines:
                _flush()

            # 拼这一行:<prosody> + 转义后的正文 + </prosody>
            escaped = _escape_xml_text(instr.text)
            # rate=0% pitch=0% 时也包 prosody(保持一致结构;Azure 接受 0%)
            current_lines.append(f'<prosody rate="{rate}" pitch="{pitch}">{escaped}</prosody>')

            # 句后停顿
            if instr.pause_after is not None:
                pause_ms = f"{instr.pause_after}ms"
            else:
                pause_ms = scene_params.pause or "500ms"
            current_lines.append(f'<break time="{pause_ms}"/>')

            current_chars += text_chars

        # 收尾
        _flush()

        if not segments:
            # 空输入,返回一个最小有效 SSML
            return [_build_speak_shell("", voice, "calm")]

        # 兜底校验所有输出(理论上不会触发,触发说明配置有误)
        for ssml in segments:
            err = _is_valid_prosody_output(ssml)
            if err:
                raise ValueError(err)

        return segments
