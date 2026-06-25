"""灵感模式：步骤向导（重试 + 格式校验 + 失败降级）+ 快速补全。

AI 设置页「灵感模式参数」开关：
  关（默认）→ 使用模型全局参数
  开 → 递减温度表控制不同阶段（title 0.8 → genre 0.45），可用滑块覆盖"""
from app.api.routes.projects_pkg.base import *


router = make_router()

# 灵感步骤递减温度（移植自 MuMuAINovel）：title 最有创意，genre 最明确
INSPIRATION_TEMPERATURES = {
    "title": 0.8,
    "description": 0.65,
    "theme": 0.55,
    "genre": 0.45,
}


def _validate_options(data: dict, step_name: str) -> tuple[bool, str]:
    """校验灵感选项返回格式（移植自 MuMuAINovel validate_options_response）"""
    if not isinstance(data, dict):
        return False, "返回格式不是对象"
    options = data.get("options")
    if not isinstance(options, list):
        return False, "缺少 options 数组"
    if len(options) < 3 or len(options) > 10:
        return False, f"选项数量应在 3-10 个之间，当前 {len(options)} 个"
    for i, opt in enumerate(options):
        if not isinstance(opt, str) or not opt.strip():
            return False, f"第 {i+1} 个选项为空或非字符串"
        if len(opt) > 500:
            return False, f"第 {i+1} 个选项过长（>{500} 字）"
    if step_name == "genre":
        for opt in options:
            if len(opt) > 10:
                return False, f"类型标签【{opt}】过长，应在 2-10 字之间"
    return True, ""


async def _run_step(engine, ai_client, step_name: str, ctx: dict) -> dict:
    """灵感步骤统一执行：读取灵感模式独立参数，未配则跟随全局模型配置。"""
    sys_skill = await engine.get_skill(f"inspiration_{step_name}_system")
    usr_skill = await engine.get_skill(f"inspiration_{step_name}_user")
    if not sys_skill or not usr_skill:
        raise HTTPException(500, f"灵感步骤模板 {step_name} 不完整")

    sys_prompt = substitute_vars(sys_skill.system_prompt, ctx)
    usr_prompt = substitute_vars(usr_skill.system_prompt, ctx)
    messages = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": usr_prompt}]

    # 灵感参数开关：关=不传参（走全局模型配置），开=递减温度表+自定义
    insp_kwargs = {}
    try:
        from app.models.ai_model import AIModelConfig
        from sqlalchemy import select
        cfg = (await engine.db.execute(
            select(AIModelConfig).where(
                AIModelConfig.user_id == engine.user_id,
                AIModelConfig.is_default == True,
            )
        )).scalar_one_or_none()
        if cfg and cfg.inspiration_custom:
            # temperature：滑块以 title (0.8) 为基准，按比例缩放所有阶段
            if cfg.inspiration_temperature is not None:
                ratio = (cfg.inspiration_temperature / 100) / INSPIRATION_TEMPERATURES.get("title", 0.8)
                insp_kwargs["temperature"] = INSPIRATION_TEMPERATURES.get(step_name, 0.7) * ratio
            elif step_name in INSPIRATION_TEMPERATURES:
                insp_kwargs["temperature"] = INSPIRATION_TEMPERATURES[step_name]
            # top_p: 滑块设置才传
            if cfg.inspiration_top_p is not None:
                insp_kwargs["top_p"] = cfg.inspiration_top_p / 100
            # frequency_penalty
            if cfg.inspiration_frequency_penalty is not None:
                fp = cfg.inspiration_frequency_penalty
                insp_kwargs["frequency_penalty"] = fp / 100 if abs(fp) > 2 else fp
            # presence_penalty
            if cfg.inspiration_presence_penalty is not None:
                pp = cfg.inspiration_presence_penalty
                insp_kwargs["presence_penalty"] = pp / 100 if abs(pp) > 2 else pp
    except Exception:
        pass

    result = await ai_client.chat_json_retry(
        messages=messages, max_tokens=600, max_retries=3,
        **insp_kwargs,
    )
    # AI 调用本身报错（401/网络等）→ 直接抛出
    if result.get("error") and result.get("json") is None:
        raise HTTPException(500, result["error"])

    data = result.get("json") or {}
    is_valid, err_msg = _validate_options(data, step_name)
    if not is_valid:
        # 降级返回，保证前端不崩
        return {
            "prompt": f"请为【{step_name}】提供内容：",
            "options": ["让 AI 重新生成", "我自己输入"],
            "warning": f"AI 生成格式不规范（{err_msg}），已降级处理，请重试或手动输入",
        }
    return data


@router.post("/{project_id}/inspiration/step/{step_name}")
async def inspiration_step(project_id: int, step_name: str, req: InspirationStepRequest, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """灵感步骤向导：title / description / theme / genre"""
    if step_name not in ("title", "description", "theme", "genre"):
        raise HTTPException(400, f"无效步骤: {step_name}")
    await get_user_project(db, project_id, user)
    engine, ai_client = await make_engine_and_client(db, user.id)
    ctx = {"initial_idea": req.initial_idea, "title": req.title, "description": req.description, "theme": req.theme}
    return await _run_step(engine, ai_client, step_name, ctx)


@router.post("/{project_id}/inspiration/quick-complete")
async def inspiration_quick_complete(project_id: int, req: InspirationStepRequest, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """灵感快速补全"""
    await get_user_project(db, project_id, user)
    engine, ai_client = await make_engine_and_client(db, user.id)
    existing = f"想法:{req.initial_idea}"
    if req.title: existing += f" 书名:{req.title}"
    if req.description: existing += f" 简介:{req.description}"
    if req.theme: existing += f" 主题:{req.theme}"
    result = await engine.execute_skill("inspiration_quick_complete", ai_client, {
        "existing": existing, "user_prompt": "请先审视以上创作片段——逻辑是否自洽？核心机制是否清晰？角色动机是否合理？然后基于你的批判性分析，生成有深度的书名、简介、主题和类型标签。",
    })
    check_skill_error(result)
    return result.get("json") or {}


@router.post("/global-inspiration/step/{step_name}")
async def global_inspiration_step(step_name: str, req: InspirationStepRequest, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """全局灵感步骤向导（无需先建项目）"""
    if step_name not in ("title", "description", "theme", "genre"):
        raise HTTPException(400, f"无效步骤: {step_name}")
    engine, ai_client = await make_engine_and_client(db, user.id)
    ctx = {"initial_idea": req.initial_idea, "title": req.title, "description": req.description, "theme": req.theme}
    return await _run_step(engine, ai_client, step_name, ctx)


@router.post("/global-inspiration/quick-complete")
async def global_inspiration_quick_complete(req: InspirationStepRequest, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """全局灵感快速补全"""
    engine, ai_client = await make_engine_and_client(db, user.id)
    existing = f"想法:{req.initial_idea}"
    if req.title: existing += f" 书名:{req.title}"
    if req.description: existing += f" 简介:{req.description}"
    if req.theme: existing += f" 主题:{req.theme}"
    result = await engine.execute_skill("inspiration_quick_complete", ai_client, {
        "existing": existing, "user_prompt": "请先审视以上创作片段——逻辑是否自洽？核心机制是否清晰？角色动机是否合理？然后基于你的批判性分析，生成有深度的书名、简介、主题和类型标签。",
    })
    check_skill_error(result)
    return result.get("json") or {}
