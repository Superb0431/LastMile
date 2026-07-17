"""main."""

import uuid
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.config import ensure_dirs, PROJECT_ROOT
from backend.memory import db
from backend.agent import approval
from backend.tools import tool_cache_gateway
from backend.queue import redis_bus

@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_dirs()
    db.init_db()
    try:
        tool_cache_gateway._client.ping()
        redis_bus.ensure_group()
        print("[启动] Redis 连接正常，工具缓存与任务队列已就绪。")
    except Exception as error:
        print(f"[启动] 警告：连不上 Redis（{error}）。工具缓存将降级，任务队列不可用，重启任务前请先启动worker.py。")
    yield

app = FastAPI(title="医疗随访 Agent", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    username: str
    message: str
    chat_id: str | None = None

class ApproveRequest(BaseModel):
    chat_id: str
    toolcall_id: str
    approved: bool

@app.get("/api/chats")
def get_chats(username: str):
    return {"chats": db.list_chats(username)}

@app.get("/api/chats/{chat_id}/messages")
def get_chat_messages(chat_id: str, username: str):
    rows = db.get_messages(chat_id, username)
    messages = [
        {
            "role": row["role"],
            "content": row["content"],
            "tool_name": row["tool_name"],
            "tool_args": row["tool_args"],
            "toolcall_id": row["toolcall_id"],
            "tool_calls": row["tool_calls"],
        }
        for row in rows
    ]
    return {"chat_id": chat_id, "messages": messages}

@app.post("/api/chat/submit")
def submit_chat(req: ChatRequest):
    chat_id = req.chat_id or _new_chat_id()
    task_id = redis_bus.submit_task(chat_id, req.username, req.message)
    return {"task_id": task_id, "chat_id": chat_id}

@app.get("/api/chat/result/{task_id}")
def get_chat_result(task_id: str, cursor: int = 0):
    status = redis_bus.get_status(task_id)
    if status is None:
        return {"status": "not_found", "cursor": cursor, "events": []}
    events, new_cursor = redis_bus.read_events(task_id, cursor)
    return {"status": status, "cursor": new_cursor, "events": events}

@app.post("/api/approve")
def post_approve(req: ApproveRequest):
    ok = approval.provide_approval(req.chat_id, req.toolcall_id, req.approved)
    return {"ok": ok}

def _new_chat_id() -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    suffix = uuid.uuid4().hex[:4]
    return f"chat-{stamp}-{suffix}"

_frontend_dir = PROJECT_ROOT / "frontend"
if _frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(_frontend_dir), html=True), name="frontend")
