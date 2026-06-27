"""项目路由共享基础：imports、Pydantic schemas、辅助函数。

所有子模块从此导入，避免重复。保持本文件只放"共享"内容，不放业务路由。
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ai_client import AIClient
from app.models.project import Project
from app.skills.engine import SkillEngine


def make_router() -> APIRouter:
    """创建项目级路由器（所有子模块共用同一 prefix）"""
    return APIRouter(prefix="/api/projects", tags=["项目"])


# ============ Pydantic Schemas ============
class ProjectCreate(BaseModel):
    title: str
    genre: str = ""
    synopsis: str = ""
    target_word_count: int = 0
    narrative_pov: str = "第三人称"
    writing_style: dict = {}
    outline_mode: str = "one_to_one"  # one_to_one / one_to_many

    @field_validator("title", "genre", "synopsis", "narrative_pov", mode="before")
    @classmethod
    def _coerce_str(cls, v):
        """字符串字段归一化：接受 None/数组/对象，统一转字符串。

        解决前端快速模式下 genre 可能是数组、或某些字段为 null 时
        导致 'Input should be a valid string' 的问题。
        """
        if v is None:
            return ""
        if isinstance(v, str):
            return v
        if isinstance(v, (list, tuple)):
            items = [str(x).strip() for x in v if x is not None and str(x).strip()]
            return "、".join(items)
        return str(v)


class ProjectUpdate(BaseModel):
    title: str | None = None
    genre: str | None = None
    synopsis: str | None = None
    narrative_pov: str | None = None
    writing_style: dict | None = None
    status: str | None = None
    target_word_count: int | None = None


class ChapterCreate(BaseModel):
    chapter_number: int
    title: str = ""
    content: str = ""
    outline_id: int | None = None  # 关联的大纲（1对多模式）
    sub_index: int = 1  # 大纲下的子章节序号
    expansion_plan: dict | None = None  # 1对多模式的展开计划
    generation_mode: str = "one_to_one"


class ChapterUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    status: str | None = None
    expansion_plan: dict | None = (
        None  # 章节规划（情节概要/关键事件/涉及角色/情感基调/冲突类型/叙事目标/预估字数）
    )


class OutlineCreate(BaseModel):
    chapter_number: int
    title: str = ""
    summary: str = ""
    scenes: list = []
    characters: list = []
    key_points: list = []
    emotion: str = ""
    goal: str = ""
    structure: dict = {}


class CharacterCreate(BaseModel):
    name: str
    role: str = "配角"
    gender: str = ""
    age: str = ""
    identity: str = ""
    appearance: str = ""
    personality: str = ""
    background: str = ""
    growth_experience: str = ""
    ability: str = ""
    story_goal: str = ""
    motivation: str = ""
    weakness: str = ""
    arc_type: str = ""
    character_change: str = ""
    speech_style: str = ""
    status: str = "alive"
    mental_state: str = ""
    main_career_id: int | None = None
    main_career_stage: int = 0  # 旧，保留兼容
    main_career_stage_desc: str = ""  # 主职业境界描述
    sub_careers: list = []
    organization_id: int | None = None


class ForeshadowCreate(BaseModel):
    title: str
    content: str = ""
    foreshadow_type: str = ""
    status: str = "pending"
    source_type: str = "manual"
    plant_chapter_number: int | None = None
    target_resolve_chapter_number: int | None = None
    priority: int = 5
    structure: dict = {}  # 扩展字段（重要性0-1/强度/隐藏度/暗示文本/关联角色等）


class WorldSettingCreate(BaseModel):
    name: str
    category: str = ""
    content: str = ""
    structure: dict = {}


class OrgCreate(BaseModel):
    name: str
    org_type: str = ""
    description: str = ""


class OutlineGenerateRequest(BaseModel):
    chapter_count: int = 10


class OutlineContinueRequest(BaseModel):
    chapter_count: int = 10
    story_direction: str = ""  # 故事发展方向（可选）
    plot_stage: str = ""  # 情节阶段：开端/发展/高潮/转折/结局（可选）
    narrative_pov: str = ""  # 叙事视角（空=按小说设定）
    other_requirements: str = ""  # 其他要求（可选）
    ai_model: str = ""  # 指定模型id（空=使用默认模型）


class OutlineExpandRequest(BaseModel):
    target_chapter_count: int = 3
    # 展开模式：new=首次展开（已展开则报错）/ replace=覆盖旧章节重新规划 / append=在已有章节后追加
    mode: str = "new"
    # 展开策略：balanced=均衡分配 / climax=高潮重点 / detail=细节丰富
    strategy: str = "balanced"


class BatchExpandRequest(BaseModel):
    target_chapter_count: int = 3


class InspireRequest(BaseModel):
    idea: str


class InspirationStepRequest(BaseModel):
    initial_idea: str
    title: str = ""
    description: str = ""
    theme: str = ""


class BatchCharacterRequest(BaseModel):
    count: int = 5
    requirements: str = ""


class AutoCharacterGenerateRequest(BaseModel):
    analysis_result: dict = {}
    specification: str = ""


class OrgGenerateRequest(BaseModel):
    user_input: str = ""


class AutoOrgGenerateRequest(BaseModel):
    analysis_result: dict = {}
    specification: str = ""


class ChapterRegenerateRequest(BaseModel):
    instructions: str = ""
    include_analysis: bool = True


class PartialRegenerateRequest(BaseModel):
    selected_text: str
    context_before: str = ""
    context_after: str = ""
    user_instructions: str = ""
    length_requirement: str = ""


class AiDenoisingRequest(BaseModel):
    text: str


class BookImportSuggestRequest(BaseModel):
    title: str = ""
    sampled_text: str


class BookImportOutlinesRequest(BaseModel):
    project_id: int
    start_chapter: int = 1
    end_chapter: int = 5
    chapters_text: str


class BookImportUploadRequest(BaseModel):
    """拆书上传：text 或 base64 二选一，filename 可选（用于推断书名）。"""

    filename: str = ""
    title: str = ""
    text: str = ""
    base64: str = ""


class BookImportDeconstructRequest(BaseModel):
    """一键拆解：采样方向 + 采样章数 + 大纲拆解章数。"""

    sample_side: str = "head"  # head(前N章) / tail(后N章)
    sample_count: int = 5  # 立项采样章数
    outline_chapters: int = 20  # 大纲拆解章数（连续前N章，按5章/批）


class McpToolTestRequest(BaseModel):
    plugin_name: str
    tool_list: list = []


# ============ 辅助函数 ============
def substitute_vars(prompt: str, context: dict) -> str:
    """替换提示词中的变量占位符 {key}"""
    for key, value in context.items():
        prompt = prompt.replace(f"{{{key}}}", str(value) if value is not None else "")
    return prompt


async def get_user_project(db: AsyncSession, project_id: int, user) -> Project:
    """获取当前用户的指定项目（含权限校验），不存在/无权则抛 404。

    所有项目子资源端点必须调用此函数校验项目归属。
    """
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.user_id == user.id)
    )
    proj = result.scalar_one_or_none()
    if not proj:
        raise HTTPException(404, "项目不存在或无权访问")
    return proj


async def make_engine_and_client(db: AsyncSession, user_id: int, model_override: str = None):
    """快速创建 SkillEngine + AIClient（用户配置优先）。各模块复用。

    model_override: 若指定，则用用户默认配置的 base_url/key 但替换为指定 model
    （供续写/批量生成等弹窗动态选择模型，空则用默认模型）。
    """
    engine = SkillEngine(db, user_id)
    if model_override:
        # 用默认配置的连接信息 + 指定模型
        try:
            from app.models.ai_model import AIModelConfig

            result = await db.execute(
                select(AIModelConfig).where(
                    AIModelConfig.user_id == user_id,
                    AIModelConfig.is_default == True,
                )
            )
            cfg = result.scalar_one_or_none()
            if cfg:
                ai_client = AIClient(
                    base_url=cfg.base_url,
                    api_key=cfg.api_key,
                    model=model_override,
                    provider=cfg.provider or cfg.backend_type or "openai",
                    embedding_model=cfg.embedding_model or "",
                    reasoning_model=cfg.reasoning_model or False,
                    **AIClient._defaults_from_cfg(cfg),
                )
                return engine, ai_client
        except Exception:
            pass
    ai_client = await AIClient.from_user_config(db, user_id)
    return engine, ai_client


def check_skill_error(result: dict):
    """检查 execute_skill 返回是否含错误，有则抛 500。各模块复用。"""
    if result.get("error"):
        raise HTTPException(500, result["error"])
