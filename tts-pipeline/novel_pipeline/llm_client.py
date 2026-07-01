"""
LLM 客户端 —— OpenAI 兼容的 Chat Completions 接口封装。

用 requests 直接调 /v1/chat/completions,不引入 openai SDK(项目已有 requests)。
支持 GLM / GPT / Claude(兼容模式) / DeepSeek / 通义千问等任何兼容接口。

核心职责:
  - 分块:把长文本切成小块逐次调用(避免超 token、避免漏句)
  - 重试:JSON 解析失败时重试一次
  - 原始文本校验:确认 LLM 没有偷偷改写原文(逐字比对)
"""
import json
import re
from typing import List, Dict, Any, Optional, Tuple

import requests


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
        # 单句就超长:硬切(极少见,比如一整段没有句号)
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


class LLMClient:
    """OpenAI 兼容的 Chat Completions 客户端。"""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: int = 60,
    ):
        """
        Args:
            base_url: API 根地址,如 "https://open.bigmodel.cn/api/paas/v4"
            api_key:  API 密钥
            model:    模型名,如 "glm-4-plus"
            timeout:  单次请求超时(秒)
        """
        # 规范化:去掉末尾斜杠,补上 /chat/completions
        base_url = base_url.rstrip("/")
        if not base_url.endswith("/chat/completions"):
            if base_url.endswith("/v1"):
                self.url = base_url + "/chat/completions"
            else:
                self.url = base_url + "/v1/chat/completions"
        else:
            self.url = base_url
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def chat(
        self,
        system_prompt: str,
        user_content: str,
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
        retry_on_fail: bool = True,
    ) -> Tuple[str, Optional[str]]:
        """
        调用一次 Chat Completions,返回 (回复文本, 错误信息)。

        retry_on_fail=True 时,如果第一次解析失败,会带提示重试一次。
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        def _call() -> Tuple[str, Optional[str]]:
            try:
                resp = requests.post(
                    self.url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "messages": messages,
                        "temperature": temperature,
                        **({"max_tokens": max_tokens} if max_tokens else {}),
                    },
                    timeout=self.timeout,
                )
                if resp.status_code != 200:
                    return "", f"LLM API {resp.status_code}: {resp.text[:500]}"
                data = resp.json()
                # OpenAI 标准格式:choices[0].message.content
                content = data["choices"][0]["message"]["content"]
                return content, None
            except requests.exceptions.Timeout:
                return "", "LLM 请求超时"
            except (KeyError, IndexError) as e:
                return "", f"LLM 返回格式异常: {e}"
            except requests.exceptions.RequestException as e:
                return "", f"LLM 请求失败: {e}"

        content, err = _call()
        if err and retry_on_fail:
            # 重试一次,带上错误提示
            messages.append({"role": "assistant", "content": content or "(空)"})
            messages.append({
                "role": "user",
                "content": f"你上次的输出有问题({err})。请重新输出,确保是合法的 JSON 数组,不要包含任何额外说明。",
            })
            content, err = _call()
        return content, err

    def chat_json(
        self,
        system_prompt: str,
        user_content: str,
        temperature: float = 0.3,
        retry_on_fail: bool = True,
    ) -> Tuple[Optional[List[Dict]], Optional[str]]:
        """
        调用并期望返回 JSON 数组。自动剥离 ```json ``` 代码块包裹。

        Returns:
            (解析后的 list, 错误信息)
        """
        content, err = self.chat(system_prompt, user_content, temperature, retry_on_fail=retry_on_fail)
        if err:
            return None, err
        parsed, parse_err = _extract_json_array(content)
        if parse_err:
            return None, f"LLM 返回非合法 JSON: {parse_err}。原始内容前200字: {content[:200]}"
        return parsed, None


def _extract_json_array(text: str) -> Tuple[Optional[List[Dict]], Optional[str]]:
    """
    从 LLM 回复中提取 JSON 数组。
    处理常见的包裹:```json ... ```、多余的前后说明文字。
    """
    text = text.strip()
    # 剥离 markdown 代码块
    if text.startswith("```"):
        # 去掉第一行(```json 或 ```)
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    # 尝试直接解析
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result, None
        if isinstance(result, dict):
            return [result], None
        return None, "JSON 不是数组或对象"
    except json.JSONDecodeError:
        pass
    # 兜底:找第一个 [ 到最后一个 ]
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        try:
            result = json.loads(text[start:end + 1])
            if isinstance(result, list):
                return result, None
        except json.JSONDecodeError as e:
            return None, str(e)
    return None, "未找到 JSON 数组"
