#!/usr/bin/env bash
# 墨语小说 - 端到端自动化测试脚本
# 用法：bash test_e2e.sh
# 测试内容：登录 → 建项目 → 灵感 → 世界观 → 角色 → 关系 → 大纲 → SSR刷新
# 前提：后端已启动（./dev.sh backend），且 AI 设置页已配置可用的模型

set -e
BASE="${API_BASE:-http://localhost:8000}"
# 颜色
G='\033[0;32m'; R='\033[0;31m'; Y='\033[1;33m'; N='\033[0m'
PASS=0; FAIL=0

ok()   { echo -e "${G}✅ $1${N}"; PASS=$((PASS+1)); }
fail() { echo -e "${R}❌ $1${N}"; FAIL=$((FAIL+1)); }
info() { echo -e "${Y}▶ $1${N}"; }

echo "============================================"
echo "  墨语小说 端到端测试  ($(date '+%H:%M:%S'))"
echo "============================================"

# 1. 后端健康检查
info "1. 后端健康检查"
CODE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/docs")
[ "$CODE" = "200" ] && ok "后端在线 (/docs → 200)" || { fail "后端未响应 ($CODE)"; exit 1; }

# 2. 登录
info "2. 登录"
TOKEN=$(curl -s -X POST "$BASE/api/auth/login" -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}' | python3 -c "import sys,json;print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null)
[ -n "$TOKEN" ] && ok "登录成功" || { fail "登录失败"; exit 1; }
AUTH="Authorization: Bearer $TOKEN"

# 3. AI 模型配置检查（关键：配置不生效会导致后续所有 AI 功能失败）
info "3. AI 模型配置检查"
MODELS=$(curl -s "$BASE/api/ai-models" -H "$AUTH" | python3 -c "
import sys,json
data=json.load(sys.stdin)
default=[m for m in data if m.get('is_default')]
print('OK' if default else 'NO_DEFAULT')
print(default[0]['model'] if default else '', end='')
" 2>/dev/null)
if echo "$MODELS" | grep -q OK; then
  ok "AI 模型配置存在: $(echo $MODELS | tail -c +3)"
else
  fail "未配置默认 AI 模型！请先在 AI 设置页配置（否则所有生成功能会失败）"
fi

# 4. 创建项目
info "4. 创建项目"
PID=$(curl -s -X POST "$BASE/api/projects" -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"title":"E2E测试书","genre":"都市","synopsis":"测试用"}' | python3 -c "import sys,json;print(json.load(sys.stdin).get('id',''))" 2>/dev/null)
[ -n "$PID" ] && ok "创建项目成功 (id=$PID)" || fail "创建项目失败"

# 5. 测试 genre 数组归一化（之前 'Input should be a valid string' 的 bug）
info "5. genre 数组归一化测试"
RES=$(curl -s -X POST "$BASE/api/projects" -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"title":"数组测试","genre":["都市","玄幻"],"synopsis":null}')
echo "$RES" | grep -q '"id"' && ok "genre=[数组] 不再报错" || fail "genre 数组仍报错: $RES"

# 6. 灵感模式 - title 步骤（真实 AI）
info "6. 灵感模式 title 步骤（真实 AI 调用）"
INSPIRE=$(curl -s -m 60 -X POST "$BASE/api/projects/global-inspiration/step/title" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"initial_idea":"重生回高三，这次我要改写命运"}')
OPTS=$(echo "$INSPIRE" | python3 -c "import sys,json;d=json.load(sys.stdin);print(len(d.get('options',[])))" 2>/dev/null)
if [ -n "$OPTS" ] && [ "$OPTS" -ge 3 ]; then
  ok "灵感生成成功 ($OPTS 个选项)"
else
  fail "灵感生成失败: $(echo $INSPIRE | head -c 100)"
fi

# 7. 世界观生成（验证存库 bug 已修）
info "7. 世界观生成（验证存库）"
WORLD=$(curl -s -m 90 -X POST "$BASE/api/projects/$PID/worlds/generate" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"genre":"都市","idea":"隐藏在都市的修仙世界"}')
WCOUNT=$(echo "$WORLD" | python3 -c "import sys,json;print(json.load(sys.stdin).get('count',0))" 2>/dev/null)
if [ -n "$WCOUNT" ] && [ "$WCOUNT" -ge 1 ]; then
  ok "世界观生成并存库成功 ($WCOUNT 条)"
  # 验证能查到
  LIST=$(curl -s "$BASE/api/projects/$PID/worlds" -H "$AUTH" | python3 -c "import sys,json;print(len(json.load(sys.stdin)))" 2>/dev/null)
  [ "$LIST" = "$WCOUNT" ] && ok "世界观查询一致 ($LIST 条)" || fail "世界观查询不一致: 生成$WCOUNT 查到$LIST"
else
  fail "世界观生成失败: $(echo $WORLD | head -c 100)"
fi

# 8. 角色生成（验证存库 bug 已修）
info "8. 角色生成（验证存库）"
CHAR=$(curl -s -m 90 -X POST "$BASE/api/projects/$PID/characters/generate" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"role_type":"主角","extra":""}')
CNAME=$(echo "$CHAR" | python3 -c "import sys,json;print(json.load(sys.stdin).get('name',''))" 2>/dev/null)
[ -n "$CNAME" ] && ok "角色生成并存库成功 ($CNAME)" || fail "角色生成失败: $(echo $CHAR | head -c 100)"

# 9. 角色关系自动建立
info "9. 角色关系图谱"
GRAPH=$(curl -s "$BASE/api/projects/$PID/relations/graph" -H "$AUTH")
NNODES=$(echo "$GRAPH" | python3 -c "import sys,json;print(len(json.load(sys.stdin).get('nodes',[])))" 2>/dev/null)
[ "$NNODES" -ge 1 ] && ok "关系图谱正常 ($NNODES 个角色节点)" || fail "关系图谱异常"

# 10. SSR 页面刷新（验证不再 500）
info "10. SSR 页面刷新测试（不再 500）"
for page in dashboard worldview characters outline chapters; do
  CODE=$(curl -s -o /dev/null -w "%{http_code}" -H "Cookie: moyu_token=$TOKEN; moyu_current_project=$PID" "http://localhost:3000/$page")
  [ "$CODE" = "200" ] && ok "  刷新 /$page → $CODE" || fail "  刷新 /$page → $CODE (应200)"
done

# 11. 错误处理测试（[object Object] 不再出现）
info "11. JSON 清洗测试（单元级）"
cd backend && source venv/bin/activate 2>/dev/null
python3 -c "
import sys; sys.path.insert(0,'.')
from app.services.json_helper import clean_json_response, parse_json
cases = [
    \"{'prompt':'x','options':['a','b','c']}\",          # 单引号
    '\`\`\`json\n{\"options\":[\"a\",\"b\"]}\n\`\`\`',   # markdown
    '好的：{\"options\":[\"a\"]} 以上',                  # 前后文字
]
ok_count = 0
for c in cases:
    try:
        r = parse_json(clean_json_response(c))
        if r is not None: ok_count += 1
    except: pass
print('JSON清洗通过率: %d/%d' % (ok_count, len(cases)))
sys.exit(0 if ok_count == len(cases) else 1)
" && ok "JSON 清洗全部通过" || fail "JSON 清洗部分失败"
cd ..

# 汇总
echo ""
echo "============================================"
echo -e "  结果: ${G}通过 $PASS${N} / ${R}失败 $FAIL${N}"
echo "============================================"
[ "$FAIL" = "0" ] && echo -e "${G}🎉 全部通过！${N}" || echo -e "${R}⚠️  有 $FAIL 项失败，请查看上方详情${N}"
