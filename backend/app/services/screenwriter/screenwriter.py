"""Screenwriter（编剧/分镜）—— 在 Director 结果基础上补充画面维度。

模式 B 流程：
  输入：小说原文 + Director 指令（已有音频维度：speaker/emotion/scene/pause）
  处理：
    1. 把 Director 指令按"场景"分组，每组是一个连续的镜头序列
    2. 逐组送 LLM，让它补充画面维度（shot_type/action/visual_prompt/duration/sfx/bgm_tag）
    3. 校验：LLM 返回的 text 必须与原文逐字一致（和 Director 同样的校验机制）
  输出：Screenplay（有序的 Storyshot / SceneHeading 列表）

关键约束：
  - text 字段绝不修改原文（配音和字幕的根基）
  - visual_prompt 用英文（图像工具对英文 prompt 效果好）
  - 一个镜头可以覆盖多句 DirectorLine（场景不变时合并为一个镜头）
"""

import json
import logging
import re
from typing import List, Optional, Tuple

from app.core.ai_client import AIClient
from app.services.tts_pipeline.director import split_text_to_chunks
from app.services.tts_pipeline.models import DirectorLine, SceneChange, DirectorOutput

from .models import Storyshot, SceneHeading, Screenplay


logger = logging.getLogger(__name__)

# 分镜分析的文本块大小（字符）。比 Director 的 800 大，因为分镜需要更大的上下文窗口
# 来理解一个完整场景的起承转合，才能合理地切分镜头。
DEFAULT_SCREENPLAY_CHUNK_SIZE = 1500


# ── Prompt ────────────────────────────────────────────────────

SYSTEM_PROMPT = """你是一个"小说分镜编剧"。你的任务是把小说文本拆解成可拍摄的分镜（shot），为后续 AI 视频生成做准备。

【最重要的规则】
1. 你绝对不能修改、改写、增删原文的任何一个字。你输出的 text 字段必须与输入原文逐字一致。
2. 你只负责补充画面维度，不改变任何音频维度的信息。

【输入】
你会收到：
- 原文片段
- 导演分析结果（JSON 数组，每行已有 speaker/text/emotion/scene 等音频维度字段）

【你的任务】
把导演分析的每一行归入一个"分镜"（shot），并为每个分镜补充画面维度。
一个镜头可以覆盖多行导演指令（场景和氛围不变时合并），也可以只有一行。

【输出格式】
输出一个 JSON 数组，每个元素是以下两种之一：

A) 分镜（shot）：
{
  "shot_type": "景别",
  "action": "画面动作描述（中文，给创作者看）",
  "camera_move": "镜头运动",
  "visual_prompt": "英文画面提示词，给 Stable Diffusion / AI 图像工具用",
  "negative_prompt": "英文负面提示词（可选）",
  "duration": 数字（秒）,
  "speaker": "继承自导演分析的说话人",
  "text": "原文这一句，一字不改",
  "emotion": "继承的情绪",
  "emphasis": "继承的强调级别",
  "pause_after": 数字（继承的停顿毫秒）,
  "sfx": ["音效标签"],
  "bgm_tag": "BGM标签"
}

B) 场景标题（场景切换时插入）：
{
  "scene_heading": true,
  "scene_change": "场景代号",
  "location": "地点描述（中文）",
  "time_of_day": "时间",
  "mood": "氛围"
}

【shot_type 景别】从以下选择：
- wide: 远景（建立环境、展示全貌）
- medium: 中景（人物半身，最常见的叙事镜头）
- closeup: 特写（面部表情、关键物品）
- extreme_closeup: 大特写（眼睛、手指等细节）
- aerial: 航拍/俯瞰

【camera_move 镜头运动】从以下选择（不写就是 static）：
- static: 固定不动
- slow_push_in: 缓慢推进（营造紧张/聚焦）
- slow_pull_out: 缓慢拉远（揭示全貌/结束感）
- pan: 水平摇摄
- tilt: 垂直摇摄
- tracking: 跟随拍摄
- zoom: 快速变焦

【visual_prompt 英文提示词】
这是给 AI 图像生成工具用的，必须用英文。要求：
- 描述画面的核心元素：场景环境、人物外观、动作、光影
- 包含风格关键词，如：cinematic, dark fantasy, anime style, oil painting 等
- 包含构图/质量关键词，如：8k, highly detailed, dramatic lighting, depth of field
- 不要写人名，用外貌特征描述（如 "a young woman with dark hair" 而非 "Kailan"）
- 长度 50-120 个英文单词

示例：
"dark fantasy, narrow stone alley at night, a young woman with long dark hair cornered against a crumbling wall, five armored knights holding glowing blue energy swords, tense atmosphere, dramatic moonlight, cinematic composition, 8k, highly detailed"

【negative_prompt 负面提示词】（可选）
排除不想要的元素，如："modern clothing, text, watermark, deformed, extra fingers, cartoon"

【duration 时长】
根据画面内容预估该镜头的合理时长（秒）：
- 简单动作/对话：2-3 秒
- 复杂动作序列：3-5 秒
- 环境空镜/氛围镜头：3-5 秒
- 快速切换的紧张场景：1.5-2.5 秒

【sfx 音效标签】
列出这个镜头需要的环境音/动作音效，用英文标签：
- 环境音：wind_howl, rain, thunder, fire_crackle, night_crickets, crowd_murmur
- 动作音：sword_clash, footstep, door_creak, explosion, glass_shatter, horse_gallop
- 魔法/特效：energy_hum, magic_glow, portal_open, light_burst
如果不需要音效，用空数组 []

【bgm_tag BGM标签】
这个镜头适合的背景音乐氛围：
- calm: 平静、日常
- suspense: 悬念、紧张
- battle: 战斗、激烈
- sad: 悲伤、沉重
- cheerful: 欢快
- mysterious: 神秘
- epic: 史诗、宏大
不写则继承上一个 scene_heading 的 mood 推断。

【分镜原则】
1. 场景不变时，相邻的几行可以合并为一个镜头（共用 visual_prompt），text 仍保持逐行。
2. 场景/地点/时间明显变化时，先输出 scene_heading，再输出该场景的分镜。
3. 重要表情/动作/物品给 closeup 或 extreme_closeup。
4. 不要每行都单独一个镜头——那太碎了。一章 2000 字大约 15-30 个镜头。
5. 你必须覆盖输入的每一行导演指令，不能漏掉任何一句的 text。
"""


class Screenwriter:
    """分镜编剧：原文 + Director 结果 → 带画面维度的分镜剧本。"""

    def __init__(
        self,
        ai_client: AIClient,
        chunk_size: int = DEFAULT_SCREENPLAY_CHUNK_SIZE,
    ):
        self.ai = ai_client
        self.chunk_size = chunk_size

    async def generate(
        self,
        novel_text: str,
        director_instructions: DirectorOutput,
    ) -> Tuple[Screenplay, Optional[str]]:
        """
        生成分镜剧本。

        Args:
            novel_text: 小说原文
            director_instructions: Director 的输出（DirectorLine/SceneChange 列表）

        Returns:
            (Screenplay 列表, 错误信息)
        """
        if not novel_text.strip():
            return [], "原文为空"
        if not director_instructions:
            return [], "Director 指令为空，请先运行导演分析"

        # 把 Director 指令按原文块分组（和原文块对齐）
        chunks = split_text_to_chunks(novel_text, self.chunk_size)
        if not chunks:
            return [], "原文分块失败"

        # 把 Director 指令分配到对应的原文块
        # 策略：按 text 内容匹配，把每个指令归入它所属的原文块
        chunk_instructions = self._assign_instructions_to_chunks(
            director_instructions, chunks
        )

        all_shots: Screenplay = []
        for i, (chunk, instructions) in enumerate(zip(chunks, chunk_instructions)):
            logger.info(
                f"分镜分析:处理第 {i+1}/{len(chunks)} 块 "
                f"({len(chunk)} 字, {len(instructions)} 行指令)"
            )

            # 构造导演分析的 JSON 给 LLM 看
            director_json = json.dumps(
                [_instruction_to_dict(instr) for instr in instructions],
                ensure_ascii=False,
                indent=2,
            )

            user_content = (
                f"以下是小说原文（第 {i+1}/{len(chunks)} 段）和对应的导演分析结果。\n"
                f"请基于导演分析的每一行，补充画面维度，生成分镜。\n"
                f"不要漏掉任何一句的 text，不要改写任何一个字。\n\n"
                f"【原文】\n{chunk}\n\n"
                f"【导演分析】\n{director_json}"
            )

            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ]

            result = await self.ai.chat_json_retry(messages=messages, temperature=0.4)
            if result.get("error") or result.get("json") is None:
                err = result.get("error") or "LLM 未返回有效 JSON"
                return all_shots, f"第 {i+1} 块分镜分析失败: {err}"

            raw_list = result["json"]
            if not isinstance(raw_list, list):
                raw_list = [raw_list]

            # 解析 + 校验
            block_shots, validate_err = self._parse_and_validate(raw_list, chunk)
            if validate_err:
                logger.warning(f"第 {i+1} 块校验警告: {validate_err}")
            all_shots.extend(block_shots)

        return all_shots, None

    def _assign_instructions_to_chunks(
        self,
        instructions: DirectorOutput,
        chunks: List[str],
    ) -> List[DirectorOutput]:
        """
        把 Director 指令按原文块分组。

        策略：对每个指令的 text，找到它所属的原文块（text 去空白后在哪个块里出现）。
        SceneChange 跟着它之后的第一个 DirectorLine 走。
        """
        # 预处理：每个块的归一化文本
        chunk_normalized = [
            c.replace(" ", "").replace("\n", "").replace("\t", "")
            for c in chunks
        ]

        result: List[DirectorOutput] = [[] for _ in chunks]
        pending_scene_changes: list = []  # 还没归属的 SceneChange

        for instr in instructions:
            if isinstance(instr, SceneChange):
                pending_scene_changes.append(instr)
                continue

            if isinstance(instr, DirectorLine):
                text_norm = instr.text.replace(" ", "").replace("\n", "").replace("\t", "")
                # 找到 text 所属的块
                found_chunk = -1
                for ci, cnorm in enumerate(chunk_normalized):
                    if text_norm and text_norm in cnorm:
                        found_chunk = ci
                        break

                if found_chunk < 0:
                    # 找不到归属，放到最后一个非空块（兜底）
                    found_chunk = len(chunks) - 1

                # 把待定的 SceneChange 归到同一个块
                result[found_chunk].extend(pending_scene_changes)
                pending_scene_changes.clear()
                result[found_chunk].append(instr)

        # 剩余未归属的 SceneChange 放到第一个块
        if pending_scene_changes and result:
            result[0].extend(pending_scene_changes)

        return result

    def _parse_and_validate(
        self,
        raw_list: list,
        source_chunk: str,
    ) -> Tuple[Screenplay, Optional[str]]:
        """
        把 LLM 返回的原始 dict 列表转成 Storyshot/SceneHeading，并校验 text。

        校验规则：Storyshot.text 去空白后应在原文 chunk 里找到（和 Director 一致）。
        找不到记为警告但不致命。
        """
        shots: Screenplay = []
        warnings: List[str] = []
        source_normalized = source_chunk.replace(" ", "").replace("\n", "").replace("\t", "")

        valid_shot_types = {"wide", "medium", "closeup", "extreme_closeup", "aerial"}
        valid_camera_moves = {
            "static", "slow_push_in", "slow_pull_out", "pan", "tilt", "tracking", "zoom"
        }

        for item in raw_list:
            if not isinstance(item, dict):
                continue

            # 场景标题
            if item.get("scene_heading") or "scene_change" in item and "text" not in item:
                scene = str(item.get("scene_change", "")).strip()
                if scene:
                    shots.append(SceneHeading(
                        scene_change=scene,
                        location=item.get("location"),
                        time_of_day=item.get("time_of_day"),
                        mood=item.get("mood"),
                    ))
                continue

            # 分镜
            if "text" in item or "action" in item:
                text = str(item.get("text", "")).strip()
                action = str(item.get("action", "")).strip()

                # 校验景别
                shot_type = str(item.get("shot_type", "medium")).strip()
                if shot_type not in valid_shot_types:
                    shot_type = "medium"

                # 校验镜头运动
                camera_move = item.get("camera_move")
                if camera_move and camera_move not in valid_camera_moves:
                    camera_move = None

                # 校验时长
                duration = item.get("duration", 3.0)
                try:
                    duration = float(duration)
                    if duration < 0.5:
                        duration = 0.5
                    elif duration > 30:
                        duration = 30.0
                except (ValueError, TypeError):
                    duration = 3.0

                # 校验 pause_after
                pause_after = item.get("pause_after")
                if pause_after is not None:
                    try:
                        pause_after = int(pause_after)
                    except (ValueError, TypeError):
                        pause_after = None

                # 音效标签
                sfx = item.get("sfx", [])
                if not isinstance(sfx, list):
                    sfx = [str(sfx)] if sfx else []

                # 校验 text 与原文一致（和 Director 相同的校验）
                if text:
                    text_normalized = text.replace(" ", "").replace("\n", "").replace("\t", "")
                    if text_normalized and text_normalized not in source_normalized:
                        warnings.append(f"text 与原文不一致: '{text[:30]}...'")

                shots.append(Storyshot(
                    shot_type=shot_type,
                    action=action,
                    camera_move=camera_move,
                    visual_prompt=str(item.get("visual_prompt", "")).strip(),
                    negative_prompt=item.get("negative_prompt"),
                    duration=duration,
                    speaker=str(item.get("speaker", "Narrator")).strip() or "Narrator",
                    text=text,
                    emotion=item.get("emotion"),
                    emphasis=item.get("emphasis"),
                    pause_after=pause_after,
                    sfx=[str(s) for s in sfx],
                    bgm_tag=item.get("bgm_tag"),
                ))

        warn_msg = "; ".join(warnings) if warnings else None
        return shots, warn_msg


# ── 辅助函数 ──────────────────────────────────────────────────

def _instruction_to_dict(instr) -> dict:
    """把 DirectorLine/SceneChange 转成简洁 dict，供 LLM 输入。"""
    if isinstance(instr, SceneChange):
        return {"scene_change": instr.scene_change}
    if isinstance(instr, DirectorLine):
        d = {
            "speaker": instr.speaker,
            "text": instr.text,
        }
        if instr.emotion:
            d["emotion"] = instr.emotion
        if instr.emphasis:
            d["emphasis"] = instr.emphasis
        if instr.pause_after is not None:
            d["pause_after"] = instr.pause_after
        return d
    return {}


def screenplay_to_json(screenplay: Screenplay) -> List[dict]:
    """把 Screenplay 序列化为可存 JSON / 传前端的 dict 列表。"""
    result = []
    for item in screenplay:
        if isinstance(item, SceneHeading):
            result.append({
                "scene_heading": True,
                "scene_change": item.scene_change,
                "location": item.location,
                "time_of_day": item.time_of_day,
                "mood": item.mood,
            })
        elif isinstance(item, Storyshot):
            result.append(item.model_dump())
    return result


def screenplay_stats(screenplay: Screenplay) -> dict:
    """统计分镜剧本的基本数据。"""
    shot_count = sum(1 for s in screenplay if isinstance(s, Storyshot))
    scene_count = sum(1 for s in screenplay if isinstance(s, SceneHeading))
    total_duration = sum(s.duration for s in screenplay if isinstance(s, Storyshot))

    # 景别分布
    shot_type_dist: dict[str, int] = {}
    for s in screenplay:
        if isinstance(s, Storyshot):
            shot_type_dist[s.shot_type] = shot_type_dist.get(s.shot_type, 0) + 1

    # BGM 分布
    bgm_tags = set()
    for s in screenplay:
        if isinstance(s, Storyshot) and s.bgm_tag:
            bgm_tags.add(s.bgm_tag)

    return {
        "shot_count": shot_count,
        "scene_count": scene_count,
        "total_duration_sec": round(total_duration, 1),
        "total_duration_display": _format_duration(total_duration),
        "shot_type_distribution": shot_type_dist,
        "bgm_tags": sorted(bgm_tags),
    }


def _format_duration(seconds: float) -> str:
    """把秒数格式化为 mm:ss 显示。"""
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m:02d}:{s:02d}"
