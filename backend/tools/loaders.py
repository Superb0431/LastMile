"""加载工具说明和 Skill。"""

from backend.config import SKILLS_DIR


def run_tools_loader(tool_name: str) -> str:
    from backend.tools import registry

    tool_def = registry.get_tool_definition(tool_name)
    if tool_def is None:
        return f"没有找到名为“{tool_name}”的工具。"

    function = tool_def.get("function", {})
    name = function.get("name", tool_name)
    description = function.get("description", "（无描述）")
    params = function.get("parameters", {}).get("properties", {})

    lines = [f"工具「{name}」的完整说明：", f"功能：{description}", "参数："]
    if not params:
        lines.append("  （这个工具不需要参数）")
    else:
        for param_name, param_info in params.items():
            param_desc = param_info.get("description", "")
            param_type = param_info.get("type", "")
            lines.append(f"  - {param_name}（{param_type}）：{param_desc}")
    return "\n".join(lines)


def run_skill_loader(skill_name: str) -> str:
    skill_md = SKILLS_DIR / skill_name / "SKILL.md"
    if not skill_md.exists():
        return f"没有找到名为“{skill_name}”的技能（缺少 {skill_md}）。"

    content = skill_md.read_text(encoding="utf-8")
    return f"技能「{skill_name}」的内容如下：\n\n{content}"
