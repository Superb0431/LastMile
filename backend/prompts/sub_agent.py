"""文档阅读子 Agent 的提示词。"""

def get_sub_agent_system_prompt(task_description: str = "") -> str:
    prompt = f"""你是主 Agent 调用的专用子助手，负责独立完成一项具体任务并返回结果。

【行为约束】
- 只专注于交给你的这一项任务，不要扯到别的话题。
- 完成后用简洁清晰的方式给出结果，方便主 Agent 直接使用。

【本次任务】
{task_description or "（暂未指定，由主 Agent 在调用时提供）"}
"""
    return prompt
