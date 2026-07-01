"""
本地验证脚本 —— 用 mock Director JSON 测试 Builder,不调真实 LLM。

运行: cd tts-pipeline && python tests/test_builder.py
"""
import sys
import os
import xml.etree.ElementTree as ET

# 让 tts-pipeline/ 成为导入根目录
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from novel_pipeline.models import DirectorLine, SceneChange
from novel_pipeline.builder import SSMLBuilder


# ── 测试数据:基于你那段「凯兰」小说的 mock Director 指令 ────────────────

MOCK_INSTRUCTIONS = [
    SceneChange(scene_change="night"),
    DirectorLine(speaker="Narrator", text="咳了两声。", pause_after=600),
    DirectorLine(speaker="Narrator", text="凯兰把蜜饯罐子塞进枕头底下，顺手拽了拽被角。", pause_after=500),
    DirectorLine(speaker="Narrator", text="门口传来靴子踩石板的声音——不是莉莉安的步子，太重。", pause_after=600),
    DirectorLine(speaker="Messenger", text="殿下，帝国有信。", pause_after=700),
    DirectorLine(speaker="Narrator", text="来人穿着帝国军团的制式甲胄。", pause_after=700),
    DirectorLine(speaker="KailanWeak", text="念。", pause_after=700),
    DirectorLine(speaker="Narrator", text="声音沙哑，刚好沙哑到合适的程度。", pause_after=700),
    DirectorLine(speaker="Messenger", text="奉天青帝国摄政王加布里埃尔之命。", pause_after=400),
    SceneChange(scene_change="suspense"),
    DirectorLine(speaker="Narrator", text="凯兰睁开了眼。", pause_after=700),
    DirectorLine(speaker="KailanCalm", text="知道了。", pause_after=600),
]


def run_tests():
    print("=" * 70)
    print("测试 1: 基本 SSML 构建(角色映射 + 场景叠加 + 停顿)")
    print("=" * 70)
    builder = SSMLBuilder()
    ssml_parts = builder.build(MOCK_INSTRUCTIONS, voice="zh-CN-XiaoxiaoNeural")
    print(f"生成 {len(ssml_parts)} 个 SSML 片段\n")
    print(ssml_parts[0])
    print()

    # 验证 XML 结构合法
    for i, ssml in enumerate(ssml_parts):
        try:
            ET.fromstring(ssml)
            print(f"  片段 {i+1}: XML 合法 ✅")
        except ET.ParseError as e:
            print(f"  片段 {i+1}: XML 非法 ❌ {e}")
            return False

    # 验证无嵌套 prosody
    ssml = ssml_parts[0]
    root = ET.fromstring(ssml)
    ns = {"s": "http://www.w3.org/2001/10/synthesis"}
    for prosody in root.findall(".//s:prosody", ns):
        inner = prosody.findall("s:prosody", ns)
        if inner:
            print(f"  嵌套 prosody ❌ 发现 {len(inner)} 个内层 prosody")
            return False
    print("  无嵌套 prosody ✅")

    # 验证 namespace
    if "ns0:" in ssml or "ns1:" in ssml:
        print("  命名空间 ❌ 出现 ns0/ns1 自动前缀")
        return False
    print("  命名空间正确(mstts:) ✅")

    # 验证无 dB
    if "dB" in ssml:
        print("  prosody 值 ❌ 出现 dB")
        return False
    print("  无 dB 非法值 ✅")

    print()
    print("=" * 70)
    print("测试 2: 场景叠加验证(night 场景 → rate 应叠加)")
    print("=" * 70)
    # Narrator rate=-2%, night scene rate=-5%, 合并应为 -7%
    builder2 = SSMLBuilder()
    test_instr = [
        SceneChange(scene_change="night"),
        DirectorLine(speaker="Narrator", text="测试文本。"),
    ]
    ssml2 = builder2.build(test_instr)[0]
    if 'rate="-7%"' in ssml2:
        print("  Narrator(-2%) + night(-5%) = -7% ✅")
    else:
        print(f"  场景叠加 ❌ 期望 rate=-7%, 实际:")
        # 提取实际 rate
        import re
        rates = re.findall(r'rate="([^"]*)"', ssml2)
        print(f"    rates: {rates}")
        return False

    # battle 场景: Narrator(-2%) + battle(+8%) = +6%
    test_instr2 = [
        SceneChange(scene_change="battle"),
        DirectorLine(speaker="Narrator", text="战斗。"),
    ]
    ssml3 = builder2.build(test_instr2)[0]
    if 'rate="+6%"' in ssml3:
        print("  Narrator(-2%) + battle(+8%) = +6% ✅")
    else:
        print(f"  battle 叠加 ❌ 期望 rate=+6%")
        return False

    # KailanWeak 在 sad 场景: rate=-15% + sad(-10%) = -25%
    test_instr3 = [
        SceneChange(scene_change="sad"),
        DirectorLine(speaker="KailanWeak", text="虚弱。"),
    ]
    ssml4 = builder2.build(test_instr3)[0]
    if 'rate="-25%"' in ssml4:
        print("  KailanWeak(-15%) + sad(-10%) = -25% ✅")
    else:
        print(f"  sad 叠加 ❌ 期望 rate=-25%")
        return False

    print()
    print("=" * 70)
    print("测试 3: 长文本自动分段")
    print("=" * 70)
    # 造 50 行,每行 100 字 = 5000 字,应该分成 2 段
    long_instr = [
        DirectorLine(speaker="Narrator", text="字" * 100, pause_after=300)
        for _ in range(50)
    ]
    ssml_long = builder2.build(long_instr, max_chars=3000)
    print(f"  5000 字输入 → {len(ssml_long)} 个 SSML 片段(期望 2)")
    if len(ssml_long) == 2:
        print("  自动分段 ✅")
    else:
        print(f"  自动分段 ❌ 期望 2 段")
        return False

    print()
    print("=" * 70)
    print("测试 4: XML 特殊字符转义")
    print("=" * 70)
    test_instr4 = [
        DirectorLine(speaker="Narrator", text="A<B 且 C&D。"),
    ]
    ssml5 = builder2.build(test_instr4)[0]
    if "&lt;" in ssml5 and "&amp;" in ssml5:
        print("  特殊字符转义 ✅")
    else:
        print(f"  转义 ❌ 输出: {ssml5}")
        return False

    print()
    print("=" * 70)
    print("测试 5: 未知 speaker 用 default 兜底")
    print("=" * 70)
    test_instr5 = [
        DirectorLine(speaker="UnknownCharacter", text="你好。"),
    ]
    ssml6 = builder2.build(test_instr5)[0]
    # default rate=0%, default scene rate=0%, 合并 = 0%
    if 'rate="0%"' in ssml6:
        print("  未知 speaker 兜底 ✅")
    else:
        print(f"  兜底 ❌")
        return False

    print()
    print("🎉 全部测试通过!")
    return True


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
