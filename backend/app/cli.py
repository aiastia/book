#!/usr/bin/env python3
"""NovelAI CLI - 命令行工具"""
import argparse
import requests
import json
import sys
import os

DEFAULT_API = os.getenv("NOVELAI_API", "http://localhost:8000")

def get_token(args):
    r = requests.post(f"{args.api}/api/auth/login", json={"username": args.user, "password": args.password})
    r.raise_for_status()
    return r.json()["access_token"]

def headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

def cmd_register(args):
    r = requests.post(f"{args.api}/api/auth/register", json={"username": args.user, "password": args.password, "email": args.email})
    if r.ok: print(f"✓ 注册成功: {args.user}")
    else: print(f"✗ {r.json().get('detail', '注册失败')}"); sys.exit(1)

def cmd_projects(args):
    token = get_token(args)
    r = requests.get(f"{args.api}/api/projects", headers=headers(token))
    for p in r.json():
        print(f"  [{p['id']}] {p['title']} ({p['genre']}) - {p['chapter_count']}章 {p['current_word_count']}字")

def cmd_create(args):
    token = get_token(args)
    r = requests.post(f"{args.api}/api/projects", headers=headers(token), json={"title": args.title, "genre": args.genre})
    if r.ok: print(f"✓ 项目创建成功: #{r.json()['id']}")
    else: print(f"✗ {r.json().get('detail', '创建失败')}"); sys.exit(1)

def cmd_outlines(args):
    token = get_token(args)
    r = requests.get(f"{args.api}/api/projects/{args.project}/outlines", headers=headers(token))
    for o in r.json():
        print(f"  第{o['chapter_number']}章 {o['title']} - {o['emotion'] or ''}")

def cmd_gen_outline(args):
    token = get_token(args)
    data = {"synopsis": args.synopsis, "chapter_count": args.count, "world_info": "", "characters_info": ""}
    r = requests.post(f"{args.api}/api/projects/{args.project}/outlines/generate", headers=headers(token), json=data)
    if r.ok:
        outlines = r.json()
        print(f"✓ 生成 {len(outlines)} 章大纲:")
        for o in outlines:
            print(f"  第{o['chapter_number']}章 {o['title']}")
    else: print(f"✗ {r.json().get('detail', '生成失败')}"); sys.exit(1)

def cmd_chapters(args):
    token = get_token(args)
    r = requests.get(f"{args.api}/api/projects/{args.project}/chapters", headers=headers(token))
    for c in r.json():
        status = "✓" if c["status"] == "completed" else "○"
        print(f"  {status} [{c['id']}] 第{c['chapter_number']}章 {c['title']} ({c['word_count']}字)")

def cmd_gen_chapter(args):
    token = get_token(args)
    r = requests.post(f"{args.api}/api/projects/{args.project}/chapters/{args.chapter}/generate", headers=headers(token))
    if r.ok:
        ch = r.json()
        print(f"✓ 第{ch['chapter_number']}章 生成完成 ({ch['word_count']}字)")
        if args.output:
            with open(args.output, "w") as f: f.write(ch["content"])
            print(f"  内容已保存到 {args.output}")
    else: print(f"✗ {r.json().get('detail', '生成失败')}"); sys.exit(1)

def cmd_foreshadows(args):
    token = get_token(args)
    r = requests.get(f"{args.api}/api/projects/{args.project}/foreshadows", headers=headers(token))
    for f in r.json():
        print(f"  [{f['status']}] {f['title']} (埋:{f['plant_chapter_number'] or '-'} 回:{f['target_resolve_chapter_number'] or '-'})")

def cmd_plan_foreshadows(args):
    token = get_token(args)
    r = requests.post(f"{args.api}/api/projects/{args.project}/foreshadows/plan", headers=headers(token))
    if r.ok:
        fs = r.json()
        print(f"✓ AI 规划了 {len(fs)} 个伏笔")
        for f in fs: print(f"  {f['title']} → 埋:{f['plant_chapter_number']} 回:{f['target_resolve_chapter_number']}")
    else: print(f"✗ {r.json().get('detail', '规划失败')}"); sys.exit(1)

def cmd_add_model(args):
    token = get_token(args)
    data = {"name": args.name, "provider": args.provider, "base_url": args.base_url, "model_name": args.model, "api_key": args.key}
    r = requests.post(f"{args.api}/api/ai-models", headers=headers(token), json=data)
    if r.ok: print(f"✓ 模型添加成功: {r.json()['name']}")
    else: print(f"✗ {r.json().get('detail', '添加失败')}"); sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="NovelAI CLI - AI 小说创作命令行工具")
    parser.add_argument("--api", default=DEFAULT_API, help="API 地址")
    parser.add_argument("--user", "-u", help="用户名")
    parser.add_argument("--password", "-p", help="密码")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("register", help="注册用户").add_argument("user").add_argument("password").add_argument("--email")
    sub.add_parser("projects", help="列出项目")
    cp = sub.add_parser("create", help="创建项目")
    cp.add_argument("title"); cp.add_argument("--genre", default="玄幻")

    sub.add_parser("outlines", help="列出大纲").add_argument("project", type=int)
    gop = sub.add_parser("gen-outline", help="AI 生成大纲")
    gop.add_argument("project", type=int); gop.add_argument("--synopsis", required=True); gop.add_argument("--count", type=int, default=10)

    sub.add_parser("chapters", help="列出章节").add_argument("project", type=int)
    gcp = sub.add_parser("gen-chapter", help="AI 生成章节")
    gcp.add_argument("project", type=int); gcp.add_argument("chapter", type=int); gcp.add_argument("--output", "-o")

    sub.add_parser("foreshadows", help="列出伏笔").add_argument("project", type=int)
    sub.add_parser("plan-foreshadows", help="AI 规划伏笔").add_argument("project", type=int)

    mp = sub.add_parser("add-model", help="添加 AI 模型")
    mp.add_argument("name"); mp.add_argument("--provider", required=True); mp.add_argument("--base-url", required=True)
    mp.add_argument("--model", required=True); mp.add_argument("--key", required=True)

    args = parser.parse_args()
    if not args.command: parser.print_help(); return

    cmds = {"register": cmd_register, "projects": cmd_projects, "create": cmd_create,
            "outlines": cmd_outlines, "gen-outline": cmd_gen_outline,
            "chapters": cmd_chapters, "gen-chapter": cmd_gen_chapter,
            "foreshadows": cmd_foreshadows, "plan-foreshadows": cmd_plan_foreshadows,
            "add-model": cmd_add_model}
    cmds[args.command](args)

if __name__ == "__main__":
    main()