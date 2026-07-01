"""
Director(导演分析)—— 不修改剧情,只分析每句的 speaker / emotion / scene / pause。

输入:小说纯文本
输出:DirectorOutput(有序的 DirectorLine / SceneChange 列表)

这一层调墨语的 AIClient(复用其推理模型/重试/用户配置等能力),
把小说分块送入,收集 JSON 结果。
关键约束:LLM 输出的 text 必须与原文逐字一致(我们做校验,不允许偷改文字)"""
import logging
import re
from typing import List, Optional, Tuple

from app.core.ai_client import AIClient
from .models import DirectorLine, SceneChange, DirectorOutput


logger = logging.getLogger(__name__)


# 单次发给 LLM 的文本块大小(字符数)。太大易漏句/超 token,太小则调用次数多。
DEFAULT_CHUNK_SIZE = 800

# 句子切分正则:中文句号/问号/叹号/换行
_SENTENCE_SPLIT = re.compile(r'(?<=[。！？\n…])')


def split_text_to_chunks(text: str, chunk_size: int = DEFAULT_CHUNK_SIZE) -> List[str]:
    """
    把小说正文按句子边界切成不超过 chunk_size 字符的块。
    尽量在句号/问号/叹号/换行处切,避免把一句话劈成两半。
    """
    sentences = _SENTENCE_SPLIT.split(text.strip())
    sentences = [s for s in sentences if s.strip()]
    if not sentences:
        return []

    chunks: List[str] = []
    current = ""
    for sent in sentences:
        # 单句就超长:硬切(极少见)
        if len(sent) > chunk_size:
            if current:
                chunks.append(current)
                current = ""
            for i in range(0, len(sent), chunk_size):
                chunks.append(sent[i:i + chunk_size])
            continue
        if len(current) + len(sent) > chunk_size and current:
            chunks.append(current)
            current = sent
        else:
            current += sent
    if current:
        chunks.append(current)
    return chunks


# ── Prompt ────────────────────────────────────────────────────

SYSTEM_PROMPT = """你是一个"小说朗读导演"。你的任务是分析小说文本,为语音合成做准备。

【最重要的规则】
1. 你绝对不能修改、改写、增删原文的任何一个字。你输出的 text 字段必须与输入原文逐字一致。
2. 你只负责分析,不负责改写。

【输出格式】
输出一个 JSON 数组。数组里每个元素是以下两种之一:

A) 台词/旁白行:
{"speaker": "说话人代号", "text": "原文这一句,一字不改", "emotion": "情绪(可选)", "pause_after": 数字}

B) 场景切换(只在氛围明显变化时插入,不要每句都标):
{"scene_change": "场景代号"}

【说话人代号 speaker】
从以下选择(如果都不合适,用 Narrator):
- Narrator:旁白、叙述
- Messenger:信使、传令兵、路人甲
- KailanWeak:凯兰病弱状态
- KailanCalm:凯兰冷静/伪装状态
- Servant:仆人、侍从

【场景代号 scene_change】
从以下选择:
- calm:安静、日常
- night:夜晚、沉寂
- suspense:悬念、紧张
- battle:战斗、激烈
- chase:追逐、急促
- sad:悲伤、沉重
- comedy:轻松、喜剧

【情绪 emotion(可选)】
如:冷漠、愤怒、悲伤、惊恐、温柔、虚弱、平静。这是给人看的标签,目前不影响声音参数。

【pause_after】
这一句读完后的停顿(毫秒)。参考:
- 普通句号:400-600
- 重大转折/段落结束:700-1000
- 急促对话:150-300
- 长沉默:1000-2000
如果不写 pause_after,系统会用当前场景的默认停顿。

【注意事项】
- 只在场景氛围明显变化时才发 scene_change,一个场景内不要重复发。
- 把输入的每一句都要覆盖到,不能漏掉任何一句。
- 对话(引号内的内容)和旁白要分开成不同的行。
- 不要输出任何 XML、SSML、HTML 标签。
- 不要输出任何解释说明,只输出 JSON 数组。
"""


class Director:
    """导演分析器:小说文本 → DirectorOutput。复用墨语 AIClient。"""

    def __init__(
        self,
        ai_client: AIClient,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
    ):
        self.ai = ai_client
        self.chunk_size = chunk_size

    async def analyze(self, novel_text: str) -> Tuple[DirectorOutput, Optional[str]]:
        """
        分析整篇小说,返回 (指令列表, 错误信息)。

        流程:
          1. 切块
          2. 逐块调 AIClient.chat_json_retry,收集 JSON
          3. 校验:每块的输出 text 必须能在原文里找到
          4. 拼接
        """
        chunks = split_text_to_chunks(novel_text, self.chunk_size)
        if not chunks:
            return [], "输入文本为空"

        all_instructions: DirectorOutput = []
        for i, chunk in enumerate(chunks):
            logger.info(f"导演分析:处理第 {i+1}/{len(chunks)} 块 ({len(chunk)} 字)")

            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": (
                    f"请分析以下小说文本(第 {i+1}/{len(chunks)} 段),"
                    f"输出 JSON 数组。不要漏掉任何一句,不要改写任何一个字:\n\n{chunk}"
                )},
            ]

            # 复用墨语 AIClient 的 JSON 调用(自带重试 + 强清洗)
            result = await self.ai.chat_json_retry(messages=messages, temperature=0.3)
            if result.get("error") or result.get("json") is None:
                err = result.get("error") or "LLM 未返回有效 JSON"
                return all_instructions, f"第 {i+1} 块分析失败: {err}"

            raw_list = result["json"]
            if not isinstance(raw_list, list):
                raw_list = [raw_list]

            # 解析 + 校验
            block_instructions, validate_err = self._parse_and_validate(raw_list, chunk)
            if validate_err:
                logger.warning(f"第 {i+1} 块校验警告: {validate_err}")
            all_instructions.extend(block_instructions)

        return all_instructions, None

    def _parse_and_validate(
        self,
        raw_list: list,
        source_chunk: str,
    ) -> Tuple[DirectorOutput, Optional[str]]:
        """
        把原始 dict 列表转成 DirectorLine/SceneChange,并校验 text 是否与原文一致。

        校验规则:DirectorLine 的 text 必须能在 source_chunk 里找到(去掉空白后)。
        找不到的行记为警告,但仍然保留(不致命,让 Builder 继续处理)。
        """
        instructions: DirectorOutput = []
        warnings: List[str] = []
        source_normalized = source_chunk.replace(" ", "").replace("\n", "").replace("\t", "")

        for item in raw_list:
            if not isinstance(item, dict):
                continue
            if "scene_change" in item:
                scene = str(item["scene_change"]).strip()
                if scene:
                    instructions.append(SceneChange(scene_change=scene))
                continue
            if "text" in item:
                text = str(item["text"]).strip()
                speaker = str(item.get("speaker", "Narrator")).strip() or "Narrator"
                emotion = item.get("emotion")
                pause_after = item.get("pause_after")
                if pause_after is not None:
                    try:
                        pause_after = int(pause_after)
                    except (ValueError, TypeError):
                        pause_after = None
                # 校验:text 去空白后应在原文里
                text_normalized = text.replace(" ", "").replace("\n", "").replace("\t", "")
                if text_normalized and text_normalized not in source_normalized:
                    warnings.append(f"text 与原文不一致: '{text[:30]}...'")
                instructions.append(DirectorLine(
                    speaker=speaker,
                    text=text,
                    emotion=emotion,
                    pause_after=pause_after,
                ))

        warn_msg = "; ".join(warnings) if warnings else None
        return instructions, warn_msg
