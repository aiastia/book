"""
命令行入口 —— 不启动 HTTP 服务,直接 小说.txt → SSML。

用法:
  # 需要 LLM 分析(要先配好 .env):
  python cli.py 小说.txt -o ssml.xml --voice zh-CN-XiaoxiaoNeural

  # 跳过 LLM,用已有的 Director JSON 直接拼 SSML:
  python cli.py --director director.json -o ssml.xml

  # 分析结果单独保存(方便复用,不用每次调 LLM):
  python cli.py 小说.txt --save-director director.json -o ssml.xml
"""
import argparse
import json
import os
import sys

from dotenv import load_dotenv

load_dotenv()


def main():
    parser = argparse.ArgumentParser(description="小说 → SSML 流水线")
    parser.add_argument("input", nargs="?", help="小说文本文件路径(.txt)")
    parser.add_argument("--director", help="已有的 Director JSON 文件(跳过 LLM 分析)")
    parser.add_argument("-o", "--output", help="输出 SSML 文件路径(缺省打印到屏幕)")
    parser.add_argument("--voice", default="zh-CN-XiaoxiaoNeural", help="Azure 语音名")
    parser.add_argument("--save-director", help="把 Director 分析结果保存到指定文件(JSON)")
    parser.add_argument("--chunk-size", type=int, default=800, help="LLM 分块大小(字符)")
    args = parser.parse_args()

    # ── 模式判断 ──
    if args.director:
        # 模式 B:用已有 Director JSON
        with open(args.director, "r", encoding="utf-8") as f:
            raw = json.load(f)
        instructions = _parse_director(raw)
        print(f"从 {args.director} 加载了 {len(instructions)} 条指令")
    elif args.input:
        # 模式 A:从小说文本分析
        with open(args.input, "r", encoding="utf-8") as f:
            text = f.read()

        base_url = os.getenv("LLM_BASE_URL")
        api_key = os.getenv("LLM_API_KEY")
        model = os.getenv("LLM_MODEL", "glm-4-plus")

        if not base_url or not api_key:
            print("错误:缺少 LLM 配置。请在 .env 里设 LLM_BASE_URL / LLM_API_KEY。", file=sys.stderr)
            sys.exit(1)

        from novel_pipeline.llm_client import LLMClient
        from novel_pipeline.director import Director

        print(f"开始分析 ({len(text)} 字,模型 {model})...")
        llm = LLMClient(base_url=base_url, api_key=api_key, model=model)
        director = Director(llm_client=llm, chunk_size=args.chunk_size)
        instructions, err = director.analyze(text)
        if err:
            print(f"分析失败: {err}", file=sys.stderr)
            sys.exit(1)
        print(f"分析完成: {len(instructions)} 条指令")

        # 可选:保存 Director 结果
        if args.save_director:
            raw = _to_json(instructions)
            with open(args.save_director, "w", encoding="utf-8") as f:
                json.dump(raw, f, ensure_ascii=False, indent=2)
            print(f"Director 结果已保存到 {args.save_director}")
    else:
        parser.error("请提供小说文件路径,或用 --director 指定已有的 Director JSON")

    # ── 构建 SSML ──
    from novel_pipeline.builder import SSMLBuilder

    builder = SSMLBuilder()
    ssml_parts = builder.build(instructions, voice=args.voice)

    print(f"生成 {len(ssml_parts)} 个 SSML 片段")

    if args.output:
        # 多片段写入同一个文件,用换行分隔
        with open(args.output, "w", encoding="utf-8") as f:
            f.write("\n\n".join(ssml_parts))
        print(f"SSML 已写入 {args.output}")
    else:
        for i, ssml in enumerate(ssml_parts):
            if len(ssml_parts) > 1:
                print(f"\n{'='*60}\n片段 {i+1}\n{'='*60}")
            print(ssml)


def _to_json(instructions) -> list:
    from novel_pipeline.models import DirectorLine, SceneChange
    result = []
    for instr in instructions:
        if isinstance(instr, SceneChange):
            result.append({"scene_change": instr.scene_change})
        elif isinstance(instr, DirectorLine):
            result.append({
                "speaker": instr.speaker,
                "text": instr.text,
                "emotion": instr.emotion,
                "pause_after": instr.pause_after,
            })
    return result


def _parse_director(raw_list):
    from novel_pipeline.models import DirectorLine, SceneChange
    instructions = []
    for item in raw_list:
        if not isinstance(item, dict):
            continue
        if "scene_change" in item:
            instructions.append(SceneChange(scene_change=str(item["scene_change"])))
        elif "text" in item:
            instructions.append(DirectorLine(
                speaker=str(item.get("speaker", "Narrator")),
                text=str(item["text"]),
                emotion=item.get("emotion"),
                pause_after=item.get("pause_after"),
            ))
    return instructions


if __name__ == "__main__":
    main()
