from __future__ import annotations

import html as html_lib
import re
import urllib.parse
import urllib.request
from typing import Optional

from jarvis.core.events import CancelToken
from jarvis.core.types import ToolResult, ToolSpec

USER_AGENT = "Mozilla/5.0 (Macintosh; Apple Silicon) AppleWebKit/605.1.15 (KHTML, like Gecko) Jarvis/0.1"

_TAG = re.compile(r"(?s)<[^>]+>")
_DROP = re.compile(r"(?is)<(script|style|noscript|svg|head)[^>]*>.*?</\1>")
_RESULT = re.compile(r'(?is)<a[^>]+class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>')
_SNIPPET = re.compile(r'(?is)<a[^>]+class="result__snippet"[^>]*>(.*?)</a>')


def strip_html(page: str, limit: int) -> str:
    page = _DROP.sub(" ", page)
    text = _TAG.sub(" ", page)
    text = html_lib.unescape(text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()[:limit]


def _ddg_url(href: str) -> str:
    if href.startswith("//"):
        href = "https:" + href
    parsed = urllib.parse.urlparse(href)
    qs = urllib.parse.parse_qs(parsed.query)
    if "uddg" in qs:
        return qs["uddg"][0]
    return href


class WebRuntime:
    """Local web tools: fetch a URL and search via DuckDuckGo. No API key."""

    def __init__(self, *, timeout: float = 20.0, max_chars: int = 4000) -> None:
        self.timeout = timeout
        self.max_chars = max_chars

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    def tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="webtools.fetch",
                server="webtools",
                raw_name="fetch",
                description="Fetch a URL and return its readable text (use for web browsing / reading a page).",
                input_schema={"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
                read_only=True,
                idempotent=True,
            ),
            ToolSpec(
                name="webtools.search",
                server="webtools",
                raw_name="search",
                description="Search the web and return the top results (title, URL, snippet).",
                input_schema={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
                read_only=True,
                idempotent=True,
            ),
        ]

    def _get(self, url: str) -> str:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310
            return resp.read().decode("utf-8", "replace")

    async def call(self, name: str, arguments: dict, *, cancel: Optional[CancelToken] = None) -> ToolResult:
        import asyncio

        if cancel:
            cancel.raise_if_cancelled()
        try:
            if name == "webtools.fetch":
                url = str(arguments.get("url", "")).strip()
                if not url:
                    return ToolResult(call_id="", name=name, ok=False, error="missing url")
                page = await asyncio.to_thread(self._get, url)
                return ToolResult(call_id="", name=name, ok=True, content=strip_html(page, self.max_chars))
            if name == "webtools.search":
                query = str(arguments.get("query", "")).strip()
                if not query:
                    return ToolResult(call_id="", name=name, ok=False, error="missing query")
                html = await asyncio.to_thread(
                    self._get, "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote_plus(query)
                )
                titles = _RESULT.findall(html)
                snippets = [strip_html(s, 200) for s in _SNIPPET.findall(html)]
                lines = []
                for i, (href, title) in enumerate(titles[:6]):
                    snippet = snippets[i] if i < len(snippets) else ""
                    lines.append(f"- {strip_html(title, 160)}\n  {_ddg_url(href)}\n  {snippet}")
                content = "\n".join(lines) or "No results."
                return ToolResult(call_id="", name=name, ok=True, content=content[: self.max_chars])
        except Exception as e:  # noqa: BLE001
            return ToolResult(call_id="", name=name, ok=False, error=f"{type(e).__name__}: {e}")
        return ToolResult(call_id="", name=name, ok=False, error=f"unknown tool: {name}")
