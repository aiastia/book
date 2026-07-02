"""JSON 处理工具类"""

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


def safe_preview(text, length=200):
    """安全的文本预览（用于日志）"""
    if not text:
        return ""
    try:
        preview = str(text)[:length]
        return preview + ("..." if len(str(text)) > length else "")
    except Exception:
        return ""


try:
    import json5

    HAS_JSON5 = True
except ImportError:
    HAS_JSON5 = False


# json5 为主解析器，标准 json 为降级
def _try_loads(text: str) -> Any:
    """尝试解析 JSON 文本：json5 优先，标准 json 降级。返回解析结果，失败抛异常。"""
    if HAS_JSON5:
        try:
            return json5.loads(text)
        except Exception:
            pass
    return json.loads(text)


# 中文引号/括号到ASCII的映射
_QUOTE_MAP = {
    "\u201c": '"',  # " → "
    "\u201d": '"',  # " → "
    "\u2018": "'",  # ' → '
    "\u2019": "'",  # ' → '
    "\u300e": '"',  # 『 → "
    "\u300f": '"',  # 』 → "
    "\u300c": '"',  # 「 → "
    "\u300d": '"',  # 」 → "
}


def _is_content_quote(text: str, pos: int) -> bool:
    """
    判断字符串值内的 '"' 是否为内容引号（需转义）而非 JSON 结束引号。

    合法 JSON 中，字符串结束引号之后的非空白字符必须是：
    ',' (值分隔) / '}' (关闭对象) / ']' (关闭数组)

    如果 '"' 后面不符合这些模式，则是 AI 写入的内容引号，需要转义。
    """
    j = pos + 1

    # 跳过空格和制表符
    while j < len(text) and text[j] in " \t":
        j += 1

    if j >= len(text):
        return False  # 文本末尾，视为结束引号

    ch = text[j]

    # } 或 ] → 结束引号
    if ch in ("}", "]"):
        return False

    # 换行 → 检查下一行开头判断
    if ch == "\n" or ch == "\r":
        k = j + (2 if (ch == "\r" and j + 1 < len(text) and text[j + 1] == "\n") else 1)
        while k < len(text) and text[k] in " \t":
            k += 1
        if k >= len(text):
            return False
        # 下一行以 " (JSON key) 或 } 或 ] 开头 → 结束引号
        if text[k] == '"' or text[k] in ("}", "]"):
            return False
        return True

    # , → 需要检查逗号后面是什么
    if ch == ",":
        k = j + 1
        while k < len(text) and text[k] in " \t":
            k += 1

        if k >= len(text):
            return False

        # 逗号后跟换行 → 检查下一行
        if text[k] in ("\n", "\r"):
            k2 = k + (2 if (text[k] == "\r" and k + 1 < len(text) and text[k + 1] == "\n") else 1)
            while k2 < len(text) and text[k2] in " \t\n\r":
                k2 += 1
            if k2 >= len(text):
                return False
            if text[k2] == '"' or text[k2] in ("}", "]"):
                return False
            return True

        after_comma = text[k]

        # 结构性逗号后应为 JSON 值的开头
        if after_comma == '"':
            return False  # 字符串值或 key
        if after_comma.isdigit() or after_comma == "-":
            return False  # 数字
        if after_comma in ("{", "["):
            return False  # 对象/数组
        if text[k : k + 4] in ("true", "null"):
            return False
        if text[k : k + 5] == "false":
            return False

        # 逗号后不是 JSON 值开头 → 内容逗号，引号是内容引号
        return True

    # : → 通常在字符串结束后不可能出现，保守处理为结束引号
    if ch == ":":
        return False

    # 其他字符（中文、字母等）→ 内容引号
    return True


def _fix_unclosed_strings(text: str) -> str:
    """
    修复 AI 输出中未闭合的 JSON 字符串值。

    常见场景：AI 在字符串内写入裸换行或对话内容，导致字符串未正常闭合，
    后续的 JSON 结构（}、,、"key"）被吞入字符串值内。

    策略：追踪引号边界，当检测到字符串未闭合时（遇到结构性元素而仍在字符串内），
    在适当位置插入闭合引号。
    """
    if not text or '"' not in text:
        return text

    result = []
    i = 0
    in_string = False
    fixed = 0

    while i < len(text):
        c = text[i]

        # 处理转义序列
        if c == '\\' and in_string and i + 1 < len(text):
            result.append(c)
            result.append(text[i + 1])
            i += 2
            continue

        # 处理引号
        if c == '"':
            if in_string:
                # 检查引号后是否跟结构性字符（, } ]），确认这是结束引号
                j = i + 1
                while j < len(text) and text[j] in ' \t':
                    j += 1
                if j < len(text) and text[j] in (',', '}', ']', '\n', '\r'):
                    in_string = False
                    result.append(c)
                    i += 1
                    continue
                # 引号后是内容字符（中文、字母等），这是内容引号
                result.append('\\')
                result.append('"')
                fixed += 1
                i += 1
                continue
            else:
                # 进入字符串
                in_string = True
                result.append(c)
                i += 1
                continue

        # 在字符串内遇到结构性元素 → 字符串未闭合，先闭合它
        if in_string and c in ('}', ']', ','):
            # 向前看：如果是 }, 或 ], 或 , 后跟 "key" → 确定是结构元素
            k = i + 1
            while k < len(text) and text[k] in ' \t\n\r':
                k += 1
            if k >= len(text) or text[k] in ('}', ']', '"'):
                result.append('"')
                fixed += 1
                in_string = False
                # 不消耗当前字符，重新处理
                continue

        if in_string:
            result.append(c)
            i += 1
            continue

        # 字符串外：正常处理
        result.append(c)
        i += 1

    # 如果字符串仍未闭合（文本末尾），补上闭合引号
    if in_string:
        result.append('"')
        fixed += 1

    if fixed > 0:
        logger.info(f"✅ 关闭了{fixed}个未闭合的JSON字符串")

    return ''.join(result)


def _fix_json_string_values(text: str) -> str:
    """
    上下文感知的 JSON 修复，区分字符串内外分别处理。

    字符串值内：
    1. 裸换行符/制表符 → 转义
    2. 中文引号（""等） → 转义为 \\"
    3. 未转义的 ASCII 双引号 → 智能检测：内容引号转义，结束引号保留
    4. 中文逗号/冒号 → 保留原样（是内容字符）

    结构位置（字符串外）：
    1. 中文引号 → ASCII 引号
    2. 中文逗号 → ASCII 逗号
    3. 中文冒号 → ASCII 冒号
    """
    if not text or '"' not in text:
        return text

    result = []
    i = 0
    in_string = False
    fixed_count = 0

    while i < len(text):
        c = text[i]

        # === 非字符串内（结构位置）===
        if not in_string:
            # 结构位置的反斜杠：\" 是 AI 错误转义的结构引号，直接解转为 "
            if c == "\\" and i + 1 < len(text) and text[i + 1] == '"':
                result.append('"')
                fixed_count += 1
                i += 2
                continue
            # 结构位置的中文标点 → ASCII
            if c == "\uff0c":  # ，→ ,
                result.append(",")
                fixed_count += 1
                i += 1
                continue
            if c == "\uff1a":  # ：→ :
                result.append(":")
                fixed_count += 1
                i += 1
                continue
            if c in _QUOTE_MAP:
                result.append(_QUOTE_MAP[c])
                fixed_count += 1
                i += 1
                continue

            # ASCII 双引号 → 进入字符串
            if c == '"':
                in_string = True
                result.append(c)
                i += 1
                continue

            result.append(c)
            i += 1
            continue

        # === 字符串值内 ===

        # 转义字符处理
        if c == "\\":
            if i + 1 < len(text):
                next_c = text[i + 1]
                if next_c in ('"', "\\", "/", "b", "f", "n", "r", "t"):
                    result.append(c)
                    result.append(next_c)
                    i += 2
                    continue
                elif next_c == "u":
                    if i + 5 < len(text) and all(
                        text[i + 2 + k] in "0123456789abcdefABCDEF" for k in range(4)
                    ):
                        result.append(text[i : i + 6])
                        i += 6
                        continue
                    else:
                        result.append(next_c)
                        fixed_count += 1
                        i += 2
                        continue
                else:
                    result.append(next_c)
                    fixed_count += 1
                    i += 2
                    continue
            else:
                fixed_count += 1
                i += 1
                continue

        # ASCII 双引号 → 智能判断是结束引号还是内容引号
        if c == '"':
            if _is_content_quote(text, i):
                # 内容引号，需要转义
                result.append("\\")
                result.append('"')
                fixed_count += 1
                i += 1
                continue
            else:
                # 结束引号
                in_string = False
                result.append(c)
                i += 1
                continue

        # 裸换行符 → 转义
        if c == "\n":
            result.append("\\")
            result.append("n")
            fixed_count += 1
            i += 1
            continue

        if c == "\r":
            if i + 1 < len(text) and text[i + 1] == "\n":
                result.append("\\")
                result.append("n")
                fixed_count += 1
                i += 2
            else:
                result.append("\\")
                result.append("n")
                fixed_count += 1
                i += 1
            continue

        if c == "\t":
            result.append("\\")
            result.append("t")
            fixed_count += 1
            i += 1
            continue

        # 中文引号处理
        if c in _QUOTE_MAP:
            mapped = _QUOTE_MAP[c]
            if mapped == '"':
                # 中文双引号在字符串内需要转义
                result.append("\\")
                result.append('"')
            else:
                # 中文单引号在双引号字符串内不需要转义，直接替换
                result.append(mapped)
            fixed_count += 1
            i += 1
            continue

        # 其他字符（包括中文逗号、中文冒号）→ 保留原样
        result.append(c)
        i += 1

    if fixed_count > 0:
        logger.debug(f"✅ 修复了{fixed_count}个JSON问题（引号/控制字符/中文标点）")

    return "".join(result)


def _fix_all_invalid_escapes(text: str) -> str:
    """
    兜底修复：扫描整个文本中的无效JSON转义序列。

    当 _fix_json_string_values 因字符串边界追踪错误而遗漏某些无效转义时，
    此函数作为兜底，不依赖字符串状态追踪，扫描整个文本修复所有无效转义。

    有效JSON转义：\\" \\\\ \\/ \\b \\f \\n \\r \\t \\uXXXX
    其他 \\X 均为无效转义，修复方式为去掉反斜杠只保留字符。
    """
    if "\\" not in text:
        return text

    result = []
    i = 0
    fixed = 0

    while i < len(text):
        if text[i] == "\\" and i + 1 < len(text):
            next_c = text[i + 1]
            if next_c in ('"', "\\", "/", "b", "f", "n", "r", "t"):
                # 有效转义，保留
                result.append(text[i])
                result.append(next_c)
                i += 2
                continue
            elif next_c == "u":
                # Unicode 转义，检查是否有4个十六进制字符
                if i + 5 < len(text) and all(
                    text[i + 2 + k] in "0123456789abcdefABCDEF" for k in range(4)
                ):
                    result.append(text[i : i + 6])
                    i += 6
                    continue
                else:
                    # 不完整的unicode转义，去掉反斜杠
                    result.append(next_c)
                    fixed += 1
                    i += 2
                    continue
            else:
                # 无效转义（如 \引 \影 \某种 等），去掉反斜杠只保留字符
                result.append(next_c)
                fixed += 1
                i += 2
                continue
        else:
            result.append(text[i])
            i += 1

    if fixed > 0:
        logger.info(f"✅ 兜底修复了{fixed}个无效JSON转义序列")

    return "".join(result)


def _fix_unescaped_quotes_by_error(text: str, max_fixes: int = 50) -> str:
    """
    基于 json.JSONDecodeError 的错误位置，迭代修复未转义的引号。

    当 _fix_json_string_values 的启发式判断失败时（_is_content_quote 误判），
    此函数利用 JSON 解析器提供的精确错误位置来定位问题并修复。

    常见场景：AI 在字符串值内写入 "content", "more content" 这样的模式，
    _is_content_quote 可能将其误判为结构引号，导致字符串提前终止。

    修复策略：在错误位置前找到最近的未转义引号，将其转义。
    """
    for _ in range(max_fixes):
        try:
            json.loads(text)
            return text  # 解析成功
        except json.JSONDecodeError as e:
            if e.pos is None or e.pos >= len(text):
                break

            pos = e.pos

            # 从错误位置向前搜索最近的未转义引号
            # 跳过空格和换行
            search_pos = pos - 1
            while search_pos >= 0 and text[search_pos] in " \t\n\r":
                search_pos -= 1

            if search_pos < 0:
                break

            # 如果错误位置的字符是引号（Unexpected '"'），直接转义它
            if text[search_pos] == '"':
                # 检查是否已被转义
                num_bs = 0
                k = search_pos - 1
                while k >= 0 and text[k] == "\\":
                    num_bs += 1
                    k -= 1
                if num_bs % 2 == 0:
                    # 未转义的引号，转义它
                    text = text[:search_pos] + '\\"' + text[search_pos + 1 :]
                    logger.debug(f"   🔧 在位置 {search_pos} 转义了未转义的引号")
                    continue

            # 否则从错误位置向前找引号
            found = False
            for j in range(pos - 1, max(0, pos - 500), -1):
                if text[j] == '"':
                    num_bs = 0
                    k = j - 1
                    while k >= 0 and text[k] == "\\":
                        num_bs += 1
                        k -= 1
                    if num_bs % 2 == 0:
                        text = text[:j] + '\\"' + text[j + 1 :]
                        logger.debug(f"   🔧 在位置 {j} 转义了未转义的引号（向前搜索）")
                        found = True
                        break
            if found:
                continue

            # 无法修复
            logger.debug(f"   ⚠️ 无法定位可修复的引号，错误位置: {pos}")
            break

    return text


def _fix_missing_commas(text: str) -> str:
    """
    补全对象/数组中属性之间缺失的逗号。

    AI 常见错误：两行字符串值之间少了逗号，如：
        "key1": "value1"
        "key2": "value2"
    修复为：
        "key1": "value1",
        "key2": "value2"
    """
    if not text or "," in text:
        # 有逗号大概率没问题，快速跳过
        # 但还是要检查：逗号可能在数组/对象外部，所以做个简单扫描
        pass

    lines = text.split("\n")
    result = []
    for i, line in enumerate(lines):
        stripped = line.rstrip()
        # 匹配一行 JSON 值（key: "value" 或 "value"）
        # 如果此行以字符串值结尾（引号闭合），且下一行以 key（"xxx":）或数组项（"xxx"）开头
        if (i + 1 < len(lines)
            and stripped.endswith('"')
            and not stripped.endswith('\\"')
            and not stripped.endswith(',')
        ):
            next_stripped = lines[i + 1].lstrip()
            # 下一行以引号开头 → 大概率是另一个 key 或数组项
            if next_stripped.startswith('"'):
                result.append(stripped + ",")
                continue
        result.append(stripped)
        # 保留原换行
        if i < len(lines) - 1:
            result.append("\n")
    return "".join(result)


def _fix_multiple_objects_as_value(text: str) -> str:
    """
    修复AI生成的JSON中，多个对象作为属性值但未合并的问题。

    示例：
        "key": {"a": "1"}, {"b": "2"}  →  "key": {"a": "1", "b": "2"}

    AI有时在输出对象类型的属性值时，输出了多个独立的对象而不是合并为一个。
    例如 relationship_changes 字段输出多个角色关系变化时可能出现此问题。
    此函数检测并合并这些对象。
    """
    if "{" not in text or "}" not in text:
        return text

    # 匹配嵌套层级不超过2的对象: { ... } 其中 ... 不含 { 或仅含单层嵌套
    nested_obj = r"\{(?:[^{}]|\{(?:[^{}]|\{[^{}]*\})*\})*\}"

    # 模式：属性冒号后跟一个对象，然后逗号和另一个对象（没有属性名）
    # 即 "key": {obj1}, {obj2} → "key": {obj1, obj2}
    pattern = r'(":)\s*(' + nested_obj + r")\s*,\s*(" + nested_obj + r")"

    def merge_objects(match):
        colon = match.group(1)
        obj1_content = match.group(2)[1:-1]  # 去掉外层的 { }
        obj2_content = match.group(3)[1:-1]  # 去掉外层的 { }
        # 合并为一个对象
        return f"{colon} {{{obj1_content}, {obj2_content}}}"

    prev = None
    count = 0
    max_iterations = 10
    while prev != text and count < max_iterations:
        prev = text
        text = re.sub(pattern, merge_objects, text)
        count += 1

    if count > 1:
        logger.info(f"✅ 修复了{count - 1}处多对象属性值合并")

    return text


def _fix_unquoted_keys(text: str) -> str:
    """修复未加引号的 JSON key（AI 常见错误：{key: value} → {"key": value}）。

    也处理单引号 key/value: {'key': 'value'} → {"key": "value"}
    """
    if not text or "{" not in text:
        return text

    # 策略：逐字符扫描，区分字符串内外，替换未引号 key 和单引号字符串
    result = []
    i = 0
    n = len(text)
    in_double = False
    in_single = False
    # 状态：0=正常, 1=在对象中刚看到{或,需要key
    expect_key = False
    depth = 0

    while i < n:
        ch = text[i]

        if in_double:
            result.append(ch)
            if ch == "\\" and i + 1 < n:
                i += 1
                result.append(text[i])
            elif ch == '"':
                in_double = False
            i += 1
            continue

        if in_single:
            # 单引号字符串 → 转为双引号
            if ch == "\\" and i + 1 < n:
                result.append("\\")
                i += 1
                result.append(text[i])
            elif ch == "'":
                result.append('"')
                in_single = False
            else:
                result.append(ch)
            i += 1
            continue

        # 不在字符串内
        if ch == '"':
            result.append(ch)
            in_double = True
            i += 1
            continue

        if ch == "'":
            # 判断是否是 key 位置的单引号
            if expect_key:
                result.append('"')
                in_single = True
                i += 1
                continue
            else:
                # 可能是单引号字符串值
                result.append('"')
                in_single = True
                i += 1
                continue

        if ch == "{":
            result.append(ch)
            depth += 1
            expect_key = True
            i += 1
            continue

        if ch == "}":
            result.append(ch)
            depth -= 1
            i += 1
            continue

        if ch == ",":
            result.append(ch)
            if depth > 0:
                expect_key = True
            i += 1
            continue

        if ch == ":":
            result.append(ch)
            expect_key = False
            i += 1
            continue

        # 空白字符
        if ch in " \t\n\r":
            result.append(ch)
            i += 1
            continue

        # 如果在 expect_key 状态且遇到字母/数字/下划线/中文 → 未引号 key
        if expect_key and (ch.isalpha() or ch == "_" or ch == "$" or ord(ch) > 127):
            result.append('"')
            while i < n and (text[i].isalnum() or text[i] in "_-$." or ord(text[i]) > 127):
                result.append(text[i])
                i += 1
            result.append('"')
            expect_key = False
            # 跳过冒号前的空白
            while i < n and text[i] in " \t\n\r":
                i += 1
            if i < n and text[i] == ":":
                result.append(":")
                i += 1
            continue

        result.append(ch)
        i += 1

    return "".join(result)


def clean_json_response(text: str) -> str:
    """清洗 AI 返回的 JSON（改进版 - 流式安全）"""
    try:
        if not text:
            logger.warning("⚠️ clean_json_response: 输入为空")
            return text

        original_length = len(text)
        logger.debug(f"🔍 开始清洗JSON，原始长度: {original_length}")

        # 去除 markdown 代码块
        text = re.sub(r"^```json\s*\n?", "", text, flags=re.MULTILINE | re.IGNORECASE)
        text = re.sub(r"^```\s*\n?", "", text, flags=re.MULTILINE)
        text = re.sub(r"\n?```\s*$", "", text, flags=re.MULTILINE)
        text = text.strip()

        if len(text) != original_length:
            logger.debug(f"   移除markdown后长度: {len(text)}")

        # 快速路径：原始文本用 json5 直接解析（json5 容错强，跳过清洗避免误伤）
        try:
            _try_loads(text)
            logger.debug("✅ json5直接解析成功，无需清洗")
            return text
        except Exception:
            pass

        # 修复0：关闭未闭合的字符串（在 _fix_json_string_values 之前处理）
        # AI 常见：字符串值内有裸换行导致字符串未闭合，后续 JSON 结构被吞入字符串
        text = _fix_unclosed_strings(text)

        # 上下文感知修复：中文引号/逗号/冒号、裸控制字符、未转义的内容引号
        text = _fix_json_string_values(text)

        # 修复未引号 key 和单引号字符串（AI 常见错误）
        text = _fix_unquoted_keys(text)

        # 找到第一个 { 或 [
        start = -1
        for i, c in enumerate(text):
            if c in ("{", "["):
                start = i
                break

        if start == -1:
            logger.warning(f"⚠️ 未找到JSON起始符号 {{ 或 [，文本预览前200字: {safe_preview(text, 200)}")
            return text

        if start > 0:
            logger.debug(f"   跳过前{start}个字符")
            text = text[start:]

        # 改进的括号匹配算法（更严格的字符串处理）
        stack = []
        i = 0
        end = -1
        in_string = False

        while i < len(text):
            c = text[i]

            # 处理字符串状态
            if c == '"':
                if not in_string:
                    # 进入字符串
                    in_string = True
                else:
                    # 检查是否是转义的引号
                    num_backslashes = 0
                    j = i - 1
                    while j >= 0 and text[j] == "\\":
                        num_backslashes += 1
                        j -= 1

                    # 偶数个反斜杠表示引号未被转义，字符串结束
                    if num_backslashes % 2 == 0:
                        in_string = False

                i += 1
                continue

            # 在字符串内部，跳过所有字符
            if in_string:
                i += 1
                continue

            # 处理括号（只有在字符串外部才有效）
            if c == "{" or c == "[":
                stack.append(c)
            elif c == "}":
                if len(stack) > 0 and stack[-1] == "{":
                    stack.pop()
                    if len(stack) == 0:
                        end = i + 1
                        logger.debug(f"✅ 找到JSON结束位置: {end}")
                        break
                elif len(stack) > 0:
                    # 括号不匹配，可能是损坏的JSON，尝试继续
                    logger.warning(f"⚠️ 括号不匹配：遇到 }} 但栈顶是 {stack[-1]}")
                else:
                    # 栈为空遇到 }，忽略多余的闭合括号
                    logger.warning("⚠️ 遇到多余的 }，忽略")
            elif c == "]":
                if len(stack) > 0 and stack[-1] == "[":
                    stack.pop()
                    if len(stack) == 0:
                        end = i + 1
                        logger.debug(f"✅ 找到JSON结束位置: {end}")
                        break
                elif len(stack) > 0:
                    # 括号不匹配，可能是损坏的JSON，尝试继续
                    logger.warning(f"⚠️ 括号不匹配：遇到 ] 但栈顶是 {stack[-1]}")
                else:
                    # 栈为空遇到 ]，忽略多余的闭合括号
                    logger.warning("⚠️ 遇到多余的 ]，忽略")

            i += 1

        # 检查未闭合的字符串
        if in_string:
            logger.warning("⚠️ 字符串未闭合，JSON可能不完整")

        # 提取结果
        if end > 0:
            result = text[:end]
            logger.debug(f"✅ JSON清洗完成，结果长度: {len(result)}")
        else:
            result = text
            logger.warning(f"⚠️ 未找到JSON结束位置，返回全部内容（长度: {len(result)}）")
            logger.debug(f"   栈状态: {stack}")

        # 验证清洗后的结果
        try:
            _try_loads(result)
            logger.debug("✅ 清洗后JSON验证成功")
        except Exception as e:
            logger.warning(f"⚠️ 清洗后JSON仍然无效: {e}，尝试修复结构性问题...")

            # 修复0：补缺失逗号（AI 常见：两行属性之间少了逗号）
            result = _fix_missing_commas(result)
            try:
                _try_loads(result)
                logger.info("✅ 补缺失逗号后JSON验证成功")
            except Exception:
                pass
            else:
                return result

            # 修复1：合并多对象属性值（AI可能输出 "key": {a:1}, {b:2} ）
            result = _fix_multiple_objects_as_value(result)

            try:
                _try_loads(result)
                logger.info("✅ 修复多对象属性值后JSON验证成功")
            except Exception:
                pass  # 继续尝试其他修复
            else:
                return result

            # 修复2：兜底修复无效转义序列（不依赖字符串边界追踪）
            logger.warning("⚠️ 继续尝试兜底修复无效转义...")
            result = _fix_all_invalid_escapes(result)
            try:
                _try_loads(result)
                logger.info("✅ 兜底修复后JSON验证成功")
            except Exception:
                # 修复3：再次尝试合并多对象属性值（转义修复后可能产生新的合并机会）
                result = _fix_multiple_objects_as_value(result)
                try:
                    _try_loads(result)
                    logger.info("✅ 二次修复后JSON验证成功")
                except Exception:
                    # 修复4：基于错误位置迭代修复未转义引号
                    logger.warning("⚠️ 继续尝试基于错误位置修复未转义引号...")
                    result = _fix_unescaped_quotes_by_error(result)
                    try:
                        _try_loads(result)
                        logger.info("✅ 基于错误位置修复后JSON验证成功")
                    except Exception as e4:
                        logger.error(f"❌ 所有修复后JSON仍然无效: {e4}")
                        logger.warning(f"   清洗后结果预览(前800字): {result[:800]}")
                        logger.warning(f"   清洗后结果结尾(后300字): ...{result[-300:]}")
                        # 最后兜底：通过括号匹配提取最长 JSON 子串
                        extracted = _extract_json_by_brackets(result)
                        if extracted:
                            try:
                                _try_loads(extracted)
                                logger.info(f"✅ 括号匹配提取成功（长度={len(extracted)}）")
                                result = extracted
                            except Exception:
                                pass
                        # 尝试关闭未闭合的 JSON 字符串/括号
                        closed = _close_unclosed_json(result)
                        if closed != result:
                            try:
                                _try_loads(closed)
                                logger.info("✅ 关闭未闭合JSON后解析成功")
                                result = closed
                            except Exception:
                                pass
                        # 输出错误位置附近的片段，便于排查
                        try:
                            import re as _re
                            m = _re.search(r"line (\d+) column (\d+)", str(e4))
                            if m:
                                el, ec = int(m.group(1)), int(m.group(2))
                                lines = result.split("\n")
                                if 0 < el <= len(lines):
                                    start = max(0, el - 3)
                                    end = min(len(lines), el + 2)
                                    snippet = "\n".join(
                                        f"{'>>>' if (start+i+1)==el else '   '} {start+i+1}| {lines[start+i]}"
                                        for i in range(end - start)
                                    )
                                    logger.warning(f"   错误位置(line {el})上下文:\n{snippet}")
                        except Exception:
                            pass

        return result

    except Exception as e:
        logger.error(f"❌ clean_json_response 出错: {e}")
        logger.error(f"   文本长度: {len(text) if text else 0}")
        logger.error(f"   文本预览: {safe_preview(text, 200)}")
        raise


def _extract_json_by_brackets(text: str) -> str | None:
    """兜底提取：通过括号匹配找到最长的合法 JSON 子串（含字符串状态追踪）。"""
    if not text:
        return None

    candidates = []
    stack = []
    start = -1
    in_string = False
    i = 0

    while i < len(text):
        c = text[i]

        # 字符串状态追踪
        if c == '"' and (i == 0 or text[i - 1] != '\\'):
            if not in_string:
                in_string = True
            else:
                in_string = False

        if in_string:
            i += 1
            continue

        # 括号处理（仅在字符串外部）
        if c == '{' and not stack:
            stack.append('{')
            start = i
        elif c == '[' and not stack:
            stack.append('[')
            start = i
        elif c == '{' and stack:
            stack.append('{')
        elif c == '[' and stack:
            stack.append('[')
        elif c == '}' and stack and stack[-1] == '{':
            stack.pop()
        elif c == ']' and stack and stack[-1] == '[':
            stack.pop()
        elif c in ('}', ']') and stack:
            # 不匹配的括号，清空栈重新开始
            stack = []
            start = -1

        if not stack and start >= 0:
            candidate = text[start:i + 1]
            candidates.append(candidate)
            start = -1

        i += 1

    if not candidates:
        return None

    # 返回最长的候选
    best = max(candidates, key=len)
    return best if len(best) > 10 else None


def _close_unclosed_json(text: str) -> str:
    """修复未闭合的 JSON：补全未闭合的字符串和缺失的闭合括号。"""
    if not text or '"' not in text:
        return text

    result = []
    in_string = False
    i = 0

    while i < len(text):
        c = text[i]

        if c == '\\' and in_string and i + 1 < len(text):
            # 转义序列，跳过下一个字符
            result.append(c)
            result.append(text[i + 1])
            i += 2
            continue

        if c == '"':
            if in_string:
                in_string = False
            else:
                in_string = True
            result.append(c)
            i += 1
            continue

        if in_string:
            result.append(c)
            i += 1
            continue

        # 字符串外：统计括号
        if c in ('{', '['):
            result.append(c)
            i += 1
            continue

        if c in ('}', ']'):
            result.append(c)
            i += 1
            continue

        result.append(c)
        i += 1

    # 如果字符串未闭合，补上闭合引号
    if in_string:
        result.append('"')

    # 补全缺失的闭合括号（统计未闭合的 { 和 [）
    open_braces = sum(1 for ch in result if ch == '{')
    close_braces = sum(1 for ch in result if ch == '}')
    open_brackets = sum(1 for ch in result if ch == '[')
    close_brackets = sum(1 for ch in result if ch == ']')

    result.append(']' * (open_brackets - close_brackets))
    result.append('}' * (open_braces - close_braces))

    return ''.join(result)


def parse_json(text: str) -> dict | list:
    """解析 JSON，json5 为主解析器（兼容无引号 key、单引号、尾逗号等 AI 常见格式）。"""
    cleaned = clean_json_response(text)

    # json5 做主解析器（JSON 超集，兼容性更好）
    if HAS_JSON5:
        try:
            return json5.loads(cleaned)
        except Exception as e5:
            logger.warning(f"json5 解析失败: {e5}，降级到标准 json")

    # 降级：标准 json（对合法 JSON 更高效）
    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, Exception) as e:
        logger.error(f"❌ parse_json 完全失败: {e}")
        logger.error(f"   原始文本长度: {len(text) if text else 0}，清洗后: {len(cleaned) if cleaned else 0}")
        logger.warning(f"   [JSON失败内容预览 前500字] {safe_preview(cleaned, 500)}")
        raise json.JSONDecodeError("JSON解析失败（json5和标准json均失败）", cleaned, 0) from None


def loads_json(text: str) -> Any:
    """
    json.loads 的容错替代品，可直接替换 json.loads()。
    json5 为主解析器（兼容无引号 key、单引号、尾逗号等 AI 常见格式）。
    """
    # json5 做主解析器（JSON 超集，兼容性更好）
    if HAS_JSON5:
        try:
            return json5.loads(text)
        except Exception:
            pass

    # 降级：标准 json
    try:
        return json.loads(text)
    except (json.JSONDecodeError, Exception):
        pass

    # 兜底修复无效转义序列后重试
    fixed_text = _fix_all_invalid_escapes(text)
    if fixed_text != text:
        if HAS_JSON5:
            try:
                return json5.loads(fixed_text)
            except Exception:
                pass
        try:
            return json.loads(fixed_text)
        except (json.JSONDecodeError, Exception):
            pass

    # 最终失败，抛出标准异常
    raise json.JSONDecodeError("JSON解析失败（json5和标准json均失败）", text, 0)
