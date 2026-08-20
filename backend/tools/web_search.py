"""联网搜索工具。"""

import json

from tavily import TavilyClient

from backend.config import SEARCH_SAFE_MODE, SEARCH_WHITELIST_PATH, TAVILY_API_KEY


def _load_trusted_domains() -> list[str]:
    if not SEARCH_WHITELIST_PATH.exists():
        return []
    try:
        data = json.loads(SEARCH_WHITELIST_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    domains = data.get("trusted_domains", [])
    return [str(d).strip() for d in domains if str(d).strip()]


def run_web_search(query: str, max_results: int = 1, safe: bool | None = None) -> str:
    if not TAVILY_API_KEY:
        return "（搜索失败：没有配置 TAVILY_API_KEY，请在 .env 里填上 Tavily 密钥）"

    use_safe = SEARCH_SAFE_MODE if safe is None else safe
    search_kwargs: dict = {"query": query, "max_results": max_results}
    if use_safe:
        domains = _load_trusted_domains()
        if not domains:
            return "（安全搜索模式已开启，但白名单为空，请检查 search_whitelist.json）"
        search_kwargs["include_domains"] = domains

    try:
        client = TavilyClient(api_key=TAVILY_API_KEY)
        response = client.search(**search_kwargs)
        results = response.get("results", [])
        if not results:
            return json.dumps([], ensure_ascii=False)

        slim = [
            {
                "url": item.get("url", ""),
                "title": item.get("title", ""),
                "content": item.get("content", ""),
            }
            for item in results
        ]
        return json.dumps(slim, ensure_ascii=False, indent=2)

    except Exception as error:
        return f"（搜索出错：{error}）"
