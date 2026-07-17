"""heartbeat."""

from backend.prompts.main_agent import CACHE_HEARTBEAT_SENTINEL

PROVIDER_CACHE_TTL_SECONDS: dict[str, int] = {
    "openai": 24 * 3600,
    "anthropic": 1 * 3600,
    "deepseek": 24 * 3600,
    "kimi": 1 * 3600,
    "moonshot": 1 * 3600,
    "gemini": 1 * 3600,
}

def get_cache_ttl_seconds(model: str) -> int:
    provider = model.split("/")[0].lower() if model else ""
    return PROVIDER_CACHE_TTL_SECONDS.get(provider, 3600)

async def heartbeat_worker() -> None:
    _ = CACHE_HEARTBEAT_SENTINEL
    return
