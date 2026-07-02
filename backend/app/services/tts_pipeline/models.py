"""
小说→SSML 流水线的数据模型。

Director(导演分析)的输出是一组有序的「指令」:
  - DirectorLine:  一句正文 + 说话人/情绪/停顿
  - SceneChange:   场景切换(切换后持续生效,直到下一次切换)
"""
from typing import Optional, Union, List, Dict, Any
from pydantic import BaseModel


class DirectorLine(BaseModel):
    """导演分析产出的单行指令。"""
    speaker: str                        # Narrator / Messenger / KailanWeak / ...
    text: str                           # 原文句子(必须与小说原文一字不差)
    emotion: Optional[str] = None       # 冷漠/愤怒/悲伤/... (用于映射 express-as style 和 emphasis)
    emphasis: Optional[str] = None      # "strong" / "moderate" / "none" / "reduced" (强调级别)
    pause_after: Optional[int] = None   # 句后停顿(毫秒),导演判断;None 表示用场景默认


class SceneChange(BaseModel):
    """场景切换标记。出现后,后续所有 Line 享用该场景的预设,直到下一次切换。"""
    scene_change: str                   # calm / battle / night / ...


# Director 的完整输出 = 有序指令列表
DirectorOutput = List[Union[DirectorLine, SceneChange]]


class VoiceParams(BaseModel):
    """角色或场景映射到的语音参数。所有值由配置决定,Builder 不接受任意字符串。"""
    rate: str = "0%"                    # 如 "-10%" / "+8%"
    pitch: str = "0%"                   # 如 "-5%" / "+5Hz" (统一用 % 避免 dB 坑)
    style: Optional[str] = None         # express-as style,如 "calm"
    volume: Optional[str] = None        # prosody volume,如 "soft" / "loud" / "x-loud"
    emphasis: Optional[str] = None      # 强调级别: "strong" / "moderate" / "none" / "reduced"
    emotion_style: Optional[Dict[str, str]] = None  # 情绪→express-as style 映射(场景级覆盖)
    pause: Optional[str] = None         # 场景默认停顿,如 "600ms"
    voice: Optional[str] = None         # 预留:多角色配音时指定不同 voice
