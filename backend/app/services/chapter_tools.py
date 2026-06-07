"""章节生成工具系统（Function Calling）。

让 AI 在写作过程中按需主动查询数据库——查角色档案、伏笔状态、物品归属、前文剧情等。
对标 MuMu 的 MCP 工具架构，但查询的是本地 DB 而非外部服务。

工具列表：
1. query_character - 查角色完整档案
2. query_character_relations - 查角色关系网络
3. query_foreshadows - 查伏笔状态
4. query_item - 查物品详情和归属
5. query_chapter_summary - 查前文章节剧情
6. query_organization - 查组织详情
"""
import json
import logging
from typing import Callable, Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.character import Character, CharacterRelation
from app.models.foreshadow import Foreshadow
from app.models.item import Item
from app.models.location import Location
from app.models.organization import Organization
from app.models.organization_member import OrganizationMember
from app.models.chapter import Chapter
from app.models.plot_analysis import PlotAnalysis
from app.services.foreshadow_service import ForeshadowService

logger = logging.getLogger(__name__)


def get_chapter_tools() -> list[dict]:
    """返回 OpenAI function calling 格式的工具定义。"""
    return [
        {
            "type": "function",
            "function": {
                "name": "query_character",
                "description": "按名字查询角色的完整档案（外貌/性格/背景/能力/动机/当前心理状态/所属组织）。写到某角色时调用，确认设定避免矛盾。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "角色名（支持模糊匹配，如'林'可匹配'林晚秋'）"}
                    },
                    "required": ["name"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "query_character_relations",
                "description": "查询某角色的所有人际关系（亲密度/关系类型/状态）。写对手戏、情感戏时确认双方关系用。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "角色名"}
                    },
                    "required": ["name"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "query_foreshadows",
                "description": "查询伏笔状态。了解哪些伏笔本章必须回收、哪些超期了、哪些即将到期。写剧情转折时调用。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filter": {
                            "type": "string",
                            "enum": ["overdue", "must_resolve", "upcoming", "all"],
                            "description": "overdue=超期未收, must_resolve=本章必须收, upcoming=即将到期(5章内), all=全部活跃伏笔",
                            "default": "all"
                        }
                    }
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "query_item",
                "description": "按名字查询物品/道具详情（持有者、属性、状态、获取经过）。写战斗/交易/赠予场景时确认道具归属。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "物品名（支持模糊匹配）"}
                    },
                    "required": ["name"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "query_chapter_summary",
                "description": "查询指定章节的剧情摘要、关键情节、角色状态变化。回顾前文避免剧情矛盾时调用。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "chapter_number": {"type": "integer", "description": "要查询的章节号"}
                    },
                    "required": ["chapter_number"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "query_organization",
                "description": "按名字查询组织/势力详情（类型、描述、势力值、所在地、成员数）。写势力冲突场景时调用。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "组织名（支持模糊匹配）"}
                    },
                    "required": ["name"]
                }
            }
        },
    ]


def make_tool_executor(db: AsyncSession, project_id: int, chapter_number: int = 1) -> Callable:
    """创建工具执行器闭包。

    返回 async def(tool_name: str, arguments: dict) -> str
    每个 AI 工具调用会路由到对应的 DB 查询。
    """
    fs_service = ForeshadowService(db, project_id)

    async def executor(tool_name: str, arguments: dict) -> str:
        """执行单个工具调用，返回 JSON 字符串。"""
        try:
            if tool_name == "query_character":
                return await _query_character(db, project_id, arguments.get("name", ""))

            elif tool_name == "query_character_relations":
                return await _query_relations(db, project_id, arguments.get("name", ""))

            elif tool_name == "query_foreshadows":
                return await _query_foreshadows(fs_service, chapter_number, arguments.get("filter", "all"))

            elif tool_name == "query_item":
                return await _query_item(db, project_id, arguments.get("name", ""))

            elif tool_name == "query_chapter_summary":
                return await _query_chapter_summary(db, project_id, arguments.get("chapter_number", 1))

            elif tool_name == "query_organization":
                return await _query_organization(db, project_id, arguments.get("name", ""))

            else:
                return json.dumps({"error": f"未知工具: {tool_name}"}, ensure_ascii=False)

        except Exception as e:
            logger.warning(f"[tools] 工具 {tool_name} 执行失败: {e}")
            return json.dumps({"error": str(e)[:200]}, ensure_ascii=False)

    return executor


# ===== 工具实现 =====

async def _query_character(db: AsyncSession, project_id: int, name: str) -> str:
    """查角色完整档案（模糊匹配名字）。"""
    if not name:
        return json.dumps({"error": "请提供角色名"}, ensure_ascii=False)
    chars = (await db.execute(
        select(Character).where(Character.project_id == project_id)
    )).scalars().all()
    # 模糊匹配
    matched = [c for c in chars if name in c.name or c.name in name]
    if not matched:
        return json.dumps({"error": f"未找到角色「{name}」"}, ensure_ascii=False)
    results = []
    for c in matched[:3]:  # 最多返回3个匹配
        results.append({
            "name": c.name, "role": c.role or "", "gender": c.gender or "",
            "age": c.age or "", "status": c.status or "alive",
            "mental_state": c.mental_state or "",
            "appearance": (c.appearance or "")[:200],
            "personality": (c.personality or "")[:200],
            "background": (c.background or "")[:200],
            "ability": (c.ability or "")[:200],
            "story_goal": (c.story_goal or "")[:150],
            "motivation": (c.motivation or "")[:150],
            "weakness": (c.weakness or "")[:100],
            "occupation": c.occupation or "",
            "speech_style": c.speech_style or "",
        })
    return json.dumps(results if len(results) > 1 else results[0], ensure_ascii=False)


async def _query_relations(db: AsyncSession, project_id: int, name: str) -> str:
    """查角色关系网络。"""
    if not name:
        return json.dumps({"error": "请提供角色名"}, ensure_ascii=False)
    char = (await db.execute(
        select(Character).where(Character.project_id == project_id)
    )).scalars().all()
    target = next((c for c in char if name in c.name or c.name in name), None)
    if not target:
        return json.dumps({"error": f"未找到角色「{name}」"}, ensure_ascii=False)
    id_to_name = {c.id: c.name for c in char}
    rels = (await db.execute(
        select(CharacterRelation).where(
            CharacterRelation.project_id == project_id,
            (CharacterRelation.from_character_id == target.id) | (CharacterRelation.to_character_id == target.id)
        )
    )).scalars().all()
    results = []
    for r in rels[:10]:
        other_id = r.to_character_id if r.from_character_id == target.id else r.from_character_id
        results.append({
            "target": id_to_name.get(other_id, "?"),
            "relation_type": r.relation_type or "",
            "category": r.category or "",
            "intimacy": r.intimacy or 0,
            "description": (r.description or "")[:100],
        })
    return json.dumps({"character": target.name, "relations": results}, ensure_ascii=False)


async def _query_foreshadows(fs_service: ForeshadowService, chapter_number: int, filter_type: str) -> str:
    """查伏笔状态。"""
    results = []
    if filter_type in ("overdue", "all"):
        overdue = await fs_service.get_overdue_foreshadows(chapter_number)
        for f in overdue[:8]:
            results.append({"title": f.title, "status": "超期", "type": f.foreshadow_type,
                            "plant_chapter": f.actual_plant_chapter or f.plant_chapter_number,
                            "target_chapter": f.target_resolve_chapter_number,
                            "content": (f.content or "")[:80]})
    if filter_type in ("must_resolve", "all"):
        must = await fs_service.get_must_resolve_foreshadows(chapter_number)
        for f in must[:5]:
            results.append({"title": f.title, "status": "本章必须回收", "type": f.foreshadow_type,
                            "content": (f.content or "")[:80]})
    if filter_type in ("upcoming", "all"):
        upcoming = await fs_service.get_pending_resolve_foreshadows(chapter_number, lookahead=5)
        for f in upcoming[:5]:
            results.append({"title": f.title, "status": "即将到期", "type": f.foreshadow_type,
                            "target_chapter": f.target_resolve_chapter_number,
                            "content": (f.content or "")[:80]})
    if not results:
        return json.dumps({"message": "没有相关伏笔"}, ensure_ascii=False)
    return json.dumps(results, ensure_ascii=False)


async def _query_item(db: AsyncSession, project_id: int, name: str) -> str:
    """查物品详情。"""
    if not name:
        return json.dumps({"error": "请提供物品名"}, ensure_ascii=False)
    items = (await db.execute(
        select(Item).where(Item.project_id == project_id)
    )).scalars().all()
    matched = [i for i in items if name in i.name or i.name in name]
    if not matched:
        return json.dumps({"error": f"未找到物品「{name}」"}, ensure_ascii=False)
    results = []
    for i in matched[:3]:
        results.append({
            "name": i.name, "category": i.category, "rarity": i.rarity,
            "item_type": i.item_type, "description": (i.description or "")[:200],
            "owner_name": i.owner_name or "无主", "status": i.status,
            "obtained_chapter": i.obtained_chapter, "is_key_item": bool(i.is_key_item),
        })
    return json.dumps(results if len(results) > 1 else results[0], ensure_ascii=False)


async def _query_chapter_summary(db: AsyncSession, project_id: int, chapter_number: int) -> str:
    """查指定章节的剧情摘要。"""
    ch = (await db.execute(
        select(Chapter).where(
            Chapter.project_id == project_id, Chapter.chapter_number == chapter_number
        ).order_by(Chapter.id.desc())
    )).scalars().first()
    if not ch:
        return json.dumps({"error": f"未找到第{chapter_number}章"}, ensure_ascii=False)
    result = {"chapter_number": chapter_number, "title": ch.title or "",
              "summary": (ch.summary or "")[:300]}
    # 附带剧情分析
    analysis = (await db.execute(
        select(PlotAnalysis).where(
            PlotAnalysis.project_id == project_id, PlotAnalysis.chapter_number == chapter_number
        ).order_by(PlotAnalysis.id.desc())
    )).scalars().first()
    if analysis:
        result["key_plot_points"] = analysis.key_plot_points or []
        result["conflicts"] = analysis.conflicts or []
        ec = analysis.emotional_curve if isinstance(analysis.emotional_curve, dict) else {}
        result["emotion_end"] = ec.get("end", "")
        result["plot_stage"] = analysis.plot_stage or ""
    return json.dumps(result, ensure_ascii=False)


async def _query_organization(db: AsyncSession, project_id: int, name: str) -> str:
    """查组织详情。"""
    if not name:
        return json.dumps({"error": "请提供组织名"}, ensure_ascii=False)
    orgs = (await db.execute(
        select(Organization).where(Organization.project_id == project_id)
    )).scalars().all()
    matched = [o for o in orgs if name in o.name or o.name in name]
    if not matched:
        return json.dumps({"error": f"未找到组织「{name}」"}, ensure_ascii=False)
    # 成员数
    results = []
    for o in matched[:3]:
        member_count = await db.scalar(
            select(func.count(OrganizationMember.id)).where(
                OrganizationMember.organization_id == o.id,
                OrganizationMember.status == "active"
            )
        )
        results.append({
            "name": o.name, "org_type": o.org_type or "",
            "description": (o.description or "")[:200],
            "power_value": o.power_value or 50, "location": o.location or "",
            "motto": o.motto or "", "member_count": member_count or 0,
        })
    return json.dumps(results if len(results) > 1 else results[0], ensure_ascii=False)
