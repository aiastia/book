"""项目路由聚合包。

将原本 1662 行的 projects.py 按功能拆分为多个短模块：
- base.py: 共享 imports + schemas + 辅助函数
- crud.py: 项目 CRUD
- outlines.py: 大纲（生成/CRUD/续写/展开）
- chapters.py: 章节（CRUD/生成/重写）
- characters.py: 角色（CRUD/生成/批量/自动）
- worlds.py: 世界观 + 组织 + 职业体系
- foreshadows.py: 伏笔 + 剧情分析
- inspiration.py: 灵感模式
- ai_tools.py: AI 工具（去味/封面/拆书导入/MCP）

所有子模块用同一个 prefix=/api/projects，此处聚合导出单一 router。
"""

from fastapi import APIRouter

from app.api.routes.projects_pkg import (
    ai_tools,
    batch_generation,
    chapter_rewrite,
    chapters,
    character_careers,
    characters,
    crud,
    foreshadows,
    inspiration,
    items,
    locations,
    memories,
    org_members,
    outlines,
    relations,
    screenplay,
    tts,
    worlds,
)

# 聚合路由：遍历所有子模块的 router，合并到一个
router = APIRouter()


def _merge(sub_router: APIRouter):
    """把子模块的路由合并到聚合 router"""
    for route in sub_router.routes:
        router.routes.append(route)


_merge(crud.router)
_merge(outlines.router)
_merge(chapters.router)
_merge(characters.router)
_merge(worlds.router)
_merge(foreshadows.router)
_merge(inspiration.router)
_merge(ai_tools.router)
_merge(relations.router)
_merge(memories.router)
_merge(items.router)
_merge(locations.router)
_merge(org_members.router)
_merge(character_careers.router)
_merge(batch_generation.router)
_merge(chapter_rewrite.router)
_merge(screenplay.router)
_merge(tts.router)

__all__ = ["router"]
