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

## 🗄️ 数据库切换

默认使用 SQLite（零配置），生产环境可切换 MySQL 或 PostgreSQL，**只需改一行连接字符串**。

### PostgreSQL

```bash
# 1. 安装异步驱动（加入 requirements.txt 或 pip install）
pip install asyncpg

# 2. 修改 .env
MOYU_DATABASE_URL=postgresql+asyncpg://用户名:密码@地址:5432/数据库名

# 3. 重启（自动建表，无需手动迁移）
```

### MySQL

```bash
# 1. 安装异步驱动
pip install aiomysql

# 2. 修改 .env
MOYU_DATABASE_URL=mysql+aiomysql://用户名:密码@地址:3306/数据库名

# 3. 重启（自动建表）
```

> 所有数据库操作走 SQLAlchemy ORM（数据库无关），切换零代码改动。
> JSON 字段需 MySQL 5.7+ 或 PostgreSQL 9.2+ 原生支持。

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
│   │   ├── models/          # SQLAlchemy 数据模型（25+ 表）
│   │   ├── services/        # 业务服务（章节/上下文/伏笔/记忆/工具）
│   │   ├── skills/          # Skill 引擎 + 内置提示词模板
│   │   └── api/routes/      # API 路由（198 个端点）
│   ├── data/                # SQLite + ChromaDB（git 忽略）
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/                # Nuxt 3 前端（原 nuxt-app）
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

## 🔑 首次使用

### 默认账号

首次启动后端时，如果数据库中没有用户，会自动创建管理员账号：
- 用户名：`admin`（可通过 `MOYU_DEFAULT_USERNAME` 修改）
- 密码：通过 `MOYU_DEFAULT_PASSWORD` 环境变量设置（**生产环境必须设置**，留空则不创建）

```bash
# .env 中设置
MOYU_DEFAULT_USERNAME=admin
MOYU_DEFAULT_PASSWORD=your-secure-password
```

登录后可在「用户管理」页创建更多用户。

### AI 模型配置

在「AI 设置」页配置模型：
1. 选择 Provider（OpenAI 兼容 / Anthropic / Gemini）
2. 填入 Base URL 和 API Key
3. 点击「获取可用模型」选择模型
4. （可选）配置 Embedding 模型启用向量记忆检索

支持的 Provider：
- **OpenAI 兼容**（推荐）：支持 DeepSeek / Moonshot / 智谱 / 自建中转等所有 OpenAI 格式接口
- **Anthropic**：Claude 系列
- **Google Gemini**：Gemini 系列

### 创建第一个项目

1. 进入「我的书架」→ 点击「创建新项目」
2. 选择大纲模式：
   - **传统模式 (1→1)**：一个大纲对应一个章节，简单直接，适合短篇
   - **细化模式 (1→N)**（推荐）：一个大纲可展开为多个章节，灵活控制，适合长篇
3. 填写标题、题材、简介
4. 创建后点击「AI 生成」自动初始化（世界观→组织→职业→角色→关系→地点→物品→大纲）

## 📝 核心功能说明

### 大纲模式（1对1 / 1对多）

- **传统模式 (1→1)**：生成大纲后自动创建对应章节（章号一一对应）
- **细化模式 (1→N)**：生成大纲后不建章节，点击「展开为多章」将一条大纲拆成 2-10 个章节（AI 自动规划每章剧情/关键事件/角色焦点/情感基调）
- 模式创建后不可更改

### 章节生成的连贯性

生成章节时，AI 会收到：
- **预加载**：本章大纲、前 2 章剧情分析（情感结尾/关键转折/伏笔动态/改进建议）、核心世界观、写作风格、前文剧情回顾（最近 10 章摘要链）
- **向量记忆召回**：从所有历史记忆中语义检索最相关的 3 条（ChromaDB + 本地 Embedding）
- **工具调用（Function Calling）**：AI 可主动查询角色档案、伏笔状态、物品归属、前文章节、组织详情、角色关系——按需获取，不是全量灌入
- **动态上下文压缩**：角色/物品/地点只注入本章涉及的，500 章后上下文稳定在 ~8K 字

### 提示词模板系统

所有 AI 生成功能（世界观/角色/大纲/章节/分析等）的提示词都存在数据库中，可在「提示词模板」页编辑：
- 修改后立即生效（无需重启）
- 支持版本管理
- 内置 59 个 skill 提示词，覆盖全部生成场景

### 记忆向量检索

- **向量库**：ChromaDB（本地持久化）
- **零 API 成本**：完全本地运行，不调外部 API
- **可切换模型**（通过 `.env` 的 `EMBEDDING_MODEL`）：
  - `jinaai/jina-embeddings-v2-base-zh`（默认，768维，~300MB，质量更高）
  - `BAAI/bge-small-zh-v1.5`（备选，512维，~100MB，更轻量更快）
- **5 路融合检索**：最近章节 / 语义相关 / 角色相关 / 重要情节 / 未完结伏笔
- Docker 中两个模型都预下载 + volume 持久化缓存

### 后台任务

- 批量生成、项目初始化等耗时操作走后台任务队列
- 右下角浮动面板实时显示进度（当前生成第几章、完成数/总数）
- 支持取消、重试
- 进程重启时自动清理僵尸任务

## ❓ FAQ

### Q: 章节生成失败怎么办？
A: 检查 AI 设置页的模型配置是否正确（点「测试连通」），确认 API Key 有效。超时失败可在右下角任务面板重试。

### Q: 向量记忆检索不工作？
A: 进入「故事记忆」页，点「重建向量索引」。首次使用会下载 Embedding 模型（~100MB），之后本地运行零成本。模型下载失败会自动回退到 API 模式。

### Q: 如何切换 AI 模型？
A: 在「AI 设置」页添加新的模型配置并设为默认。章节生成、分析等会自动使用默认模型。

### Q: 数据存在哪里？
A: SQLite 数据库在 `backend/data/moyu.db`，向量库在 `backend/data/chroma_db/`。Docker 部署时通过 volume 持久化。

### Q: 如何备份数据？
A: 复制 `backend/data/` 目录即可。或使用「导出」功能导出完整项目 JSON。

### Q: 支持多用户吗？
A: 支持。管理员在「用户管理」页创建用户，每个用户只能访问自己的项目（权限隔离）。

## 🤝 贡献

欢迎提 Issue 和 PR。

## 📄 License

MIT
