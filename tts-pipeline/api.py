"""
小说→SSML 流水线的 FastAPI 服务。

独立运行,不和墨语主项目耦合。墨语通过 HTTP 调用本服务。

启动:
  cd tts-pipeline && python api.py
  或: uvicorn api:app --host 0.0.0.0 --port 8001

环境变量(.env):
  LLM_BASE_URL   LLM API 根地址
  LLM_API_KEY    LLM 密钥
  LLM_MODEL      模型名
"""
import os
import logging
from typing import Optional, List, Dict

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from novel_pipeline.director import Director
from novel_pipeline.builder import SSMLBuilder
from novel_pipeline.llm_client import LLMClient
from novel_pipeline.models import DirectorLine, SceneChange

# 加载 .env
load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="小说→SSML 流水线", version="1.0.0")

# CORS:允许墨语前端/后端调用
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── 请求/响应模型 ──────────────────────────────────────────────

class ConvertRequest(BaseModel):
    """一键转换:小说正文 → Director 分析 → SSML。"""
    text: str = Field(..., description="小说正文(纯文本)")
    voice: str = Field("zh-CN-XiaoxiaoNeural", description="Azure 语音名")
    # LLM 配置(可选,缺省时用 .env 里的)
    llm_base_url: Optional[str] = None
    llm_api_key: Optional[str] = None
    llm_model: Optional[str] = None
    # 可选:自定义角色/场景配置
    characters: Optional[Dict] = None
    scenes: Optional[Dict] = None
    chunk_size: int = Field(800, description="分块大小(字符)")


class BuildRequest(BaseModel):
    """只跑 Builder:Director JSON → SSML(不调 LLM)。"""
    director_json: List[Dict] = Field(..., description="Director 指令列表")
    voice: str = "zh-CN-XiaoxiaoNeural"
    characters: Optional[Dict] = None
    scenes: Optional[Dict] = None


class ConvertResponse(BaseModel):
    success: bool
    ssml_parts: List[str] = Field(default_factory=list)
    director_json: Optional[List[Dict]] = None
    stats: Optional[Dict] = None
    error: Optional[str] = None


# ── 辅助 ──────────────────────────────────────────────────────

def _to_json(instructions) -> List[Dict]:
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


def _parse_json(raw_list: List[Dict]):
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


# ── 路由 ──────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {
        "service": "小说→SSML 流水线",
        "version": "1.0.0",
        "endpoints": {
            "POST /convert": "小说正文一键转 SSML(Director + Builder)",
            "POST /build": "Director JSON 转 SSML(只跑 Builder)",
            "GET /health": "健康检查",
        },
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.post("/convert", response_model=ConvertResponse)
async def convert(request: ConvertRequest):
    """一键转换:小说正文 → Director(LLM)→ SSML。"""
    try:
        # LLM 配置:请求参数优先,缺省用 .env
        base_url = request.llm_base_url or os.getenv("LLM_BASE_URL")
        api_key = request.llm_api_key or os.getenv("LLM_API_KEY")
        model = request.llm_model or os.getenv("LLM_MODEL", "glm-4-plus")

        if not base_url or not api_key:
            return ConvertResponse(
                success=False,
                error="缺少 LLM 配置。请在 .env 里设 LLM_BASE_URL / LLM_API_KEY,或在请求参数里传入。",
            )

        # ① Director 分析
        llm = LLMClient(base_url=base_url, api_key=api_key, model=model)
        director = Director(llm_client=llm, chunk_size=request.chunk_size)
        instructions, err = director.analyze(request.text)

        if err:
            return ConvertResponse(
                success=False,
                director_json=_to_json(instructions) if instructions else None,
                error=err,
            )

        # ② Builder
        builder = SSMLBuilder(characters_override=request.characters, scenes_override=request.scenes)
        ssml_parts = builder.build(instructions, voice=request.voice)

        line_count = sum(1 for i in instructions if isinstance(i, DirectorLine))
        scene_count = sum(1 for i in instructions if isinstance(i, SceneChange))
        total_chars = sum(len(i.text) for i in instructions if isinstance(i, DirectorLine))

        return ConvertResponse(
            success=True,
            ssml_parts=ssml_parts,
            director_json=_to_json(instructions),
            stats={
                "lines": line_count,
                "scenes": scene_count,
                "chars": total_chars,
                "ssml_parts": len(ssml_parts),
            },
        )
    except ValueError as e:
        return ConvertResponse(success=False, error=f"配置错误: {str(e)}")
    except Exception as e:
        logger.exception("convert 失败")
        return ConvertResponse(success=False, error=f"内部错误: {str(e)}")


@app.post("/build", response_model=ConvertResponse)
async def build(request: BuildRequest):
    """只跑 Builder:Director JSON → SSML。"""
    try:
        instructions = _parse_json(request.director_json)
        if not instructions:
            return ConvertResponse(success=False, error="director_json 为空或格式不对")

        builder = SSMLBuilder(characters_override=request.characters, scenes_override=request.scenes)
        ssml_parts = builder.build(instructions, voice=request.voice)

        return ConvertResponse(success=True, ssml_parts=ssml_parts, stats={"ssml_parts": len(ssml_parts)})
    except ValueError as e:
        return ConvertResponse(success=False, error=f"配置错误: {str(e)}")
    except Exception as e:
        logger.exception("build 失败")
        return ConvertResponse(success=False, error=f"内部错误: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8001)))
