"""TXT 解析服务（#23 拆书导入第一步）。

对标 MuMuAINovel TxtParserService。
- 编码识别：utf-8 / utf-8-sig / gb18030 / gbk / big5
- 文本清洗：换行归一、压缩空行
- 章节切分：强标题（第X章）+ 弱标题（短行+前后空行）+ 兜底窗口
"""

import logging
import re

logger = logging.getLogger(__name__)


def decode_bytes(raw: bytes) -> str:
    """尝试多种编码解码，返回成功的那一个。"""
    for enc in ["utf-8-sig", "utf-8", "gb18030", "gbk", "big5"]:
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    # 兜底：utf-8 忽略错误
    return raw.decode("utf-8", errors="ignore")


def clean_text(text: str) -> str:
    """清洗文本：归一化换行、全角空格、压缩连续空行。"""
    # 统一换行符
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # 全角空格转双空格（保留缩进）
    text = text.replace("\u3000", "  ")
    # 压缩 3+ 连续空行为 2 个
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# 强标题正则：第X章/卷/节/回/集/部/篇，或 Chapter N
STRONG_TITLE_PATTERNS = [
    re.compile(r"^第[\s]*[零一二三四五六七八九十百千万0-9]+[\s]*(章|卷|节|回|集|部|篇)"),
    re.compile(r"^(Chapter|CHAPTER|chapter)[\s]*[0-9]+", re.IGNORECASE),
    re.compile(r"^(Chap|chap|CHAP)[\.\s]*[0-9]+", re.IGNORECASE),
    re.compile(r"^[0-9]+[\.\s]"),  # 纯数字开头 1. 或 1
]


def is_strong_title(line: str) -> bool:
    """是否强标题行。"""
    line = line.strip()
    if not line or len(line) > 50:
        return False
    return any(p.search(line) for p in STRONG_TITLE_PATTERNS)


def is_weak_title(line: str, prev_blank: bool, next_blank: bool) -> bool:
    """是否弱标题行（短行+前后空行+无结尾标点）。"""
    line = line.strip()
    if not line or len(line) > 25:
        return False
    if not prev_blank or not next_blank:
        return False
    # 无结尾标点（句号/问号/感叹号/省略号）
    if re.search(r"[。！？!?\.\…]$", line):
        return False
    # 包含数字或「章/节/回」字样更可能是标题
    if re.search(r"[0-9章卷节回篇]", line):
        return True
    return False


def split_chapters(text: str) -> list[dict]:
    """切分章节。

    返回 [{chapter_number, title, content, start_pos}]。
    策略：先强标题切，切不出则弱标题，再不行则固定窗口兜底。
    """
    text = clean_text(text)
    lines = text.split("\n")

    # 第一遍：找所有强标题位置
    title_positions = []
    for i, line in enumerate(lines):
        if is_strong_title(line):
            title_positions.append(i)

    if len(title_positions) >= 3:
        # 强标题切分成功
        chapters = []
        for idx, start in enumerate(title_positions):
            title = lines[start].strip()
            # 内容范围：标题后一行 → 下一个标题前
            content_start = start + 1
            content_end = title_positions[idx + 1] if idx + 1 < len(title_positions) else len(lines)
            content = "\n".join(lines[content_start:content_end]).strip()
            chapters.append(
                {
                    "chapter_number": idx + 1,
                    "title": title,
                    "content": content,
                }
            )
        # 标题前的内容作为前言
        if title_positions[0] > 0:
            preface = "\n".join(lines[: title_positions[0]]).strip()
            if len(preface) > 100:
                chapters.insert(
                    0,
                    {
                        "chapter_number": 0,
                        "title": "前言",
                        "content": preface,
                    },
                )
        return chapters

    # 第二遍：弱标题
    title_positions = []
    for i, line in enumerate(lines):
        prev_blank = i == 0 or not lines[i - 1].strip()
        next_blank = i == len(lines) - 1 or not lines[i + 1].strip()
        if is_weak_title(line, prev_blank, next_blank):
            title_positions.append(i)

    if len(title_positions) >= 3:
        chapters = []
        for idx, start in enumerate(title_positions):
            title = lines[start].strip()
            content_start = start + 1
            content_end = title_positions[idx + 1] if idx + 1 < len(title_positions) else len(lines)
            content = "\n".join(lines[content_start:content_end]).strip()
            chapters.append(
                {
                    "chapter_number": idx + 1,
                    "title": title,
                    "content": content,
                }
            )
        return chapters

    # 第三遍：固定窗口兜底（每 3000-5000 字一章，按段落边界切）
    WINDOW = 4000
    chapters = []
    paragraphs = text.split("\n\n")
    current = []
    current_len = 0
    ch_num = 1
    for para in paragraphs:
        current.append(para)
        current_len += len(para)
        if current_len >= WINDOW:
            chapters.append(
                {
                    "chapter_number": ch_num,
                    "title": f"第{ch_num}章",
                    "content": "\n\n".join(current).strip(),
                }
            )
            current = []
            current_len = 0
            ch_num += 1
    if current:
        chapters.append(
            {
                "chapter_number": ch_num,
                "title": f"第{ch_num}章",
                "content": "\n\n".join(current).strip(),
            }
        )
    return chapters


def parse_txt_file(raw: bytes) -> dict:
    """解析 TXT 文件，返回 {text, chapters, stats}。"""
    text = decode_bytes(raw)
    chapters = split_chapters(text)
    return {
        "text": text,
        "chapters": chapters,
        "stats": {
            "total_chars": len(text),
            "chapter_count": len(chapters),
            "has_strong_titles": any(
                c.get("chapter_number", 0) > 0 and c.get("title", "").startswith("第")
                for c in chapters
            ),
        },
    }
