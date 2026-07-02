"""分镜剧本数据模型。

Storyshot（分镜）= 一个可拍摄/可生成的最小视觉单元。
一个镜头可以覆盖多句原文（DirectorLine），也可以只有旁白没有台词。

设计原则：
  - text 字段（台词/旁白原文）必须与原文逐字一致，供 TTS 配音和字幕使用
  - visual_prompt / negative_prompt 用英文，因为 SD/ComfyUI 等图像工具对英文 prompt 效果好
  - duration + pause_after 决定音画对齐时长
  - sfx / bgm_tag 供后续合成阶段叠加音效和背景音乐
"""

from typing import Optional, List, Union, Dict, Any

from pydantic import BaseModel


# ── 单个分镜 ──────────────────────────────────────────────────

class Storyshot(BaseModel):
    """一个分镜（shot）。

    音频维度字段（speaker/emotion/emphasis/pause_after）直接从 Director 结果继承，
    Screenwriter 负责补充画面维度字段（shot_type/action/visual_prompt 等）。

    对于"纯旁白镜头"（画面是环境空镜但有人在旁白），speaker=Narrator，
    dialogue 可以为空，action 描述画面。
    """
    # ── 画面维度（Screenwriter 补充）──
    shot_type: str = "medium"          # 镜头景别：wide/medium/closeup/extreme_closeup/aerial
    action: str = ""                   # 画面动作描述（中文，给创作者看）
    camera_move: Optional[str] = None  # 镜头运动：static/slow_push_in/pan/tilt/tracking/zoom
    visual_prompt: str = ""            # 画面生成提示词（英文，给 SD/ComfyUI 用）
    negative_prompt: Optional[str] = None  # 负面提示词（英文）
    duration: float = 3.0              # 该镜头预估时长（秒）

    # ── 音频维度（从 Director 继承）──
    speaker: str = "Narrator"
    text: str = ""                     # 原文句子（逐字一致，供配音+字幕）
    emotion: Optional[str] = None      # 情绪标签
    emphasis: Optional[str] = None     # 强调级别
    pause_after: Optional[int] = None  # 句后停顿（毫秒）

    # ── 音效维度（Screenwriter 补充）──
    sfx: List[str] = []                # 音效标签，如 ["sword_clash", "wind_howl"]
    bgm_tag: Optional[str] = None      # BGM 标签，如 "suspense" / "battle" / "calm"

    # ── 场景标识（从 Director 的 SceneChange 继承当前场景）──
    scene: Optional[str] = None        # 当前场景代号，如 "night" / "battle"


class SceneHeading(BaseModel):
    """场景标题（分镜剧本中的场景切换标记）。

    对应 Director 的 SceneChange，但补充画面维度：
    告诉后续图像生成阶段"整体环境/时间/地点变了"。
    """
    scene_change: str                  # 场景代号（与 Director 一致）
    location: Optional[str] = None     # 地点描述（中文，如"审判所废墟"）
    time_of_day: Optional[str] = None  # 时间（如"夜晚"/"黄昏"/"清晨"）
    mood: Optional[str] = None         # 氛围（如"压抑"/"紧张"/"宁静"）


# 分镜剧本 = 有序的分镜和场景标题列表
Screenplay = List[Union[Storyshot, SceneHeading]]


# ── 分镜剧本的完整结果（含统计信息）────────────────────────────

class ScreenplayResult(BaseModel):
    """一章的分镜剧本完整结果，用于持久化和前端展示。"""
    success: bool = True
    shots: List[Dict[str, Any]] = []   # 序列化后的 Screenplay（兼容 JSON 存储）
    stats: Dict[str, Any] = {}         # 统计：shot_count/total_duration/scene_count 等
    director_stats: Optional[Dict[str, Any]] = None  # Director 阶段的统计（音频维度）
    error: Optional[str] = None
