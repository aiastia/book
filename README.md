# 墨语 — AI 小说创作平台

基于 AI 的长篇网文创作辅助平台，对标 MuMuAINovel，提供从世界观构建到章节生成的全链路创作工具。

## ✨ 核心功能

- **世界观构建**：核心世界观 + 详细设定（地理/历史/势力/科技等），按题材自动适配规则
- **角色管理**：完整角色档案（外貌/性格/背景/动机/弱点/人物弧光），支持 AI 批量生成
- **组织势力**：组织树（父子层级）+ 成员管理（职位/忠诚度/贡献度）
- **职业体系**：主/副职业 + 进阶阶段 + 能力列表
- **物品道具**：分类/稀有度/属性/持有者/关键剧情道具
- **地点地图**：层级地点 + 氛围/危险等级/势力控制
- **故事大纲**：1对1（传统）/ 1对多（细化）两种模式
- **章节生成**：AI 创作带连贯性增强（前2章分析 + 向量记忆召回 + 工具调用）
- **剧情分析**：多维度分析（钩子/冲突/情感曲线/角色状态/质量评分）
- **伏笔系统**：完整闭环（规划→埋设→回收→超期提醒）
- **记忆系统**：ChromaDB 向量检索（本地 embedding，零 API 成本）
- **章节阅读器**：带记忆标注的沉浸式阅读
- **批量生成**：后台逐章顺序生成 + 进度追踪
- **章节重写**：全章重写/局部重写/扩写缩写 + 版本历史对比
- **导入导出**：全量 JSON / 整书 TXT / 拆书导入
- **后台任务**：通用任务队列 + 浮动进度面板

## 🚀 快速部署（Docker）

### 前置条件

- Docker + Docker Compose
- 一个 OpenAI 兼容的 API Key（支持 OpenAI / DeepSeek / Moonshot / 智谱等）

### 步骤

```bash
# 1. 克隆仓库
git clone https://github.com/你的用户名/book.git
cd book

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，填入你的 AI API Key
vi .env

# 3. 一键启动
docker compose up -d --build

# 4. 访问
# 前端：http://localhost:3000
# 后端文档：http://localhost:8000/docs
```

### 数据持久化

- SQLite 数据库：`backend/data/moyu.db`
- ChromaDB 向量库：`backend/data/chroma_db/`
- 通过 docker-compose volumes 自动挂载，容器重建数据不丢失

## 💻 本地开发

### 前置条件

- Python 3.12+
- Node.js 20+
- npm

### 启动

```bash
# 后端
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000

# 前端（另开终端）
cd frontend
npm install
npm run dev
```

访问 http://localhost:3000，首次启动会自动创建默认用户（用户名 `admin`，密码 `admin123`）。

## ⚙️ 配置说明

所有配置通过环境变量（`.env` 文件），带 `MOYU_` 前缀：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `MOYU_SECRET_KEY` | JWT 密钥（生产环境必须修改） | 内置默认值 |
| `MOYU_AI_BASE_URL` | AI API 地址 | `https://api.openai.com/v1` |
| `MOYU_AI_API_KEY` | AI API Key | 必填 |
| `MOYU_AI_MODEL` | 默认 AI 模型 | `gpt-4o` |
| `MOYU_DATABASE_URL` | 数据库连接 | `sqlite+aiosqlite:///./data/moyu.db` |
| `MOYU_PORT` | 后端端口 | `8000` |

详细配置见 `.env.example`。

## 🏗️ 技术栈

**后端**：Python 3.12 / FastAPI / SQLAlchemy (async) / SQLite / ChromaDB / fastembed

**前端**：Nuxt 3 (SSR) / Vue 3 / Ant Design Vue / Vue Flow

**AI**：OpenAI 兼容接口 / Function Calling / 本地 Embedding (BAAI/bge-small-zh-v1.5)

## 🔄 CI/CD

推送到 main 分支自动触发 GitHub Actions，构建 Docker 镜像并推送到 GHCR：

```bash
# 使用预构建镜像（无需本地构建）
docker pull ghcr.io/你的用户名/book/backend:latest
docker pull ghcr.io/你的用户名/book/frontend:latest
```

## 📁 项目结构

```
book/
├── backend/                 # FastAPI 后端
│   ├── app/
│   │   ├── core/            # AI 客户端 / 配置 / 数据库 / 认证
│   │   ├── models/          # SQLAlchemy 数据模型（20+ 表）
│   │   ├── services/        # 业务服务（章节/上下文/伏笔/记忆/工具）
│   │   ├── skills/          # Skill 引擎 + 内置提示词模板
│   │   └── api/routes/      # API 路由（198 个端点）
│   ├── data/                # SQLite + ChromaDB（git 忽略）
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/                # Nuxt 3 前端
│   ├── pages/               # 页面（28 个）
│   ├── components/          # 组件
│   ├── composables/         # 组合式函数（API/导航/项目上下文）
│   ├── Dockerfile
│   └── package.json
├── .github/workflows/       # GitHub Actions CI/CD
├── docker-compose.yml       # 一键部署
├── .env.example             # 环境变量模板
└── dev.sh                   # 本地开发脚本
```

## 📄 License

MIT
