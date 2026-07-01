# 小说 → SSML 流水线

把小说正文转成带感情标注的 Azure TTS SSML。

## 架构

```
小说正文
   │
   ▼ ① Director(调 LLM)
   │   不改剧情,只分析每句的 speaker / emotion / scene / pause
   │   输出 Director JSON
   ▼ ② SSML Builder(纯程序)
   │   吃 Director JSON + 角色配置 + 场景配置
   │   映射成 prosody(值全由配置决定,不可能出 dB 这种错)
   ▼ ③ 输出 SSML → 交给 Azure TTS 合成 MP3
```

核心原则:**AI 永远不碰 XML。** AI 只输出 JSON 分析结果,SSML 由程序 + 配置拼接。

## 快速开始

### 1. 安装依赖

```bash
cd tts-pipeline
pip install -r requirements.txt
```

### 2. 配置 LLM

```bash
cp .env.example .env
# 编辑 .env,填入 LLM base_url / api_key / model
# 可直接复用墨语主项目 .env 里的 MOYU_AI_* 那组
```

### 3. 命令行使用

```bash
# 小说.txt → SSML(调 LLM 分析)
python cli.py 小说.txt -o ssml.xml --voice zh-CN-XiaoxiaoNeural

# 保存 Director 分析结果(下次不用重新调 LLM)
python cli.py 小说.txt --save-director director.json -o ssml.xml

# 用已有的 Director JSON 直接拼 SSML(不调 LLM)
python cli.py --director director.json -o ssml.xml
```

### 4. HTTP 服务

```bash
python api.py
# 默认监听 http://localhost:8001
```

接口:
- `POST /convert` — 一键:小说正文 → SSML
- `POST /build` — 只跑 Builder:Director JSON → SSML
- `GET /health` — 健康检查

## 配置

### 角色 `config/characters.yaml`

speaker(Director 分析产出)→ 语音参数。改这里就改声音,不用改代码。

```yaml
KailanWeak:        # 凯兰病弱态
  rate: "-15%"
  pitch: "-5%"
  style: "calm"
```

### 场景 `config/scenes.yaml`

场景预设,场景切换后持续生效直到下一次切换。和角色参数叠加。

```yaml
battle:            # 战斗场景
  rate: "+8%"
  pause: "150ms"
```

## 测试

```bash
python tests/test_builder.py
```

不调真实 LLM,用 mock 数据验证 Builder 的角色映射、场景叠加、自动分段、XML 转义。

## 目录结构

```
tts-pipeline/
├── novel_pipeline/
│   ├── models.py        # 数据模型
│   ├── llm_client.py    # OpenAI 兼容接口封装
│   ├── director.py      # ① 导演分析
│   └── builder.py       # ② SSML Builder
├── config/
│   ├── characters.yaml  # 角色映射配置
│   └── scenes.yaml      # 场景预设配置
├── tests/
│   └── test_builder.py  # Builder 测试
├── api.py               # FastAPI 服务
├── cli.py               # 命令行工具
├── requirements.txt
└── .env.example
```
