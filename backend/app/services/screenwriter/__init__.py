"""小说→分镜剧本模块。

模式 B（分离关注点）：
  ① Director（已有）分析音频维度：speaker/emotion/scene/pause
  ② Screenwriter（本模块）补充画面维度：镜头/动作/视觉提示词/时长/音效

两者独立运行，各自用专门的 prompt，质量更高。
最终 Storyshot = 音频字段（来自 Director）+ 画面字段（来自 Screenwriter）。
"""
