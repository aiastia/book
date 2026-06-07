"""灵感模式：步骤向导（递减温度 + 重试 + 格式校验 + 失败降级）+ 快速补全"""
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
    """灵感步骤统一执行：递减温度 + 重试 + 格式校验 + 失败降级。"""
    sys_skill = await engine.get_skill(f"inspiration_{step_name}_system")
    usr_skill = await engine.get_skill(f"inspiration_{step_name}_user")
    if not sys_skill or not usr_skill:
        raise HTTPException(500, f"灵感步骤模板 {step_name} 不完整")

    sys_prompt = substitute_vars(sys_skill.system_prompt, ctx)
    usr_prompt = substitute_vars(usr_skill.system_prompt, ctx)
    messages = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": usr_prompt}]

    result = await ai_client.chat_json_retry(
        messages=messages, temperature=INSPIRATION_TEMPERATURES.get(step_name, 0.7), max_retries=3
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
        "existing": existing, "user_prompt": "请补全缺失的字段",
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
        "existing": existing, "user_prompt": "请补全缺失的字段",
    })
    check_skill_error(result)
    return result.get("json") or {}
