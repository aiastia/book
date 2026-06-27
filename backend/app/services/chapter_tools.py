"""章节生成工具系统（Function Calling）。

让 AI 在写作过程中按需主动查询数据库——查角色档案、伏笔状态、物品归属、前文剧情等。
对标 MuMu 的 MCP 工具架构，但查询的是本地 DB 而非外部服务。

工具列表（12个）：
1. query_character - 查角色完整档案
2. query_character_relations - 查角色关系网络
3. query_foreshadows - 查伏笔状态
4. query_item - 查物品详情和归属
5. query_location - 查地点详情
6. query_chapter_summary - 查前文章节剧情
7. query_organization - 查组织详情
8. query_career - 查职业体系详情
9. query_world_setting - 查世界设定条目
10. query_plot_timeline - 查剧情演进时间线（跨章因果链追溯）
11. query_outline - 查大纲规划（计划 vs 实际对比）
12. list_available_entities - 列出项目中所有可查询的实体概要（角色/组织/地点/物品）
"""

import json
import logging
from collections.abc import Callable

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.career import Career
from app.models.chapter import Chapter
from app.models.character import Character, CharacterRelation
from app.models.item import Item
from app.models.location import Location
from app.models.organization import Organization
from app.models.organization_member import OrganizationMember
from app.models.outline import Outline
from app.models.plot_analysis import PlotAnalysis
from app.models.world import WorldSetting
from app.services.foreshadow_service import ForeshadowService

logger = logging.getLogger(__name__)


def get_chapter_tools() -> list[dict]:
    """返回 OpenAI function calling 格式的工具定义。"""
    return [
        {
            "type": "function",
            "function": {
                "name": "query_character",
                "description": "按名字查询角色的完整档案（外貌/性格/背景/能力/动机/当前心理状态/所属组织/职业境界）。写到某角色时调用，确认设定避免矛盾。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "角色名（支持模糊匹配，如'林'可匹配'林晚秋'）",
                        }
                    },
                    "required": ["name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "query_character_relations",
                "description": "查询某角色的所有人际关系（亲密度/关系类型/状态）。写对手戏、情感戏时确认双方关系用。",
                "parameters": {
                    "type": "object",
                    "properties": {"name": {"type": "string", "description": "角色名"}},
                    "required": ["name"],
                },
            },
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
                            "default": "all",
                        }
                    },
                },
            },
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
                    "required": ["name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "query_location",
                "description": "按名字查询地点/场景详情（类型、描述、氛围、控制势力、危险等级）。写到新场景时确认地点设定避免描述矛盾。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "地点名（支持模糊匹配）"}
                    },
                    "required": ["name"],
                },
            },
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
                    "required": ["chapter_number"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "query_organization",
                "description": "按名字查询组织/势力详情（类型、描述、势力值、所在地、成员名单、对外关系）。写势力冲突场景时调用。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "组织名（支持模糊匹配）"}
                    },
                    "required": ["name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "query_career",
                "description": "按名字查询职业体系详情（类型、描述、进阶阶段、核心能力）。写角色使用能力或突破境界时确认设定。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "职业名（支持模糊匹配，如'丹修'可匹配'炼丹师'）",
                        }
                    },
                    "required": ["name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "query_world_setting",
                "description": "按关键词查询世界设定条目（地理/历史/种族/势力/文化等）。写到涉及世界观细节时确认设定一致性。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "keyword": {
                            "type": "string",
                            "description": "关键词（支持模糊匹配条目名或内容）",
                        }
                    },
                    "required": ["keyword"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "query_plot_timeline",
                "description": "查询某角色或某关键词在指定章节范围内的剧情演进时间线。用于追溯角色成长弧线、伏笔回收脉络、跨章节因果链。当涉及「回顾前期」「角色成长回顾」「伏笔回收」「跨阶段呼应」时务必调用。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "character_name": {
                            "type": "string",
                            "description": "角色名（可选，按角色追踪演进）",
                        },
                        "keyword": {
                            "type": "string",
                            "description": "关键词（可选，按主题/事件追踪，如'师门''复仇'）",
                        },
                        "from_chapter": {
                            "type": "integer",
                            "description": "起始章节号（可选，默认从第1章开始）",
                        },
                        "to_chapter": {
                            "type": "integer",
                            "description": "结束章节号（可选，默认到当前章之前）",
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "query_outline",
                "description": "查询指定章节的大纲规划（标题、摘要、关键情节点、涉及角色、写作目标）。用于对照原计划确认剧情是否偏离，或回顾某章的原始设计意图。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "chapter_number": {"type": "integer", "description": "要查询的章节号"}
                    },
                    "required": ["chapter_number"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_available_entities",
                "description": "列出项目中所有可查询的实体概要（角色、组织、地点、物品、职业、世界设定）。仅在不确定有哪些可查时才调用，预加载信息已覆盖本章大部分需求。",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
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
                return await _query_foreshadows(
                    fs_service, chapter_number, arguments.get("filter", "all")
                )

            elif tool_name == "query_item":
                return await _query_item(db, project_id, arguments.get("name", ""))

            elif tool_name == "query_location":
                return await _query_location(db, project_id, arguments.get("name", ""))

            elif tool_name == "query_chapter_summary":
                return await _query_chapter_summary(
                    db, project_id, arguments.get("chapter_number", 1)
                )

            elif tool_name == "query_organization":
                return await _query_organization(db, project_id, arguments.get("name", ""))

            elif tool_name == "query_career":
                return await _query_career(db, project_id, arguments.get("name", ""))

            elif tool_name == "query_world_setting":
                return await _query_world_setting(db, project_id, arguments.get("keyword", ""))

            elif tool_name == "query_plot_timeline":
                return await _query_plot_timeline(
                    db,
                    project_id,
                    chapter_number,
                    character_name=arguments.get("character_name", ""),
                    keyword=arguments.get("keyword", ""),
                    from_chapter=arguments.get("from_chapter"),
                    to_chapter=arguments.get("to_chapter"),
                )

            elif tool_name == "query_outline":
                return await _query_outline(db, project_id, arguments.get("chapter_number", 1))

            elif tool_name == "list_available_entities":
                return await _list_available_entities(db, project_id)

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
    chars = (
        (await db.execute(select(Character).where(Character.project_id == project_id)))
        .scalars()
        .all()
    )
    # 模糊匹配
    matched = [c for c in chars if name in c.name or c.name in name]
    if not matched:
        return json.dumps({"error": f"未找到角色「{name}」"}, ensure_ascii=False)
    results = []
    for c in matched[:3]:
        # 查询组织归属
        org_name = ""
        if c.organization_id:
            org = (
                await db.execute(select(Organization).where(Organization.id == c.organization_id))
            ).scalar_one_or_none()
            if org:
                org_name = org.name
        # 查询组织成员身份（可能属于多个组织）
        org_members = (
            (
                await db.execute(
                    select(OrganizationMember).where(
                        OrganizationMember.character_id == c.id,
                        OrganizationMember.status == "active",
                    )
                )
            )
            .scalars()
            .all()
        )
        orgs_detail = [
            {
                "org": (
                    await db.scalar(
                        select(Organization.name).where(Organization.id == om.organization_id)
                    )
                )
                or "",
                "position": om.position or "成员",
            }
            for om in org_members[:5]
        ]

        results.append(
            {
                "name": c.name,
                "role": c.role or "",
                "gender": c.gender or "",
                "age": c.age or "",
                "status": c.status or "alive",
                "identity": c.identity or "",
                "mental_state": c.mental_state or "",
                "appearance": (c.appearance or "")[:200],
                "personality": (c.personality or "")[:200],
                "background": (c.background or "")[:200],
                "ability": (c.ability or "")[:200],
                "story_goal": (c.story_goal or "")[:150],
                "motivation": (c.motivation or "")[:150],
                "weakness": (c.weakness or "")[:100],
                "speech_style": c.speech_style or "",
                "growth_experience": (c.growth_experience or "")[:150],
                "arc_type": c.arc_type or "",
                "character_change": (c.character_change or "")[:150],
                "tags": c.tags or [],
                "main_career_stage_desc": c.main_career_stage_desc or "",
                "organization": org_name,
                "organizations": orgs_detail,
            }
        )
    return json.dumps(results if len(results) > 1 else results[0], ensure_ascii=False)


async def _query_relations(db: AsyncSession, project_id: int, name: str) -> str:
    """查角色关系网络。"""
    if not name:
        return json.dumps({"error": "请提供角色名"}, ensure_ascii=False)
    char = (
        (await db.execute(select(Character).where(Character.project_id == project_id)))
        .scalars()
        .all()
    )
    target = next((c for c in char if name in c.name or c.name in name), None)
    if not target:
        return json.dumps({"error": f"未找到角色「{name}」"}, ensure_ascii=False)
    id_to_name = {c.id: c.name for c in char}
    rels = (
        (
            await db.execute(
                select(CharacterRelation).where(
                    CharacterRelation.project_id == project_id,
                    (CharacterRelation.from_character_id == target.id)
                    | (CharacterRelation.to_character_id == target.id),
                )
            )
        )
        .scalars()
        .all()
    )
    results = []
    for r in rels[:10]:
        other_id = r.to_character_id if r.from_character_id == target.id else r.from_character_id
        results.append(
            {
                "target": id_to_name.get(other_id, "?"),
                "relation_type": r.relation_type or "",
                "category": r.category or "",
                "intimacy": r.intimacy or 0,
                "description": (r.description or "")[:100],
            }
        )
    return json.dumps({"character": target.name, "relations": results}, ensure_ascii=False)


async def _query_foreshadows(
    fs_service: ForeshadowService, chapter_number: int, filter_type: str
) -> str:
    """查伏笔状态。"""
    results = []
    if filter_type in ("overdue", "all"):
        overdue = await fs_service.get_overdue_foreshadows(chapter_number)
        for f in overdue[:8]:
            results.append(
                {
                    "title": f.title,
                    "status": "超期",
                    "type": f.foreshadow_type,
                    "plant_chapter": f.actual_plant_chapter or f.plant_chapter_number,
                    "target_chapter": f.target_resolve_chapter_number,
                    "content": (f.content or "")[:80],
                }
            )
    if filter_type in ("must_resolve", "all"):
        must = await fs_service.get_must_resolve_foreshadows(chapter_number)
        for f in must[:5]:
            results.append(
                {
                    "title": f.title,
                    "status": "本章必须回收",
                    "type": f.foreshadow_type,
                    "content": (f.content or "")[:80],
                }
            )
    if filter_type in ("upcoming", "all"):
        upcoming = await fs_service.get_pending_resolve_foreshadows(chapter_number, lookahead=5)
        for f in upcoming[:5]:
            results.append(
                {
                    "title": f.title,
                    "status": "即将到期",
                    "type": f.foreshadow_type,
                    "target_chapter": f.target_resolve_chapter_number,
                    "content": (f.content or "")[:80],
                }
            )
    if not results:
        return json.dumps({"message": "没有相关伏笔"}, ensure_ascii=False)
    return json.dumps(results, ensure_ascii=False)


async def _query_item(db: AsyncSession, project_id: int, name: str) -> str:
    """查物品详情。"""
    if not name:
        return json.dumps({"error": "请提供物品名"}, ensure_ascii=False)
    items = (await db.execute(select(Item).where(Item.project_id == project_id))).scalars().all()
    matched = [i for i in items if name in i.name or i.name in name]
    if not matched:
        return json.dumps({"error": f"未找到物品「{name}」"}, ensure_ascii=False)
    results = []
    for i in matched[:3]:
        results.append(
            {
                "name": i.name,
                "category": i.category,
                "rarity": i.rarity,
                "item_type": i.item_type,
                "description": (i.description or "")[:200],
                "owner_name": i.owner_name or "无主",
                "status": i.status,
                "obtained_chapter": i.obtained_chapter,
                "is_key_item": bool(i.is_key_item),
            }
        )
    return json.dumps(results if len(results) > 1 else results[0], ensure_ascii=False)


async def _query_chapter_summary(db: AsyncSession, project_id: int, chapter_number: int) -> str:
    """查指定章节的剧情摘要。"""
    ch = (
        (
            await db.execute(
                select(Chapter)
                .where(Chapter.project_id == project_id, Chapter.chapter_number == chapter_number)
                .order_by(Chapter.id.desc())
            )
        )
        .scalars()
        .first()
    )
    if not ch:
        return json.dumps({"error": f"未找到第{chapter_number}章"}, ensure_ascii=False)
    result = {
        "chapter_number": chapter_number,
        "title": ch.title or "",
        "summary": (ch.summary or "")[:300],
    }
    # 附带剧情分析
    analysis = (
        (
            await db.execute(
                select(PlotAnalysis)
                .where(
                    PlotAnalysis.project_id == project_id,
                    PlotAnalysis.chapter_number == chapter_number,
                )
                .order_by(PlotAnalysis.id.desc())
            )
        )
        .scalars()
        .first()
    )
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
    orgs = (
        (await db.execute(select(Organization).where(Organization.project_id == project_id)))
        .scalars()
        .all()
    )
    matched = [o for o in orgs if name in o.name or o.name in name]
    if not matched:
        return json.dumps({"error": f"未找到组织「{name}」"}, ensure_ascii=False)
    # 成员数
    results = []
    for o in matched[:3]:
        member_count = await db.scalar(
            select(func.count(OrganizationMember.id)).where(
                OrganizationMember.organization_id == o.id, OrganizationMember.status == "active"
            )
        )
        # 查成员列表
        members = (
            (
                await db.execute(
                    select(OrganizationMember)
                    .where(
                        OrganizationMember.organization_id == o.id,
                        OrganizationMember.status == "active",
                    )
                    .limit(10)
                )
            )
            .scalars()
            .all()
        )
        member_list = []
        for m in members:
            ch = (
                await db.execute(select(Character).where(Character.id == m.character_id))
            ).scalar_one_or_none()
            member_list.append({"name": ch.name if ch else "?", "role": m.role or "成员"})
        # 结构信息
        extra = o.structure or {}
        results.append(
            {
                "name": o.name,
                "org_type": o.org_type or "",
                "description": (o.description or "")[:200],
                "power_value": o.power_value or 50,
                "location": o.location or "",
                "motto": o.motto or "",
                "color": o.color or "",
                "member_count": member_count or 0,
                "members": member_list,
                "personality": extra.get("personality", ""),
                "purpose": extra.get("purpose", ""),
                "traits": extra.get("traits", []),
                "relations": o.relations or [],
            }
        )
    return json.dumps(results if len(results) > 1 else results[0], ensure_ascii=False)


async def _query_plot_timeline(
    db: AsyncSession,
    project_id: int,
    current_chapter: int,
    character_name: str = "",
    keyword: str = "",
    from_chapter: int = None,
    to_chapter: int = None,
) -> str:
    """查询剧情演进时间线（方案 C）。

    按角色名或关键词，在指定章节范围内检索 PlotAnalysis，
    提取关键情节点、角色状态变化、冲突进展，拼接为时间线文本。
    用于追溯角色成长弧线、伏笔回收脉络、跨章节因果链。
    """
    if not character_name and not keyword:
        return json.dumps({"error": "请提供角色名或关键词"}, ensure_ascii=False)

    # 确定查询范围
    fc = from_chapter or 1
    tc = to_chapter or (current_chapter - 1)
    if fc > tc:
        return json.dumps({"error": f"起始章节({fc})不能大于结束章节({tc})"}, ensure_ascii=False)
    # 限制范围防止返回过多数据
    if tc - fc > 50:
        fc = tc - 50

    # 查询范围内的 PlotAnalysis
    analyses = (
        (
            await db.execute(
                select(PlotAnalysis)
                .where(
                    PlotAnalysis.project_id == project_id,
                    PlotAnalysis.chapter_number >= fc,
                    PlotAnalysis.chapter_number <= tc,
                )
                .order_by(PlotAnalysis.chapter_number)
            )
        )
        .scalars()
        .all()
    )

    if not analyses:
        return json.dumps({"message": f"第{fc}-{tc}章暂无剧情分析数据"}, ensure_ascii=False)

    # 构建时间线
    timeline = []
    for pa in analyses:
        ch = pa.chapter_number
        entry_parts = []

        # 匹配条件：角色名 or 关键词
        matched = False

        # 检查关键情节点
        kps = pa.key_plot_points or []
        for kp in kps:
            text = kp if isinstance(kp, str) else kp.get("event", kp.get("description", str(kp)))
            if character_name and character_name in text:
                matched = True
            if keyword and keyword in text:
                matched = True
            entry_parts.append(f"  关键事件：{text[:80]}")

        # 检查角色状态变化
        for cs in pa.character_states or []:
            if not isinstance(cs, dict):
                continue
            name = cs.get("character") or cs.get("character_name") or ""
            if character_name and (character_name in name or name in character_name):
                matched = True
                change = cs.get("state_after") or cs.get("mental_change") or cs.get("change", "")
                if change:
                    entry_parts.append(f"  {name}：{str(change)[:80]}")
            elif keyword:
                desc = str(cs)
                if keyword in desc:
                    matched = True
                    entry_parts.append(f"  角色变化：{desc[:80]}")

        # 检查冲突
        for cf in pa.conflicts or []:
            if not isinstance(cf, dict):
                continue
            desc = cf.get("description", cf.get("type", str(cf)))
            if character_name and character_name in desc:
                matched = True
            if keyword and keyword in desc:
                matched = True
            progress = cf.get("resolution_progress", cf.get("status", ""))
            if progress:
                entry_parts.append(f"  冲突：{desc[:60]} → {progress}")

        # 检查伏笔
        for fs in pa.foreshadows or []:
            if not isinstance(fs, dict):
                continue
            title = fs.get("title", fs.get("description", str(fs)))
            if character_name and character_name in title:
                matched = True
            if keyword and keyword in title:
                matched = True

        # 如果没有明确匹配条件（只有 keyword），检查整个分析
        if not matched and keyword:
            raw = pa.raw_response or ""
            if keyword in raw:
                matched = True

        # 如果有角色名但没匹配到具体条目，检查角色名是否在任何字段中出现
        if not matched and character_name:
            all_text = (
                str(pa.key_plot_points)
                + str(pa.character_states)
                + str(pa.conflicts)
                + str(pa.foreshadows)
            )
            if character_name in all_text:
                matched = True

        if matched and entry_parts:
            # 情感曲线
            ec = pa.emotional_curve if isinstance(pa.emotional_curve, dict) else {}
            emotion_tag = f"（情感：{ec.get('end', '')}）" if ec.get("end") else ""
            # 剧情阶段
            stage_tag = f"[{pa.plot_stage}]" if pa.plot_stage else ""
            timeline.append(f"第{ch}章{stage_tag}{emotion_tag}：" + "\n".join(entry_parts))

    if not timeline:
        search_desc = f"角色「{character_name}」" if character_name else f"关键词「{keyword}」"
        return json.dumps(
            {"message": f"第{fc}-{tc}章未找到与{search_desc}相关的剧情演进"}, ensure_ascii=False
        )

    # 限制返回长度
    result_text = "\n\n".join(timeline[:20])
    if len(result_text) > 2000:
        result_text = result_text[:2000] + "\n...(已截断)"

    return json.dumps(
        {
            "range": f"第{fc}-{tc}章",
            "search": character_name or keyword,
            "entries": len(timeline),
            "timeline": result_text,
        },
        ensure_ascii=False,
    )


async def _query_outline(db: AsyncSession, project_id: int, chapter_number: int) -> str:
    """查询指定章节的大纲规划。"""
    outline = (
        (
            await db.execute(
                select(Outline)
                .where(
                    Outline.project_id == project_id,
                    Outline.chapter_number == chapter_number,
                )
                .order_by(Outline.id.desc())
            )
        )
        .scalars()
        .first()
    )
    if not outline:
        return json.dumps({"error": f"未找到第{chapter_number}章的大纲"}, ensure_ascii=False)

    result = {
        "chapter_number": outline.chapter_number,
        "title": outline.title or "",
        "summary": (outline.summary or "")[:500],
        "emotion": outline.emotion or "",
        "goal": outline.goal or "",
    }
    # 关键情节点
    if outline.key_points:
        kps = outline.key_points if isinstance(outline.key_points, list) else []
        result["key_points"] = [str(kp)[:100] for kp in kps[:5]]
    # 涉及角色
    if outline.characters:
        chars = outline.characters if isinstance(outline.characters, list) else []
        result["characters"] = [
            str(c) if isinstance(c, str) else c.get("name", str(c)) for c in chars[:8]
        ]
    # 场景
    if outline.scenes:
        scenes = outline.scenes if isinstance(outline.scenes, list) else []
        result["scenes"] = [str(s)[:80] for s in scenes[:5]]

    # 附带该章节的实际完成状态（如果有的话）
    from app.models.chapter import Chapter

    chapter = (
        (
            await db.execute(
                select(Chapter)
                .where(
                    Chapter.project_id == project_id,
                    Chapter.chapter_number == chapter_number,
                )
                .order_by(Chapter.id.desc())
            )
        )
        .scalars()
        .first()
    )
    if chapter:
        result["actual_status"] = chapter.status
        result["actual_title"] = chapter.title or ""
        if chapter.summary:
            result["actual_summary"] = chapter.summary[:300]
        result["word_count"] = chapter.word_count or 0

    return json.dumps(result, ensure_ascii=False)


async def _list_available_entities(db: AsyncSession, project_id: int) -> str:
    """列出项目中所有可查询的实体概要，让 AI 了解全局再精准查询。"""
    # 角色
    chars = (
        (await db.execute(select(Character).where(Character.project_id == project_id)))
        .scalars()
        .all()
    )
    character_list = [
        {
            "name": c.name,
            "role": c.role or "",
            "gender": c.gender or "",
            "status": c.status or "alive",
            "identity": (c.identity or "")[:50],
        }
        for c in chars
    ]

    # 组织
    orgs = (
        (await db.execute(select(Organization).where(Organization.project_id == project_id)))
        .scalars()
        .all()
    )
    organization_list = [
        {
            "name": o.name,
            "org_type": o.org_type or "",
            "location": o.location or "",
        }
        for o in orgs
    ]

    # 地点
    locs = (
        (await db.execute(select(Location).where(Location.project_id == project_id)))
        .scalars()
        .all()
    )
    location_list = [
        {
            "name": l.name,
            "location_type": l.location_type or "",
            "danger_level": l.danger_level or "safe",
        }
        for l in locs
    ]

    # 物品
    items = (await db.execute(select(Item).where(Item.project_id == project_id))).scalars().all()
    item_list = [
        {
            "name": i.name,
            "category": i.category or "",
            "rarity": i.rarity or "",
        }
        for i in items
    ]

    # 职业
    careers = (
        (await db.execute(select(Career).where(Career.project_id == project_id))).scalars().all()
    )
    career_list = [{"name": c.name, "career_type": c.career_type or ""} for c in careers]

    # 世界设定
    worlds = (
        (await db.execute(select(WorldSetting).where(WorldSetting.project_id == project_id)))
        .scalars()
        .all()
    )
    world_setting_list = [{"name": w.name, "category": w.category or ""} for w in worlds]

    result = {
        "total_counts": {
            "characters": len(character_list),
            "organizations": len(organization_list),
            "locations": len(location_list),
            "items": len(item_list),
            "careers": len(career_list),
            "world_settings": len(world_setting_list),
        },
        "characters": character_list,
        "organizations": organization_list,
        "locations": location_list,
        "items": item_list,
        "careers": career_list,
        "world_settings": world_setting_list,
    }
    return json.dumps(result, ensure_ascii=False)


async def _query_location(db: AsyncSession, project_id: int, name: str) -> str:
    """查地点详情（类型、描述、氛围、控制势力、危险等级）。"""
    if not name:
        return json.dumps({"error": "请提供地点名"}, ensure_ascii=False)
    locs = (
        (await db.execute(select(Location).where(Location.project_id == project_id)))
        .scalars()
        .all()
    )
    matched = [l for l in locs if name in l.name or l.name in name]
    if not matched:
        return json.dumps({"error": f"未找到地点「{name}」"}, ensure_ascii=False)
    results = []
    for l in matched[:3]:
        parent_name = ""
        if l.parent_location_id:
            parent = (
                await db.execute(select(Location).where(Location.id == l.parent_location_id))
            ).scalar_one_or_none()
            if parent:
                parent_name = parent.name
        results.append(
            {
                "name": l.name,
                "location_type": l.location_type or "",
                "description": (l.description or "")[:200],
                "atmosphere": l.atmosphere or "",
                "faction_control": l.faction_control or "",
                "geography": l.geography or "",
                "importance": l.importance or "normal",
                "danger_level": l.danger_level or "safe",
                "parent_location": parent_name,
                "first_appear_chapter": l.first_appear_chapter,
            }
        )
    return json.dumps(results if len(results) > 1 else results[0], ensure_ascii=False)


async def _query_career(db: AsyncSession, project_id: int, name: str) -> str:
    """查职业体系详情（类型、描述、进阶阶段、核心能力）。"""
    if not name:
        return json.dumps({"error": "请提供职业名"}, ensure_ascii=False)
    careers = (
        (await db.execute(select(Career).where(Career.project_id == project_id))).scalars().all()
    )
    matched = [c for c in careers if name in c.name or c.name in name]
    if not matched:
        return json.dumps({"error": f"未找到职业「{name}」"}, ensure_ascii=False)
    results = []
    for c in matched[:3]:
        stages_preview = []
        if c.stages and isinstance(c.stages, list):
            for s in c.stages[:5]:
                if isinstance(s, dict):
                    stages_preview.append(f"{s.get('name', '')}(Lv{s.get('level', '?')})")
        results.append(
            {
                "name": c.name,
                "career_type": c.career_type or "",
                "category": c.category or "",
                "description": (c.description or "")[:200],
                "stages": stages_preview,
                "full_stages": c.stages or [],
                "abilities": c.abilities or [],
            }
        )
    return json.dumps(results if len(results) > 1 else results[0], ensure_ascii=False)


async def _query_world_setting(db: AsyncSession, project_id: int, keyword: str) -> str:
    """按关键词查询世界设定条目。"""
    if not keyword:
        return json.dumps({"error": "请提供关键词"}, ensure_ascii=False)
    worlds = (
        (await db.execute(select(WorldSetting).where(WorldSetting.project_id == project_id)))
        .scalars()
        .all()
    )
    matched = [w for w in worlds if keyword in (w.name or "") or keyword in (w.content or "")]
    if not matched:
        return json.dumps({"error": f"未找到与「{keyword}」相关的世界设定"}, ensure_ascii=False)
    results = []
    for w in matched[:5]:
        results.append(
            {
                "name": w.name,
                "category": w.category or "",
                "content": (w.content or "")[:300],
            }
        )
    return json.dumps(results, ensure_ascii=False)
