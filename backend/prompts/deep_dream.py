"""Deep Dream 的提示词。"""

DEEP_DREAM_SUMMARY_INSTRUCTION = """
[SystemNotice] 请对以上对话做上下文压缩摘要。

**只输出摘要文本，禁止调用任何工具。**

请严格按以下结构输出（保留标题）：

## 初始意图（INITIAL INTENT）
用 1-2 句话概括用户**第一条诉求**（INITIAL INTENT）。这是最重要的信息——重复强调三次：INITIAL INTENT 决定后续所有建议方向。

## 当前关注点（CURRENT FOCUS）
用户**当前**最关心的问题是什么？（CURRENT FOCUS）

## 计划与进展（PLAN STATUS）
列出对话中出现的主要计划/待办，并标记状态：
- [已完成] …
- [进行中] …
- [待办] …

## 关键医疗信息（KEY FACTS）
浓缩重要的数值、诊断、用药、过敏史、**具体日期**（精确到日）。

---
IMPORTANT: INITIAL INTENT 必须准确。CURRENT FOCUS 必须反映最新状态。只输出上述结构化摘要，不要其他内容。
""".strip()

DEEP_DREAM_SUMMARY_INSTRUCTION_EVAL = DEEP_DREAM_SUMMARY_INSTRUCTION


def get_deep_dream_summary_instruction(eval_mode: bool = False) -> str:
    if eval_mode:
        return DEEP_DREAM_SUMMARY_INSTRUCTION_EVAL
    return DEEP_DREAM_SUMMARY_INSTRUCTION
