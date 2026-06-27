"""FastAPI 主入口"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select

from app.api.routes.admin import router as admin_router
from app.api.routes.auth import router as auth_router
from app.api.routes.compat import router as compat_router
from app.api.routes.global_routes import router as global_router
from app.api.routes.mcp import router as mcp_router
from app.api.routes.project_init import router as project_init_router
from app.api.routes.projects_pkg import router as projects_router
from app.api.routes.prompt_templates import router as prompt_templates_router
from app.api.routes.tasks import router as tasks_router
from app.api.routes.writing_styles import router as writing_styles_router
from app.api.routes.ws_tasks import router as ws_tasks_router
from app.core.auth import get_password_hash
from app.core.database import Base, async_session, engine
from app.models.skill import Skill
from app.models.user import User
from app.skills.builtin import init_builtin_skills

# 默认用户配置
_DEFAULT_USER = {
    "username": os.getenv("MOYU_DEFAULT_USERNAME", "admin"),
    # 生产环境务必通过环境变量设置密码
    "password": os.getenv("MOYU_DEFAULT_PASSWORD", ""),
    "nickname": "管理员",
}


async def _cleanup_zombie_tasks():
    """清理僵尸任务：进程崩溃后残留的 running/pending 任务标记为 failed。"""
    from sqlalchemy import text

    async with engine.begin() as conn:
        # BackgroundTask 表
        await conn.execute(
            text(
                "UPDATE background_tasks SET status='failed', error='进程重启时自动清理（任务未正常完成）' "
                "WHERE status IN ('pending', 'running')"
            )
        )
        # BatchGenerationTask 表
        await conn.execute(
            text(
                "UPDATE batch_generation_tasks SET status='failed', error='进程重启时自动清理' "
                "WHERE status IN ('pending', 'running')"
            )
        )
        # ProjectInitTask 表（旧 init-task）
        await conn.execute(
            text(
                "UPDATE project_init_tasks SET status='failed', error='进程重启时自动清理' "
                "WHERE status IN ('pending', 'running')"
            )
        )


async def _ensure_default_user():
    """确保数据库中至少有一个默认用户（首次启动时自动创建，且为管理员）。"""
    async with async_session() as db:
        exists = (await db.execute(select(User).limit(1))).scalar_one_or_none()
        if not exists:
            user = User(
                username=_DEFAULT_USER["username"],
                password_hash=get_password_hash(_DEFAULT_USER["password"]),
                nickname=_DEFAULT_USER["nickname"],
                is_active=True,
                is_admin=True,  # 第一个用户自动成为管理员
            )
            db.add(user)
            await db.commit()
            print(
                f"[启动] 已创建默认管理员 → 用户名: {_DEFAULT_USER['username']}, "
                f"密码: {_DEFAULT_USER['password']}"
            )


async def _auto_migrate():
    """轻量自动迁移：为已有表补列（SQLite 的 create_all 不会 ALTER 已有表）。

    幂等：列已存在时 ALTER 会报错，捕获忽略。
    新增列时在此登记：(表名, 列定义SQL)
    """
    from sqlalchemy import text

    migrations = [
        # 第1批：AI 多 Provider + 记忆向量
        ("ai_model_configs", "ADD COLUMN provider VARCHAR(20) DEFAULT 'openai'"),
        ("ai_model_configs", "ADD COLUMN embedding_model VARCHAR(100) DEFAULT ''"),
        ("ai_model_configs", "ADD COLUMN frequency_penalty INTEGER"),
        ("ai_model_configs", "ADD COLUMN presence_penalty INTEGER"),
        ("story_memories", "ADD COLUMN user_id INTEGER"),
        ("story_memories", "ADD COLUMN title VARCHAR(200) DEFAULT ''"),
        ("story_memories", "ADD COLUMN vector_id VARCHAR(100) DEFAULT ''"),
        ("story_memories", "ADD COLUMN embedding_model VARCHAR(100) DEFAULT ''"),
        ("story_memories", "ADD COLUMN related_characters JSON"),
        # 第2批：组织树 + 角色职业关联
        ("organizations", "ADD COLUMN parent_org_id INTEGER"),
        ("organizations", "ADD COLUMN tree_level INTEGER DEFAULT 0"),
        ("organizations", "ADD COLUMN power_value INTEGER DEFAULT 50"),
        ("organizations", "ADD COLUMN member_count INTEGER DEFAULT 0"),
        ("organizations", "ADD COLUMN location VARCHAR(200) DEFAULT ''"),
        ("organizations", "ADD COLUMN motto VARCHAR(200) DEFAULT ''"),
        ("organizations", "ADD COLUMN color VARCHAR(20) DEFAULT ''"),
        ("organizations", "ADD COLUMN status VARCHAR(20) DEFAULT 'active'"),
        ("characters", "ADD COLUMN main_career_id INTEGER"),
        ("characters", "ADD COLUMN main_career_stage INTEGER DEFAULT 0"),
        ("characters", "ADD COLUMN sub_careers JSON"),
        # 第3批：剧情分析增强 + 角色状态追踪
        ("characters", "ADD COLUMN status_updated_chapter INTEGER"),
        ("plot_analyses", "ADD COLUMN conflict_types JSON"),
        ("plot_analyses", "ADD COLUMN emotional_curve JSON"),
        ("plot_analyses", "ADD COLUMN organization_states JSON"),
        ("plot_analyses", "ADD COLUMN plot_stage VARCHAR(20) DEFAULT ''"),
        ("plot_analyses", "ADD COLUMN dialogue_ratio FLOAT DEFAULT 0"),
        ("plot_analyses", "ADD COLUMN description_ratio FLOAT DEFAULT 0"),
        ("plot_analyses", "ADD COLUMN pacing VARCHAR(20) DEFAULT ''"),
        # 第5批：用户管理 + 导入导出
        ("users", "ADD COLUMN is_admin BOOLEAN DEFAULT 0"),
        # 大纲模式：1对1 / 1对多
        ("projects", "ADD COLUMN outline_mode VARCHAR(20) DEFAULT 'one_to_one' NOT NULL"),
        ("chapters", "ADD COLUMN sub_index INTEGER DEFAULT 1"),
        # 第6批：初始化流程增强（8步进度 + 重试 + resume）
        ("project_init_tasks", "ADD COLUMN career_done INTEGER DEFAULT 0"),
        ("project_init_tasks", "ADD COLUMN assign_careers_done INTEGER DEFAULT 0"),
        ("project_init_tasks", "ADD COLUMN relations_done INTEGER DEFAULT 0"),
        ("project_init_tasks", "ADD COLUMN locations_done INTEGER DEFAULT 0"),
        ("project_init_tasks", "ADD COLUMN items_done INTEGER DEFAULT 0"),
        ("project_init_tasks", "ADD COLUMN failed_step VARCHAR(100) DEFAULT ''"),
        ("project_init_tasks", "ADD COLUMN chapter_count INTEGER DEFAULT 3"),
        ("project_init_tasks", "ADD COLUMN cancel_requested INTEGER DEFAULT 0"),
        # 第7批：评分系统增强（8维 + 一致性 + 告警）
        ("plot_analyses", "ADD COLUMN consistency_issues JSON"),
        ("chapters", "ADD COLUMN quality_alert VARCHAR(50) DEFAULT ''"),
        # 第8批：批量章节生成连续模式 + 覆盖项（风格/模型/视角/字数）
        ("batch_generation_tasks", "ADD COLUMN start_chapter_number INTEGER"),
        ("batch_generation_tasks", "ADD COLUMN batch_count INTEGER"),
        ("batch_generation_tasks", "ADD COLUMN model_override VARCHAR(100) DEFAULT ''"),
        # 第9批：角色职业境界改为文字描述
        ("characters", "ADD COLUMN main_career_stage_desc VARCHAR(200) DEFAULT ''"),
        ("batch_generation_tasks", "ADD COLUMN style_id INTEGER"),
        ("batch_generation_tasks", "ADD COLUMN narrative_perspective VARCHAR(50) DEFAULT ''"),
        # 第9批：写作风格自定义提示词
        ("writing_styles", "ADD COLUMN custom_prompt TEXT DEFAULT ''"),
        # 第10批：角色副职业
        ("characters", "ADD COLUMN sub_occupations TEXT DEFAULT ''"),
        # 第11批：剧情分析标准报告文本（=== 章节分析报告 ===）
        ("plot_analyses", "ADD COLUMN analysis_report TEXT DEFAULT ''"),
        # 第12批：组织成员后置分配步骤 + 移除地点/物品初始化步骤
        ("project_init_tasks", "ADD COLUMN assign_org_members_done INTEGER DEFAULT 0"),
        # 第13批：提示词自定义开关
        ("skill_configs", "ADD COLUMN is_customized BOOLEAN DEFAULT 0"),
        ("skill_configs", "ADD COLUMN system_prompt_snapshot TEXT DEFAULT ''"),
        # 第14批：大纲验证补全步骤
        ("project_init_tasks", "ADD COLUMN validate_done INTEGER DEFAULT 0"),
        # 第15批：作家文风模仿（范文 + AI 提炼的结构化特征）
        ("writing_styles", "ADD COLUMN author_name VARCHAR(100) DEFAULT ''"),
        ("writing_styles", "ADD COLUMN reference_text TEXT DEFAULT ''"),
        ("writing_styles", "ADD COLUMN style_traits TEXT DEFAULT '{}'"),  # 存 JSON 文本，默认空对象
        ("writing_styles", "ADD COLUMN traits_updated_at DATETIME"),
        ("writing_styles", "ADD COLUMN is_default BOOLEAN DEFAULT 0"),
        # 第16批：推理模型标记（Kimi K2 / DeepSeek-R1 / o1-o3，强制 temperature=1，不发 top_p/penalty）
        ("ai_model_configs", "ADD COLUMN reasoning_model BOOLEAN DEFAULT 0"),
        # 第18批：推理深度选择
        ("ai_model_configs", "ADD COLUMN reasoning_effort VARCHAR(10) DEFAULT 'low'"),
        # 第19批：移除冗余的文本职业字段，统一使用职业体系（main_career_id + main_career_stage_desc）
        ("characters", "DROP COLUMN occupation"),
        ("characters", "DROP COLUMN sub_occupations"),
        # 第17批：灵感模式独立参数（NULL=跟随全局模型配置）
        ("ai_model_configs", "ADD COLUMN inspiration_temperature INTEGER"),
        ("ai_model_configs", "ADD COLUMN inspiration_top_p INTEGER"),
        ("ai_model_configs", "ADD COLUMN inspiration_frequency_penalty INTEGER"),
        ("ai_model_configs", "ADD COLUMN inspiration_presence_penalty INTEGER"),
        # 第18批：灵感模式自定义开关
        ("ai_model_configs", "ADD COLUMN inspiration_custom BOOLEAN DEFAULT 0"),
        # 第20批：Diff Rewrite 润色 API（独立于章节生成）
        ("ai_model_configs", "ADD COLUMN rewrite_base_url VARCHAR(500) DEFAULT ''"),
        ("ai_model_configs", "ADD COLUMN rewrite_api_key VARCHAR(500) DEFAULT ''"),
        ("ai_model_configs", "ADD COLUMN rewrite_model VARCHAR(100) DEFAULT ''"),
        # 第21批：存储清理/改写前的原始 AI 输出
        ("chapters", "ADD COLUMN raw_output TEXT DEFAULT ''"),
    ]
    async with engine.begin() as conn:
        for table, col_def in migrations:
            try:
                await conn.execute(text(f"ALTER TABLE {table} {col_def}"))
            except Exception:
                pass  # 列已存在，忽略


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时创建表
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # 轻量迁移：为已有表补列
    await _auto_migrate()
    # 清理僵尸任务（进程崩溃后残留的 running/pending 任务）
    await _cleanup_zombie_tasks()
    # 初始化默认用户
    await _ensure_default_user()
    # 初始化内置 Skills（builtin.py 是唯一真相源，自动处理用户自定义版本）
    # 设环境变量 MOYU_RESET_PROMPTS=1 启动可一键清除所有用户自定义提示词
    async with async_session() as db:
        if os.getenv("MOYU_RESET_PROMPTS") == "1":
            from app.skills.builtin import force_reset_all_skills

            await force_reset_all_skills(db)
            print("[启动] ✅ 已清除所有用户自定义提示词，恢复为系统默认")
        else:
            await init_builtin_skills(db)
        existing_count = await db.scalar(select(func.count(Skill.id)))
        print(f"[启动] 提示词模板已就绪（数据库共 {existing_count or 0} 个 Skill）")
    # 同步 Skill 表到 PromptTemplate 版本管理表（首次部署 + 新增 Skill 自动同步）
    async with async_session() as db:
        from app.models.prompt_template import PromptTemplate, PromptVersion

        synced = 0
        all_skills = (await db.execute(select(Skill))).scalars().all()
        for skill in all_skills:
            pt_name = skill.name.upper()
            existing_pt = (
                await db.execute(select(PromptTemplate).where(PromptTemplate.name == pt_name))
            ).scalar_one_or_none()
            if not existing_pt:
                pt = PromptTemplate(
                    name=pt_name,
                    category=skill.category or "other",
                    description=skill.description or skill.display_name or skill.name,
                    is_system=True,
                )
                db.add(pt)
                await db.flush()
                ver = PromptVersion(
                    template_id=pt.id,
                    version=1,
                    system_prompt=skill.system_prompt or "",
                    user_prompt="",
                    variables=skill.parameters or {},
                    config={},
                    is_active=True,
                )
                db.add(ver)
                await db.flush()
                pt.current_version_id = ver.id
                synced += 1
            else:
                # 兜底修复：旧数据可能存在 PromptTemplate 但无 PromptVersion（current_version_id 为 NULL，
                # 版本表为空），导致「提示词模板」页面点开后右侧空白。这里自动补建一个 v1 激活版本。
                if not existing_pt.current_version_id:
                    existing_versions = (
                        (
                            await db.execute(
                                select(PromptVersion).where(
                                    PromptVersion.template_id == existing_pt.id
                                )
                            )
                        )
                        .scalars()
                        .all()
                    )
                    if not existing_versions:
                        ver = PromptVersion(
                            template_id=existing_pt.id,
                            version=1,
                            system_prompt=skill.system_prompt or "",
                            user_prompt="",
                            variables=skill.parameters or {},
                            config={},
                            is_active=True,
                        )
                        db.add(ver)
                        await db.flush()
                        existing_pt.current_version_id = ver.id
                        synced += 1
                        continue
                if existing_pt.current_version_id:
                    active_ver = (
                        await db.execute(
                            select(PromptVersion).where(
                                PromptVersion.id == existing_pt.current_version_id
                            )
                        )
                    ).scalar_one_or_none()
                    if active_ver and active_ver.system_prompt != skill.system_prompt:
                        active_ver.system_prompt = skill.system_prompt or ""
                        active_ver.variables = skill.parameters or {}
                        synced += 1
        if synced:
            await db.commit()
            print(f"[启动] PromptTemplate 同步完成（{synced} 个更新）")
    yield
    await engine.dispose()


app = FastAPI(title="AI Novel Studio", version="1.0.0", lifespan=lifespan)

# CORS
# 注意：allow_credentials=True 时，allow_origins 不能用 "*"（浏览器规范禁止）
# 显式列出允许的前端来源；通过环境变量 CORS_ORIGINS 可扩展
_allowed_origins = os.environ.get(
    "CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _allowed_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 路由（注册顺序很重要：全局静态路由必须先于 projects 动态路由注册）
app.include_router(auth_router)
# 全局接口（/api/ai-models、/api/skills、/api/global-inspire 等）
app.include_router(global_router)
app.include_router(projects_router)
# 前端扁平化兼容路由（/api/books、/api/chapters 等）
app.include_router(compat_router)
# 提示词模板版本管理路由
app.include_router(prompt_templates_router)
# 写作风格管理
app.include_router(writing_styles_router)
app.include_router(project_init_router)
app.include_router(tasks_router)
app.include_router(ws_tasks_router)
app.include_router(admin_router)
app.include_router(mcp_router)

# 前端静态文件
frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.exists(frontend_dir):
    app.mount("/assets", StaticFiles(directory=os.path.join(frontend_dir, "assets")), name="assets")

    @app.get("/")
    @app.get("/{path:path}")
    async def serve_frontend(path: str = ""):
        # API 路由不走前端
        if path.startswith("api/"):
            return {"error": "not found"}
        file_path = (
            os.path.join(frontend_dir, path) if path else os.path.join(frontend_dir, "index.html")
        )
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(frontend_dir, "index.html"))
