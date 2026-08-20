"""工具注册、参数校验和渐进式加载。"""

from typing import Callable, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from backend.memory import db
from backend.tools.web_search import run_web_search
from backend.tools.write_record import run_write_record
from backend.tools.read_record import run_read_record
from backend.tools.loaders import run_tools_loader, run_skill_loader
from backend.tools.drug_analyser import run_drug_interaction
from backend.tools.drug_danger import run_check_drug_danger
from backend.tools.read_docs import run_read_docs
from backend.tools.recall_history import run_recall_history


MAX_TOOL_CALLS = 10
LIGHT_DREAM_MAX_TOOL_CALLS = 8

AgentMode = Literal["main", "light_dream"]

LOADER_GATE_MESSAGE = "（工具权限错误：请先调用tools_loader查看工具调用说明）"

_loaded_tools_by_chat: dict[str, set[str]] = {}


class WebSearchArgs(BaseModel):
    model_config = ConfigDict(strict=False, extra="forbid")
    query: str = Field(min_length=1, description="要搜索的关键词或问题")
    max_results: int = Field(default=1, ge=1, description="最多返回几条结果，默认 1")
    safe: bool = Field(default=False, description="为 true 时仅搜索白名单中的可信来源")


class WriteRecordArgs(BaseModel):
    model_config = ConfigDict(strict=False, extra="forbid")
    target: str = Field(
        min_length=1,
        description="写入目标：profile（基本个人信息）| ehr（就诊记录）| interval（症状记录）",
    )
    content: str = Field(default="", description="target=profile 时要追加的内容")
    visit_date: str = Field(default="", description="target=ehr 时到院日期")
    diagnosis: str = Field(default="", description="target=ehr 时诊断疾病")
    chief_complaint: str = Field(default="", description="target=ehr 时主诉")
    exam_results: str = Field(default="", description="target=ehr 时检查结果")
    treatment: str = Field(default="", description="target=ehr 时医生处置")
    notes: str = Field(default="", description="target=ehr 时备注")
    symptom_date: str = Field(default="", description="target=interval 时症状日期")
    symptoms: str = Field(default="", description="target=interval 时症状描述")


class ReadRecordArgs(BaseModel):
    model_config = ConfigDict(strict=False, extra="forbid")
    target: str = Field(
        default="all",
        description="读取目标：profile | ehr | interval | all（默认 all）",
    )
    recent_n: Optional[int] = Field(
        default=None,
        ge=1,
        description="仅对 EHR/Interval 生效：只返回最近 N 条记录（profile 不受限）",
    )


class ToolsLoaderArgs(BaseModel):
    model_config = ConfigDict(strict=False, extra="forbid")
    tool_name: str = Field(min_length=1, description="想了解的工具名字")


class SkillLoaderArgs(BaseModel):
    model_config = ConfigDict(strict=False, extra="forbid")
    skill_name: str = Field(min_length=1, description="想加载的技能名字")


class DrugInteractionArgs(BaseModel):
    model_config = ConfigDict(strict=False, extra="forbid")
    drugs: list[str] = Field(
        min_length=2,
        description="要检查的药物英文通用名列表（至少2种），如 ['Methotrexate', 'Aspirin']",
    )


class CheckDrugDangerArgs(BaseModel):
    model_config = ConfigDict(strict=False, extra="forbid")
    drug_name: str = Field(min_length=1, description="要查询的药物名称（中文或英文）")


class ReadDocsArgs(BaseModel):
    model_config = ConfigDict(strict=False, extra="forbid")
    query: str = Field(min_length=1, description="检索意图，如：最新指南中如何诊断 Alport 综合征")


class RecallHistoryArgs(BaseModel):
    model_config = ConfigDict(strict=False, extra="forbid")
    request: str = Field(
        min_length=1,
        description="检索意图，如：找到所有关于去医院拍CT没带钱的记录",
    )
    recent_dialogue: str = Field(
        default="",
        description="当前用户问题及最近两轮对话原文（从上下文摘录，便于提炼关键词）",
    )


_TOOL_SPECS: list[dict] = [
    {
        "name": "web_search",
        "description": (
            "联网搜索。当你不确定医学事实、需要最新资料或外部知识时使用；"
            "用户拒绝授权时，说明情况并用已有知识回复。"
        ),
        "args_model": WebSearchArgs,
        "parameters": WebSearchArgs.model_json_schema(),
        "handler": run_web_search,
        "requires_approval": True,
        "needs_username": False,
        "main_agent": True,
        "light_dream": False,
        "full_in_prompt": True,
        "cache_policy": "redis",
        "cache_ttl_seconds": 3600,
    },
    {
        "name": "read_record",
        "description": (
            "读取用户档案（Profile / 就诊记录 EHR / 院外症状 Interval）。"
            "当 Profile 或 Summary 未覆盖所需细节（症状、就诊、检查数值、时间等）时，应主动查询；"
            "可先 tools_loader('read_record') 了解参数。"
        ),
        "args_model": ReadRecordArgs,
        "parameters": ReadRecordArgs.model_json_schema(),
        "handler": run_read_record,
        "requires_approval": False,
        "needs_username": True,
        "main_agent": True,
        "light_dream": True,
        "full_in_prompt": False,
        "cache_policy": "bypass",
    },
    {
        "name": "write_record",
        "description": (
            "写入用户档案（Profile / EHR / Interval）。"
            "仅在记忆整理阶段，将对话中提取的信息落库时使用。"
        ),
        "args_model": WriteRecordArgs,
        "parameters": WriteRecordArgs.model_json_schema(),
        "handler": run_write_record,
        "requires_approval": False,
        "needs_username": True,
        "main_agent": False,
        "light_dream": True,
        "full_in_prompt": False,
        "cache_policy": "bypass",
    },
    {
        "name": "tools_loader",
        "description": (
            "加载某工具的完整参数说明。"
            "当你要调用工具但尚不清楚其参数格式时使用。"
        ),
        "args_model": ToolsLoaderArgs,
        "parameters": ToolsLoaderArgs.model_json_schema(),
        "handler": run_tools_loader,
        "requires_approval": False,
        "needs_username": False,
        "main_agent": True,
        "light_dream": False,
        "full_in_prompt": True,
        "cache_policy": "redis",
        "cache_ttl_seconds": 86400,
    },
    {
        "name": "skill_loader",
        "description": (
            "加载某技能的完整内容。"
            "当你需要借助专项技能（如健康建议模板）指导回复时使用。"
        ),
        "args_model": SkillLoaderArgs,
        "parameters": SkillLoaderArgs.model_json_schema(),
        "handler": run_skill_loader,
        "requires_approval": False,
        "needs_username": False,
        "main_agent": True,
        "light_dream": False,
        "full_in_prompt": True,
        "cache_policy": "redis",
        "cache_ttl_seconds": 86400,
    },
    {
        "name": "drug_interaction",
        "description": (
            "检查多种药物之间是否存在高危联用风险。"
            "传入药物英文通用名列表，返回两两组合的风险结论。"
            "当用户提到多种药物、或需要评估联用安全性时使用。"
        ),
        "args_model": DrugInteractionArgs,
        "parameters": DrugInteractionArgs.model_json_schema(),
        "handler": run_drug_interaction,
        "requires_approval": False,
        "needs_username": False,
        "main_agent": True,
        "light_dream": True,
        "full_in_prompt": True,
        "cache_policy": "bypass",
    },
    {
        "name": "check_drug_danger",
        "description": (
            "查询药物是否为高危警示或特殊管理药品。"
            "在向用户推荐具体药物之前必须先调用本工具；"
            "若在高危目录中，禁止直接推荐，应提醒需医生处方。"
        ),
        "args_model": CheckDrugDangerArgs,
        "parameters": CheckDrugDangerArgs.model_json_schema(),
        "handler": run_check_drug_danger,
        "requires_approval": False,
        "needs_username": False,
        "main_agent": True,
        "light_dream": False,
        "full_in_prompt": True,
        "cache_policy": "bypass",
    },
    {
        "name": "read_docs",
        "description": (
            "检索本地权威医学指南与共识。"
            "当需要依据指南诊断标准、治疗建议或共识结论作答时使用；"
            "返回分析摘要与 doc_id，回复末尾应标注参考资料。"
        ),
        "args_model": ReadDocsArgs,
        "parameters": ReadDocsArgs.model_json_schema(),
        "handler": run_read_docs,
        "requires_approval": False,
        "needs_username": False,
        "main_agent": True,
        "light_dream": False,
        "full_in_prompt": True,
        "cache_policy": "bypass",
    },
    {
        "name": "recall_history",
        "description": (
            "跨会话检索用户曾经说过的聊天原文。"
            "当用户问「还记得」「之前说过」「上次提到」等，"
            "且 Profile / Summary / Timeline 不足以还原具体对话细节时使用；"
            "传入检索意图，并尽量附上当前问题与近两轮对话原文。"
        ),
        "args_model": RecallHistoryArgs,
        "parameters": RecallHistoryArgs.model_json_schema(),
        "handler": run_recall_history,
        "requires_approval": False,
        "needs_username": True,
        "main_agent": True,
        "light_dream": False,
        "full_in_prompt": True,
        "cache_policy": "bypass",
    },
]

TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": spec["name"],
            "description": spec["description"],
            "parameters": spec["parameters"],
        },
    }
    for spec in _TOOL_SPECS
]

TOOL_HANDLERS: dict[str, Callable] = {spec["name"]: spec["handler"] for spec in _TOOL_SPECS}
_SPEC_BY_NAME: dict[str, dict] = {spec["name"]: spec for spec in _TOOL_SPECS}


def _specs_for_mode(mode: AgentMode) -> list[dict]:
    key = "main_agent" if mode == "main" else "light_dream"
    return [spec for spec in _TOOL_SPECS if spec.get(key)]


def _build_tool_list(specs: list[dict], *, full_parameters: bool) -> list[dict]:
    tools: list[dict] = []
    for spec in specs:
        if full_parameters or spec["full_in_prompt"]:
            parameters = spec["parameters"]
        else:
            parameters = {"type": "object", "properties": {}}
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": spec["name"],
                    "description": spec["description"],
                    "parameters": parameters,
                },
            }
        )
    return tools


def get_initial_tools(mode: AgentMode = "main") -> list[dict]:
    return _build_tool_list(_specs_for_mode(mode), full_parameters=False)


def get_light_dream_tools() -> list[dict]:
    specs = [spec for spec in _TOOL_SPECS if spec.get("light_dream")]
    return _build_tool_list(specs, full_parameters=True)


def get_tool_definition(tool_name: str) -> Optional[dict]:
    for tool in TOOLS:
        if tool["function"]["name"] == tool_name:
            return tool
    return None


def requires_approval(tool_name: str) -> bool:
    spec = _SPEC_BY_NAME.get(tool_name)
    return bool(spec and spec.get("requires_approval"))


def get_cache_policy(tool_name: str) -> str:
    spec = _SPEC_BY_NAME.get(tool_name)
    return (spec or {}).get("cache_policy", "bypass")


def get_cache_ttl(tool_name: str) -> Optional[int]:
    spec = _SPEC_BY_NAME.get(tool_name)
    return (spec or {}).get("cache_ttl_seconds")


def _scan_loaded_tools_from_db(chat_id: str, username: str) -> set[str]:
    messages = db.get_messages(chat_id, username)
    tool_results = {
        msg["toolcall_id"]: msg["content"]
        for msg in messages
        if msg["role"] == "tool" and msg.get("toolcall_id")
    }
    loaded: set[str] = set()
    for msg in messages:
        if msg.get("role") != "assistant" or msg.get("tool_name") != "tools_loader":
            continue
        args = msg.get("tool_args") or {}
        target = (args.get("tool_name") or "").strip()
        toolcall_id = msg.get("toolcall_id")
        if not target or not toolcall_id:
            continue
        result = tool_results.get(toolcall_id, "")
        if result.startswith("工具「"):
            loaded.add(target)
    return loaded


def hydrate_loaded_tools(chat_id: str, username: str) -> None:
    if not chat_id or chat_id in _loaded_tools_by_chat:
        return
    _loaded_tools_by_chat[chat_id] = _scan_loaded_tools_from_db(chat_id, username)


def mark_tool_loaded(chat_id: str, tool_name: str) -> None:
    target = (tool_name or "").strip()
    if not chat_id or not target:
        return
    _loaded_tools_by_chat.setdefault(chat_id, set()).add(target)

def if_valid(
    tool_call: dict,
    mode: AgentMode = "main",
    chat_id: str = "",
) -> tuple[bool, str]:
    name = tool_call.get("name")
    arguments = tool_call.get("arguments")

    allowed = {spec["name"] for spec in _specs_for_mode(mode)}
    if name not in allowed:
        return False, f"当前阶段不允许调用工具：{name}"

    if name not in TOOL_HANDLERS:
        return False, f"未知的工具名：{name}"

    if not isinstance(arguments, dict):
        return False, "工具参数格式不对（应该是一个对象/字典）。"

    if arguments.get("_parse_error"):
        return False, "工具参数不是合法的 JSON，解析失败。"

    if mode == "main" and chat_id:
        spec = _SPEC_BY_NAME.get(name)
        if spec and not spec["full_in_prompt"]:
            loaded = _loaded_tools_by_chat.get(chat_id, set())
            if name not in loaded:
                return False, LOADER_GATE_MESSAGE

    return True, ""


def check_arguments(tool_name: str, arguments: dict) -> tuple[bool, str]:
    spec = _SPEC_BY_NAME.get(tool_name)
    if spec is None:
        return False, f"未知的工具名：{tool_name}"

    model = spec["args_model"]
    try:
        model.model_validate(arguments)
        return True, ""
    except ValidationError as error:
        problems = []
        for err in error.errors():
            loc = ".".join(str(part) for part in err["loc"]) or "(根)"
            problems.append(f"参数「{loc}」不合法：{err['msg']}")
        return False, "；".join(problems)


def execute_tool(tool_name: str, arguments: dict, username: str) -> str:
    handler = TOOL_HANDLERS[tool_name]
    spec = _SPEC_BY_NAME[tool_name]
    final_args = dict(arguments)
    if spec.get("needs_username"):
        final_args["username"] = username
    return handler(**final_args)
