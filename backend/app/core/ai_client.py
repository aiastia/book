"""AI 客户端 - 自定义 OpenAI 兼容接口"""

import asyncio
import json
import re
import time
from collections.abc import AsyncGenerator


def _try_parse_inline_tool_calls(content: str) -> list | None:
    """尝试从文本内容中解析内联工具调用（兼容不同模型的返回格式）。

    支持格式：
    - Kimi: <|tool_calls_section_begin|>...<|tool_calls_section_end|>
    - DSML: <｜DSML｜tool_calls>...<invoke name="x">...</invoke>...</｜DSML｜tool_calls>
    - 通用: 任何包含 function name + arguments 的结构化文本
    返回标准 tool_calls 列表或 None。
    """
    if not content:
        return None
    # Kimi 原生格式
    if "<|tool_call_begin|>" in content:
        tool_calls = []
        for match in re.finditer(
            r"<\|tool_call_begin\|>(.+?)<\|tool_call_argument_begin\|>(.+?)<\|tool_call_end\|>",
            content,
            re.DOTALL,
        ):
            name = match.group(1).strip()
            args_str = match.group(2).strip()
            try:
                args = json.loads(args_str)
            except Exception:
                args = {}
            # 去掉 functions. 前缀（如 functions.query_location → query_location）
            clean_name = name.replace("functions.", "").split(":")[0]
            tool_calls.append(
                {
                    "id": f"inline_{clean_name}",
                    "type": "function",
                    "function": {
                        "name": clean_name,
                        "arguments": json.dumps(args, ensure_ascii=False),
                    },
                }
            )
        return tool_calls if tool_calls else None

    # DSML 格式：<｜DSML｜tool_calls>...<invoke name="x">...<parameter ...>...</invoke>...</｜DSML｜tool_calls>
    # 使用全角竖线 ｜ (U+FF5C) 作为分隔符
    if "｜DSML｜tool_calls" in content or "<｜DSML｜invoke" in content:
        tool_calls = []
        for match in re.finditer(
            r"<｜DSML｜invoke\s+name\s*=\s*\"([^\"]+)\">(.*?)</｜DSML｜invoke>",
            content,
            re.DOTALL,
        ):
            name = match.group(1).strip()
            body = match.group(2)
            args = {}
            for pm in re.finditer(
                r"<｜DSML｜parameter\s+name\s*=\s*\"([^\"]+)\"[^>]*>(.*?)</｜DSML｜parameter>",
                body,
                re.DOTALL,
            ):
                pname = pm.group(1).strip()
                pval = pm.group(2).strip()
                # 尝试解析 JSON，否则保留字符串
                try:
                    pval = json.loads(pval)
                except Exception:
                    pass
                args[pname] = pval
            clean_name = name.replace("functions.", "").split(":")[0]
            tool_calls.append(
                {
                    "id": f"dsml_{clean_name}",
                    "type": "function",
                    "function": {
                        "name": clean_name,
                        "arguments": json.dumps(args, ensure_ascii=False),
                    },
                }
            )
        return tool_calls if tool_calls else None

    # 兜底：检测任意 <|...|> 格式的 tool_call 标记（防止未来新格式泄漏）
    if re.search(r"<\|[^>]+\|tool_call", content):
        return []  # 返回空列表触发 content="" 清理

    return None


from openai import AsyncOpenAI

from app.core.config import settings

# 支持的 Provider 类型
SUPPORTED_PROVIDERS = ["openai", "anthropic", "gemini"]


class AIClient:
    """统一的 AI 调用客户端，支持自定义 OpenAI 兼容接口。

    通过 provider 字段区分厂商：
    - openai（默认）：走 AsyncOpenAI，兼容 deepseek/moonshot/智谱等所有 OpenAI 兼容接口
    - anthropic：Claude 系列（通过 openai 兼容代理或直接 anthropic SDK）
    - gemini：Google Gemini
    """

    def __init__(
        self,
        base_url: str = None,
        api_key: str = None,
        model: str = None,
        provider: str = "openai",
        embedding_model: str = None,
        reasoning_model: bool = False,
        reasoning_effort: str = "low",
        default_temperature: float = None,
        default_top_p: float = None,
        default_frequency_penalty: float = None,
        default_presence_penalty: float = None,
        default_max_tokens: int = None,
    ):
        self.base_url = base_url or settings.AI_BASE_URL
        self.api_key = api_key or settings.AI_API_KEY
        self.model = model or settings.AI_MODEL
        self.provider = (provider or "openai").lower()
        self.embedding_model = embedding_model or ""
        self.reasoning_model = bool(reasoning_model)
        self.reasoning_effort = reasoning_effort or "low"
        self.default_temperature = default_temperature
        self.default_top_p = default_top_p
        self.default_frequency_penalty = default_frequency_penalty
        self.default_presence_penalty = default_presence_penalty
        self.default_max_tokens = default_max_tokens
        self._client = None

    def _apply_reasoning(self, kwargs: dict) -> dict:
        if self.reasoning_model:
            kwargs["temperature"] = 1
            kwargs.pop("top_p", None)
            kwargs.pop("frequency_penalty", None)
            kwargs.pop("presence_penalty", None)
            if "extra_body" not in kwargs:
                kwargs["extra_body"] = {}
            kwargs["extra_body"].setdefault("reasoning_effort", self.reasoning_effort)
        return kwargs

    def _resolve_temperature(self, temperature: float) -> float:
        """temperature 解析：显式传参 > 模型配置 > settings。"""
        if temperature is not None:
            return temperature
        if self.default_temperature is not None:
            return self.default_temperature
        return settings.AI_TEMPERATURE

    def _resolve_top_p(self, top_p: float) -> float:
        """top_p 解析：显式传参 > 模型配置 > settings。"""
        if top_p is not None:
            return top_p
        if self.default_top_p is not None:
            return self.default_top_p
        return settings.AI_TOP_P

    def _resolve_max_tokens(self, max_tokens: int) -> int:
        """max_tokens 解析：显式传参 > 模型配置 > settings。"""
        if max_tokens is not None:
            return max_tokens
        if self.default_max_tokens is not None:
            return self.default_max_tokens
        return settings.AI_DEFAULT_MAX_TOKENS

    @staticmethod
    def _defaults_from_cfg(cfg) -> dict:
        """从 AIModelConfig 提取模型配置层的默认参数（temperature/top_p/penalty）。
        AIModelConfig 按 *100 整数存储，转回 0~1 浮点；None 表示「不发送」。
        用于 from_user_config 及其它直接从 cfg 构造 AIClient 的场景，避免重复。
        """
        return dict(
            default_temperature=cfg.temperature / 100 if cfg.temperature is not None else None,
            default_top_p=cfg.top_p / 100 if cfg.top_p is not None else None,
            default_frequency_penalty=cfg.frequency_penalty / 100
            if cfg.frequency_penalty is not None
            else None,
            default_presence_penalty=cfg.presence_penalty / 100
            if cfg.presence_penalty is not None
            else None,
            default_max_tokens=cfg.max_tokens,
        )

    @classmethod
    async def from_user_config(cls, db, user_id: int) -> "AIClient":
        """从用户配置创建客户端（查找用户默认 AI 模型）。

        会把 AIModelConfig 的 temperature/top_p/penalty 挂到实例作为默认值，
        使所有走本方法的调用路径（skill 流水线、project_init、inspiration、ai_tools 等）
        自动读取用户在 AI 设置页配的参数。

        Raises:
            ValueError: 用户未配置任何 AI 模型
        """
        try:
            from sqlalchemy import select

            from app.models.ai_model import AIModelConfig

            result = await db.execute(
                select(AIModelConfig).where(
                    AIModelConfig.user_id == user_id,
                    AIModelConfig.is_default == True,
                )
            )
            cfg = result.scalar_one_or_none()
            if cfg:
                return cls(
                    base_url=cfg.base_url,
                    api_key=cfg.api_key,
                    model=cfg.model,
                    provider=cfg.provider or cfg.backend_type or "openai",
                    embedding_model=cfg.embedding_model or "",
                    reasoning_model=cfg.reasoning_model or False,
                    reasoning_effort=cfg.reasoning_effort or "low",
                    **cls._defaults_from_cfg(cfg),
                )
            # 无默认模型，尝试取任意一个
            result = await db.execute(
                select(AIModelConfig).where(AIModelConfig.user_id == user_id).limit(1)
            )
            cfg = result.scalar_one_or_none()
            if cfg:
                return cls(
                    base_url=cfg.base_url,
                    api_key=cfg.api_key,
                    model=cfg.model,
                    provider=cfg.provider or cfg.backend_type or "openai",
                    embedding_model=cfg.embedding_model or "",
                    reasoning_model=cfg.reasoning_model or False,
                    reasoning_effort=cfg.reasoning_effort or "low",
                    **cls._defaults_from_cfg(cfg),
                )
        except Exception:
            pass
        raise ValueError("未配置 AI 模型。请在「AI 设置」中添加至少一个 AI 模型配置。")

    @property
    def client(self) -> AsyncOpenAI:
        if self._client is None:
            import httpx

            self._client = AsyncOpenAI(
                base_url=self.base_url,
                api_key=self.api_key or "dummy-key",
                timeout=httpx.Timeout(
                    float(settings.AI_TIMEOUT),
                    connect=float(settings.AI_CONNECT_TIMEOUT),
                ),
                max_retries=settings.AI_SDK_MAX_RETRIES,  # SDK 层不重试，由应用层统一控制，避免透明重试导致重复计费
            )
        return self._client

    async def chat(
        self,
        messages: list[dict],
        model: str = None,
        temperature: float = None,
        top_p: float = None,
        max_tokens: int = None,
        frequency_penalty: float = None,
        presence_penalty: float = None,
        response_format: dict = None,
        tools: list = None,
        tool_choice: str = None,
    ) -> dict:
        """非流式调用（支持 MCP 工具）"""
        start = time.time()
        kwargs = {
            "model": model or self.model,
            "messages": messages,
            "temperature": self._resolve_temperature(temperature),
            "top_p": self._resolve_top_p(top_p),
            "max_tokens": self._resolve_max_tokens(max_tokens),
        }
        # penalty 参数：显式传 > 实例默认（模型配置）> 不发送（兼容不支持的模型）
        eff_fp = (
            frequency_penalty if frequency_penalty is not None else self.default_frequency_penalty
        )
        eff_pp = presence_penalty if presence_penalty is not None else self.default_presence_penalty
        if eff_fp is not None:
            kwargs["frequency_penalty"] = eff_fp
        if eff_pp is not None:
            kwargs["presence_penalty"] = eff_pp
        if response_format:
            kwargs["response_format"] = response_format
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice or "auto"
        # 推理模型：强制 temperature=1，移除 top_p/penalty
        self._apply_reasoning(kwargs)
        try:
            resp = await self.client.chat.completions.create(**kwargs)
            message = resp.choices[0].message
            content = message.content or ""
            tool_calls = [
                tc.model_dump() if hasattr(tc, "model_dump") else tc
                for tc in (message.tool_calls or [])
            ]
            usage = resp.usage
            cached = 0
            if usage and hasattr(usage, 'prompt_tokens_details') and usage.prompt_tokens_details:
                cached = getattr(usage.prompt_tokens_details, 'cached_tokens', 0) or 0
            return {
                "content": content,
                "model": resp.model,
                "input_tokens": usage.prompt_tokens if usage else 0,
                "cached_tokens": cached,
                "output_tokens": usage.completion_tokens if usage else 0,
                "duration_ms": int((time.time() - start) * 1000),
                "tool_calls": tool_calls,
            }
        except Exception as e:
            return {
                "content": "",
                "error": str(e),
                "duration_ms": int((time.time() - start) * 1000),
            }

    async def chat_stream_collect(
        self,
        messages: list[dict],
        model: str = None,
        temperature: float = None,
        top_p: float = None,
        max_tokens: int = None,
        frequency_penalty: float = None,
        presence_penalty: float = None,
        response_format: dict = None,
        tools: list = None,
        tool_choice: str = None,
    ) -> dict:
        """流式调用，收集完整响应（含 tool_calls）。

        使用 stream=True 保持连接活跃，防止 Cloudflare/CDN 代理超时掐断。
        返回格式与 chat() 完全一致。
        """
        start = time.time()
        kwargs = {
            "model": model or self.model,
            "messages": messages,
            "temperature": self._resolve_temperature(temperature),
            "top_p": self._resolve_top_p(top_p),
            "max_tokens": self._resolve_max_tokens(max_tokens),
            "stream": True,
        }
        # penalty 参数：显式传 > 实例默认（模型配置）> 不发送（兼容不支持的模型）
        eff_fp = (
            frequency_penalty if frequency_penalty is not None else self.default_frequency_penalty
        )
        eff_pp = presence_penalty if presence_penalty is not None else self.default_presence_penalty
        if eff_fp is not None:
            kwargs["frequency_penalty"] = eff_fp
        if eff_pp is not None:
            kwargs["presence_penalty"] = eff_pp
        if response_format:
            kwargs["response_format"] = response_format
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice or "auto"
        # 推理模型：强制 temperature=1，移除 top_p/penalty
        self._apply_reasoning(kwargs)
        try:
            stream = await self.client.chat.completions.create(**kwargs)
            content_parts = []
            tool_call_buf: dict[int, dict] = {}  # index -> {id, name, arguments}
            model_name = model or self.model
            usage_info = None
            async for chunk in stream:
                if chunk.usage:
                    usage_info = chunk.usage
                if chunk.choices:
                    delta = chunk.choices[0].delta
                    if delta.content:
                        content_parts.append(delta.content)
                    if delta.tool_calls:
                        for tc in delta.tool_calls:
                            idx = tc.index
                            if idx not in tool_call_buf:
                                tool_call_buf[idx] = {
                                    "id": tc.id or "",
                                    "name": "",
                                    "arguments": "",
                                }
                            if tc.id:
                                tool_call_buf[idx]["id"] = tc.id
                            if tc.function:
                                if tc.function.name:
                                    tool_call_buf[idx]["name"] += tc.function.name
                                if tc.function.arguments:
                                    tool_call_buf[idx]["arguments"] += tc.function.arguments

            content = "".join(content_parts)
            tool_calls = []
            for idx in sorted(tool_call_buf.keys()):
                tc = tool_call_buf[idx]
                if tc["name"]:  # 有 name 才算有效 tool_call
                    tool_calls.append(
                        {
                            "index": idx,
                            "id": tc["id"],
                            "type": "function",
                            "function": {"name": tc["name"], "arguments": tc["arguments"]},
                        }
                    )

            cached = 0
            if usage_info and hasattr(usage_info, 'prompt_tokens_details') and usage_info.prompt_tokens_details:
                cached = getattr(usage_info.prompt_tokens_details, 'cached_tokens', 0) or 0

            return {
                "content": content,
                "model": model_name,
                "input_tokens": usage_info.prompt_tokens if usage_info else 0,
                "cached_tokens": cached,
                "output_tokens": usage_info.completion_tokens if usage_info else 0,
                "duration_ms": int((time.time() - start) * 1000),
                "tool_calls": tool_calls,
            }
        except Exception as e:
            return {
                "content": "",
                "error": str(e),
                "duration_ms": int((time.time() - start) * 1000),
            }

    async def chat_stream(
        self,
        messages: list[dict],
        model: str = None,
        temperature: float = None,
        top_p: float = None,
        max_tokens: int = None,
    ) -> AsyncGenerator[str, None]:
        """流式调用，yield 每个 token（用于章节生成等前端流式场景）"""
        kwargs = {
            "model": model or self.model,
            "messages": messages,
            "temperature": self._resolve_temperature(temperature),
            "top_p": self._resolve_top_p(top_p),
            "max_tokens": self._resolve_max_tokens(max_tokens),
            "stream": True,
        }
        # 推理模型：强制 temperature=1，移除 top_p/penalty
        self._apply_reasoning(kwargs)
        stream = await self.client.chat.completions.create(**kwargs)
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    async def chat_json(
        self,
        messages: list[dict],
        model: str = None,
        temperature: float = None,
        max_tokens: int = None,
        frequency_penalty: float = None,
        presence_penalty: float = None,
    ) -> dict:
        """调用并解析 JSON 响应（移植自 MuMuAINovel 的强清洗逻辑）"""
        import logging

        logger = logging.getLogger(__name__)
        result = await self.chat_stream_collect(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            frequency_penalty=frequency_penalty,
            presence_penalty=presence_penalty,
        )
        if result.get("error"):
            return result
        content = result["content"].strip()

        # 流式空内容兜底：推理模型（如 Kimi K2.6）可能把所有 token 用于 reasoning
        # 导致 content 为空。退到非流式重试一次，非流式 API 会正确分配 reasoning/content 配额。
        if not content and (result.get("output_tokens") or 0) > 0:
            logger.warning(
                f"[AI] 流式返回空内容（output_tokens={result.get('output_tokens')}），"
                f"回退到非流式重试..."
            )
            result = await self.chat(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                frequency_penalty=frequency_penalty,
                presence_penalty=presence_penalty,
            )
            if result.get("error"):
                return result
            content = result["content"].strip()

        # 记录每次 AI 调用的 token 消耗，便于排查重复计费
        cached = result.get("cached_tokens", 0)
        cache_pct = f" {cached}/{result.get('input_tokens', 0)}" if cached else ""
        logger.warning(
            f"[AI] model={result.get('model', '?')} "
            f"input={result.get('input_tokens', 0)}{' 缓存' + cache_pct if cached else ''} "
            f"output={result.get('output_tokens', 0)} "
            f"duration={result.get('duration_ms', 0)}ms content_len={len(content)}"
        )

        # 先尝试解析 JSON。如果短内容（如 "[]" "{}"）能解析成功，不应拒绝。
        from app.services.json_helper import clean_json_response, parse_json

        try:
            cleaned = clean_json_response(content)
            parsed = parse_json(cleaned)
            if parsed is not None:
                result["json"] = parsed
                return result
        except Exception:
            pass
        # 响应过短且无法解析：AI 未返回有效 JSON（通常是上下文溢出或模型异常）
        if len(content) < 20:
            result["json"] = None
            result["error"] = f"AI 返回内容过短（{len(content)}字符），无法解析为 JSON"
            return result

        # 用原项目的强清洗逻辑：中文标点、未转义引号、markdown、json5 兜底
        try:
            cleaned = clean_json_response(content)
            parsed = parse_json(cleaned)
            if parsed is not None:
                result["json"] = parsed
                return result
        except Exception as e:
            parse_error = str(e)
        else:
            parse_error = "无法解析 AI 返回的 JSON"

        # 解析失败：统一写入 error，让上层 if result.get("error") 能兜底
        result["json"] = None
        result["parse_error"] = parse_error
        result["error"] = f"AI 返回内容无法解析为 JSON：{parse_error}"
        return result

    async def chat_json_retry(
        self,
        messages: list[dict],
        model: str = None,
        temperature: float = None,
        max_tokens: int = None,
        frequency_penalty: float = None,
        presence_penalty: float = None,
        max_retries: int = None,
    ) -> dict:
        """带重试的 JSON 调用：解析失败时最多重试 max_retries 次。

        重试策略（移植自 MuMuAINovel call_with_json_retry）：
        - 仅对「JSON 解析失败」重试；AI 调用本身报错（如 401/网络）不重试。
        - 每次重试在 messages 末尾追加格式强化提示，并把上次失败内容反馈给 AI。
        """
        import logging

        logger = logging.getLogger(__name__)
        if max_retries is None:
            max_retries = settings.AI_MAX_RETRIES
        hint_messages = list(messages)
        last_result = None
        total_input_tokens = 0
        total_output_tokens = 0
        for attempt in range(1, max_retries + 1):
            last_result = await self.chat_json(
                messages=hint_messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                frequency_penalty=frequency_penalty,
                presence_penalty=presence_penalty,
            )
            total_input_tokens += last_result.get("input_tokens", 0)
            total_output_tokens += last_result.get("output_tokens", 0)
            # 成功（有 json 数据，且无 error）→ 直接返回
            if last_result.get("json") is not None and not last_result.get("error"):
                if attempt > 1:
                    last_result["retries"] = attempt - 1
                    logger.warning(
                        f"[AI] JSON解析在第{attempt}次尝试后成功，"
                        f"共消耗 input={total_input_tokens} output={total_output_tokens} tokens"
                    )
                return last_result

            # AI 调用本身的错误
            # 连接错误（Connection error / 504 Gateway / Cloudflare）也重试，其他错误（401/权限）不重试
            err_msg = last_result.get("error") or ""
            err_lower = err_msg.lower()
            is_conn_error = (
                "connection" in err_lower
                or "timeout" in err_lower
                or "time-out" in err_lower
                or "gateway" in err_lower
                or "504" in err_lower
            )
            if (
                last_result.get("error")
                and last_result.get("json") is None
                and not last_result.get("parse_error")
                and not is_conn_error
            ):
                return last_result
            if is_conn_error and attempt < max_retries:
                delay = min(settings.AI_RETRY_DELAY * attempt, settings.AI_RETRY_MAX_DELAY)
                logger.warning(
                    f"[AI] 连接错误，{delay}s后重试 (attempt {attempt}/{max_retries}): {err_msg[:200]}"
                )
                await asyncio.sleep(delay)
                continue

            # JSON 解析失败 → 准备重试（最后一次也跳出）
            if attempt < max_retries:
                bad_content = (last_result.get("content") or "")[:500]
                logger.warning(
                    f"[AI] JSON解析失败，准备重试 (attempt {attempt}/{max_retries})，"
                    f"input={total_input_tokens} output={total_output_tokens}，"
                    f"失败内容预览: {bad_content[:200]}"
                )
                hint_messages = list(messages) + [
                    {
                        "role": "user",
                        "content": (
                            f"⚠️ 上次返回的内容无法解析为合法 JSON，请严格只返回纯 JSON（不要 markdown 代码块、"
                            f"不要解释文字、所有 key 和字符串必须用英文双引号）。\n"
                            f"上次失败内容预览：\n{bad_content}"
                        ),
                    }
                ]
        return last_result

    async def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        tool_executor,
        model: str = None,
        temperature: float = None,
        max_tokens: int = None,
        max_rounds: int = 3,
        post_tool_messages: list[dict] = None,
    ) -> dict:
        """带工具调用的聊天循环（对标 MuMu _handle_tool_calls）。

        流程：
        1. 调 chat(messages, tools=tools, tool_choice="auto")
        2. 如果有 tool_calls → 执行每个工具 → 追加 tool 消息 → 续调
        3. 最多 max_rounds 轮，最后一轮强制 tool_choice="none"
        4. 返回最终正文

        Args:
            messages: 初始消息列表（system + user）
            tools: OpenAI function calling 格式的工具定义
            tool_executor: async def(tool_name, arguments_dict) -> str
            max_tokens: None → 走 _resolve_max_tokens（用户 AI 设置 > settings 默认）
            max_rounds: 最大工具调用轮数（默认3，含最后一轮强制输出）
        """
        import json
        import logging

        logger = logging.getLogger(__name__)

        # 注入工具调用预算提示，让 AI 合理规划查询
        tool_rounds = max_rounds - 1
        budget_hint = {
            "role": "system",
            "content": (
                f"【工具调用预算】你最多有 {tool_rounds} 轮工具调用机会（每轮可同时调多个工具）。"
                f"第 {max_rounds} 轮你必须直接输出最终结果，不能再调用工具。"
                f"如果你已获得足够信息，可以提前输出，不必用完所有轮次。\n"
                f"建议：如果第一轮查询了信息，第二轮就直接输出结果，不要反复查询。\n"
                f"⚠️ 重要：如果某次查询返回「未找到」或空结果，说明该数据确实不存在，不要换关键词反复查同类数据。直接基于已有信息继续。"
            ),
        }
        current_messages = [budget_hint] + list(messages)
        post_tool_inserted = False
        tool_call_history: list[dict] = []  # 记录所有工具调用（名称+参数），供上层校验

        for round_num in range(max_rounds):
            is_last_round = round_num == max_rounds - 1
            tool_choice = "none" if is_last_round else "auto"
            actual_tools = None if is_last_round else tools

            result = await self.chat_stream_collect(
                messages=current_messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=actual_tools,
                tool_choice=tool_choice,
            )

            if result.get("error"):
                result["tool_call_history"] = tool_call_history
                return result

            tool_calls = result.get("tool_calls") or []
            content = result.get("content") or ""

            # 兼容各模型返回工具调用的不同格式
            if not tool_calls and content:
                parsed = _try_parse_inline_tool_calls(content)
                if parsed:
                    tool_calls = parsed
                    content = ""

            # 没有工具调用 → 返回正文
            if not tool_calls:
                # 推理模型可能输出过短（推理消耗大量 token 后正文被截断）
                # 如果有内容但太短，且不是最后一轮，给它一次无工具重试机会
                min_output = 2000  # 正文至少 ~2000 token（约 1300 字）
                if content and len(content) < min_output and not is_last_round:
                    logger.warning(
                        f"[tools] 正文过短（{len(content)} 字符），可能推理模型 token 分配异常，"
                        f"强制无工具重试..."
                    )
                    retry = await self.chat_stream_collect(
                        messages=current_messages
                        + [
                            {
                                "role": "system",
                                "content": "请直接输出完整正文，不要调用工具。内容不足会判定失败，请确保写够目标字数。",
                            },
                        ],
                        model=model,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        tool_choice="none",
                    )
                    if not retry.get("error") and (retry.get("content") or ""):
                        retry["tool_call_history"] = tool_call_history
                        return retry
                result["tool_call_history"] = tool_call_history
                return result

            # 有工具调用 → 执行并追加消息
            logger.info(
                f"[tools] 第{round_num + 1}轮: AI 调用了 {len(tool_calls)} 个工具: {[tc.get('function', {}).get('name', '?') for tc in tool_calls]}"
            )

            # 追加 assistant 的 tool_calls 消息
            current_messages.append(
                {
                    "role": "assistant",
                    "content": content,
                    "tool_calls": tool_calls,
                }
            )

            # 执行每个工具，追加 tool 结果消息
            for tc in tool_calls:
                func = tc.get("function", {})
                tool_name = func.get("name", "")
                try:
                    args = json.loads(func.get("arguments", "{}"))
                except Exception:
                    args = {}

                tool_result = await tool_executor(tool_name, args)
                tool_call_history.append({"name": tool_name, "arguments": args})
                current_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.get("id", ""),
                        "content": tool_result,
                    }
                )

            # 首次工具调用完成后，注入延迟消息（如写作指导）
            if not post_tool_inserted and post_tool_messages:
                current_messages.extend(post_tool_messages)
                post_tool_inserted = True

            # 最后一轮：模型无视 tool_choice=none 仍调了工具，再给它一次机会强制输出
            if is_last_round:
                final = await self.chat_stream_collect(
                    messages=current_messages,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    tool_choice="none",  # 防止模型再次调用工具
                )
                final["tool_call_history"] = tool_call_history
                return final

        # 兜底
        return {
            "content": "",
            "error": "工具调用超过最大轮数",
            "tool_call_history": tool_call_history,
        }

    async def embed(self, texts, model: str = None) -> dict:
        """调用 embedding API 生成向量（用于记忆向量检索）。

        Args:
            texts: 单个字符串或字符串列表
            model: embedding 模型名（默认用 self.embedding_model 或 text-embedding-3-small）

        Returns:
            {"vectors": [[...], ...], "model": ..., "error": None/str}
            单条输入时 vectors 仍是 list[list[float]]，调用方取 [0]
        """
        start = time.time()
        if isinstance(texts, str):
            inputs = [texts]
        else:
            inputs = list(texts)
        # 批量上限：OpenAI embedding 接口建议单次 ≤ 2048，这里保守 100
        MAX_BATCH = 100
        all_vectors = []
        emb_model = model or self.embedding_model or "text-embedding-3-small"
        try:
            for i in range(0, len(inputs), MAX_BATCH):
                batch = inputs[i : i + MAX_BATCH]
                resp = await self.client.embeddings.create(
                    model=emb_model,
                    input=batch,
                )
                all_vectors.extend([d.embedding for d in resp.data])
            return {
                "vectors": all_vectors,
                "model": emb_model,
                "count": len(all_vectors),
                "duration_ms": int((time.time() - start) * 1000),
            }
        except Exception as e:
            return {
                "vectors": [],
                "model": emb_model,
                "error": str(e),
                "duration_ms": int((time.time() - start) * 1000),
            }

    async def embed_one(self, text: str, model: str = None) -> list[float]:
        """便捷方法：单条文本转向量，失败返回空列表。"""
        r = await self.embed(text, model=model)
        if r.get("error") or not r.get("vectors"):
            return []
        return r["vectors"][0]


# 全局默认客户端
default_client = AIClient()
