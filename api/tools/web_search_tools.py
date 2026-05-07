"""
Web search and research tools — production-grade, no API key required by default.

Tool set modelled after how large AI labs structure web grounding:

  web_search       — query the web (DuckDuckGo by default; Brave Search if key set)
  fetch_page       — fetch a URL and return clean markdown-formatted text
  extract_links    — return all hyperlinks on a page, optionally filtered by domain
  get_page_metadata — return OG/meta tags, canonical URL, and publication date
  research_topic   — orchestrated deep-research: search → multi-source fetch → brief

Environment variables (optional upgrades):
  AGENT_API_BRAVE_SEARCH_KEY  — Brave Search API key for higher-quality results
  AGENT_API_SEARCH_PROXY      — HTTP proxy for outbound search requests
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Annotated

from langchain_core.tools import tool

# ── Constants ──────────────────────────────────────────────────────────────────

_USER_AGENT = "Mozilla/5.0 (compatible; agent-mcp/3.0; +research)"
_DDG_HTML_URL = "https://html.duckduckgo.com/html/"
_BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
_FETCH_TIMEOUT = 20
_SEARCH_TIMEOUT = 12
_MAX_FETCH_CHARS = 12_000
_MAX_SEARCH_RESULTS = 10

# Noise elements to strip before any content extraction
_NOISE_TAGS = (
    "script", "style", "nav", "header", "footer", "aside", "form",
    "noscript", "iframe", "svg", "canvas", "dialog", "figure",
    "advertisement", "banner",
)

# SSRF / private network guard
_BLOCKED_SCHEMES = {"file", "ftp", "data", "javascript"}
_PRIVATE_PREFIXES = ("10.", "192.168.", "172.16.", "172.17.", "172.18.",
                     "172.19.", "172.2", "172.3", "fc00:", "fe80:")
_BLOCKED_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}


# ── Shared helpers ─────────────────────────────────────────────────────────────

def _validate_url(url: str) -> str | None:
    """Return an error string if the URL is disallowed, else None."""
    try:
        p = urllib.parse.urlparse(url)
    except Exception:
        return "Invalid URL format"
    if p.scheme not in ("http", "https"):
        return f"Scheme '{p.scheme}' not allowed (http/https only)"
    host = (p.hostname or "").lower()
    if not host:
        return "No hostname in URL"
    if host in _BLOCKED_HOSTS:
        return f"Requests to '{host}' are not allowed"
    if any(host.startswith(pfx) for pfx in _PRIVATE_PREFIXES):
        return "Requests to private IP ranges are not allowed"
    return None


def _make_request(url: str, *, method: str = "GET", data: bytes | None = None,
                  extra_headers: dict | None = None, timeout: int = 15) -> str:
    """Perform an HTTP request and return response text. Raises on failure."""
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("User-Agent", _USER_AGENT)
    req.add_header("Accept", "text/html,application/json,text/plain,*/*")
    req.add_header("Accept-Language", "en-US,en;q=0.9")
    if extra_headers:
        for k, v in extra_headers.items():
            req.add_header(k, v)

    proxy = os.environ.get("AGENT_API_SEARCH_PROXY")
    if proxy:
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": proxy, "https": proxy})
        )
    else:
        opener = urllib.request.build_opener()

    with opener.open(req, timeout=timeout) as resp:
        ct = resp.headers.get("Content-Type", "")
        raw = resp.read(400_000)

    enc = "utf-8"
    m = re.search(r"charset=([^\s;\"']+)", ct)
    if m:
        enc = m.group(1)
    try:
        return raw.decode(enc)
    except (UnicodeDecodeError, LookupError):
        return raw.decode("utf-8", errors="replace")


def _strip_tags(html: str) -> str:
    """Remove all HTML tags and decode entities."""
    text = re.sub(r"<[^>]+>", " ", html)
    text = (text
            .replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
            .replace("&quot;", '"').replace("&nbsp;", " ").replace("&#39;", "'")
            .replace("&mdash;", "—").replace("&ndash;", "–").replace("&hellip;", "…")
            .replace("&copy;", "©").replace("&reg;", "®").replace("&trade;", "™"))
    text = re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1))), text)
    return re.sub(r"\s+", " ", text).strip()


def _get_domain(url: str) -> str:
    try:
        return urllib.parse.urlparse(url).netloc.lower().lstrip("www.")
    except Exception:
        return url


def _remove_noise(html: str) -> str:
    """Strip boilerplate HTML regions before text extraction."""
    for tag in _NOISE_TAGS:
        html = re.sub(
            rf"<{tag}[^>]*>.*?</{tag}>",
            " ",
            html,
            flags=re.DOTALL | re.IGNORECASE,
        )
    # Remove comments
    html = re.sub(r"<!--.*?-->", " ", html, flags=re.DOTALL)
    # Remove common noise classes / ids
    html = re.sub(
        r'<div[^>]+(class|id)="[^"]*(?:ad|ads|sidebar|promo|banner|cookie|popup|'
        r'newsletter|social|share|related|comment)[^"]*"[^>]*>.*?</div>',
        " ",
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    return html


def _html_to_markdown(html: str, base_url: str = "") -> str:
    """
    Convert cleaned HTML to readable markdown text.

    Converts structural elements to markdown equivalents so the LLM receives
    well-formatted, citation-ready content rather than tag soup.
    """
    html = _remove_noise(html)

    # Attempt to isolate main content region (article > main > body)
    for container_re in (
        r"<article[^>]*>(.*?)</article>",
        r"<main[^>]*>(.*?)</main>",
        r'<div[^>]+(?:class|id)="[^"]*(?:content|post|article|entry|story)[^"]*"[^>]*>(.*?)</div>',
    ):
        m = re.search(container_re, html, re.DOTALL | re.IGNORECASE)
        if m and len(m.group(1)) > 400:
            html = m.group(1)
            break

    # Headings
    def _heading(m: re.Match) -> str:
        level = int(m.group(1))
        text = _strip_tags(m.group(2)).strip()
        return f"\n{'#' * level} {text}\n"

    html = re.sub(r"<h([1-6])[^>]*>(.*?)</h\1>", _heading, html,
                  flags=re.DOTALL | re.IGNORECASE)

    # Paragraphs
    html = re.sub(r"<p[^>]*>(.*?)</p>",
                  lambda m: "\n" + _strip_tags(m.group(1)).strip() + "\n",
                  html, flags=re.DOTALL | re.IGNORECASE)

    # List items
    html = re.sub(r"<li[^>]*>(.*?)</li>",
                  lambda m: "\n- " + _strip_tags(m.group(1)).strip(),
                  html, flags=re.DOTALL | re.IGNORECASE)

    # Code blocks before inline code (order matters)
    html = re.sub(r"<pre[^>]*><code[^>]*>(.*?)</code></pre>",
                  lambda m: "\n```\n" + _strip_tags(m.group(1)) + "\n```\n",
                  html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<pre[^>]*>(.*?)</pre>",
                  lambda m: "\n```\n" + _strip_tags(m.group(1)) + "\n```\n",
                  html, flags=re.DOTALL | re.IGNORECASE)

    # Inline code
    html = re.sub(r"<code[^>]*>(.*?)</code>",
                  lambda m: "`" + _strip_tags(m.group(1)) + "`",
                  html, flags=re.DOTALL | re.IGNORECASE)

    # Links — resolve relative URLs when base_url is provided
    def _link(m: re.Match) -> str:
        href = m.group(1).strip()
        text = _strip_tags(m.group(2)).strip()
        if base_url and href.startswith("/"):
            p = urllib.parse.urlparse(base_url)
            href = f"{p.scheme}://{p.netloc}{href}"
        return f"[{text}]({href})" if text else href

    html = re.sub(
        r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
        _link,
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )

    # Bold / italic
    html = re.sub(r"<(?:strong|b)[^>]*>(.*?)</(?:strong|b)>",
                  lambda m: f"**{_strip_tags(m.group(1))}**",
                  html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<(?:em|i)[^>]*>(.*?)</(?:em|i)>",
                  lambda m: f"*{_strip_tags(m.group(1))}*",
                  html, flags=re.DOTALL | re.IGNORECASE)

    # Line breaks and horizontal rules
    html = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    html = re.sub(r"<hr\s*/?>", "\n---\n", html, flags=re.IGNORECASE)

    # Blockquotes
    html = re.sub(r"<blockquote[^>]*>(.*?)</blockquote>",
                  lambda m: "\n> " + _strip_tags(m.group(1)).replace("\n", "\n> ") + "\n",
                  html, flags=re.DOTALL | re.IGNORECASE)

    # Strip remaining tags
    text = re.sub(r"<[^>]+>", " ", html)

    # Entity cleanup
    text = (text
            .replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
            .replace("&quot;", '"').replace("&nbsp;", " ").replace("&#39;", "'")
            .replace("&mdash;", "—").replace("&ndash;", "–").replace("&hellip;", "…"))
    text = re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1))), text)

    # Normalise whitespace
    text = re.sub(r" {2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ── Search backends ────────────────────────────────────────────────────────────

def _ddg_search(query: str, num_results: int = 6, recency: str | None = None) -> list[dict]:
    """
    Search via DuckDuckGo HTML endpoint (no API key required).

    recency: 'd' last day, 'w' last week, 'm' last month, 'y' last year
    """
    params: dict[str, str] = {"q": query, "kl": "us-en", "kp": "-1"}
    if recency:
        params["df"] = recency

    body = urllib.parse.urlencode(params).encode()
    try:
        html = _make_request(
            _DDG_HTML_URL,
            method="POST",
            data=body,
            extra_headers={"Content-Type": "application/x-www-form-urlencoded",
                           "Referer": "https://html.duckduckgo.com/html/"},
            timeout=_SEARCH_TIMEOUT,
        )
    except Exception as exc:
        return [{"error": f"DuckDuckGo search failed: {exc}"}]

    results: list[dict] = []

    # DDG HTML result blocks are delineated by class="result"
    blocks = re.split(r'<div[^>]+class="[^"]*result[^"]*"', html)
    for block in blocks[1:]:  # first split fragment is preamble
        if len(results) >= num_results:
            break

        # Title + redirect URL
        a_match = re.search(
            r'class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
            block,
            re.DOTALL | re.IGNORECASE,
        )
        if not a_match:
            continue

        redirect = a_match.group(1)
        title = _strip_tags(a_match.group(2)).strip()

        # Decode actual URL from DDG redirect (/l/?uddg=<encoded>)
        uddg_match = re.search(r"[?&]uddg=(https?[^&\"]+)", redirect)
        if uddg_match:
            actual_url = urllib.parse.unquote(uddg_match.group(1))
        elif redirect.startswith("http"):
            actual_url = redirect
        else:
            # Fallback: try the result__url span
            url_span = re.search(r'class="result__url"[^>]*>(.*?)</span>', block, re.DOTALL | re.IGNORECASE)
            if url_span:
                actual_url = "https://" + _strip_tags(url_span.group(1)).strip().lstrip("/")
            else:
                continue

        # Validate extracted URL
        if _validate_url(actual_url):
            continue

        # Snippet
        snip_match = re.search(
            r'class="result__snippet"[^>]*>(.*?)</(?:a|span|div)>',
            block,
            re.DOTALL | re.IGNORECASE,
        )
        snippet = _strip_tags(snip_match.group(1)).strip() if snip_match else ""

        results.append({
            "title": title,
            "url": actual_url,
            "domain": _get_domain(actual_url),
            "snippet": snippet,
        })

    return results


def _brave_search(query: str, num_results: int = 6, recency: str | None = None) -> list[dict]:
    """
    Search via Brave Search API (requires AGENT_API_BRAVE_SEARCH_KEY).

    Returns same dict schema as _ddg_search.
    """
    key = os.environ.get("AGENT_API_BRAVE_SEARCH_KEY", "")
    params: dict[str, str | int] = {"q": query, "count": min(num_results, 20)}
    if recency:
        # Brave freshness: pd (past day), pw (past week), pm (past month), py (past year)
        _map = {"d": "pd", "w": "pw", "m": "pm", "y": "py"}
        params["freshness"] = _map.get(recency, "")

    url = _BRAVE_SEARCH_URL + "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v})
    try:
        raw = _make_request(
            url,
            extra_headers={"Accept": "application/json",
                           "Accept-Encoding": "gzip",
                           "X-Subscription-Token": key},
            timeout=_SEARCH_TIMEOUT,
        )
    except Exception as exc:
        return [{"error": f"Brave Search failed: {exc}"}]

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return [{"error": "Brave Search returned non-JSON response"}]

    results: list[dict] = []
    for item in data.get("web", {}).get("results", [])[:num_results]:
        url_val = item.get("url", "")
        if _validate_url(url_val):
            continue
        results.append({
            "title": item.get("title", ""),
            "url": url_val,
            "domain": _get_domain(url_val),
            "snippet": item.get("description", ""),
            "age": item.get("age", ""),
        })
    return results


def _search(query: str, num_results: int = 6, recency: str | None = None) -> list[dict]:
    """Route to Brave Search if key configured, else DuckDuckGo."""
    if os.environ.get("AGENT_API_BRAVE_SEARCH_KEY"):
        return _brave_search(query, num_results, recency)
    return _ddg_search(query, num_results, recency)


def _fetch_url_text(url: str, max_chars: int = _MAX_FETCH_CHARS) -> str:
    """Fetch a URL and return clean markdown text. Returns error string on failure."""
    err = _validate_url(url)
    if err:
        return f"ERROR: {err}"
    try:
        html = _make_request(url, timeout=_FETCH_TIMEOUT)
    except urllib.error.HTTPError as exc:
        return f"ERROR: HTTP {exc.code} {exc.reason}"
    except urllib.error.URLError as exc:
        return f"ERROR: {exc.reason}"
    except TimeoutError:
        return "ERROR: Request timed out"
    except Exception as exc:
        return f"ERROR: {exc}"

    text = _html_to_markdown(html, base_url=url)
    if len(text) > max_chars:
        text = text[:max_chars] + f"\n\n[… content truncated at {max_chars:,} chars]"
    return text


# ── Public tools ───────────────────────────────────────────────────────────────

@tool
def web_search(
    query: Annotated[str, "Search query"],
    num_results: Annotated[int, "Number of results to return (1–10)"] = 6,
    recency: Annotated[
        str | None,
        "Filter by recency: 'd' (last day), 'w' (last week), 'm' (last month), 'y' (last year)",
    ] = None,
) -> str:
    """
    Search the web and return ranked results with title, URL, domain, and snippet.

    Uses Brave Search API when AGENT_API_BRAVE_SEARCH_KEY is set; falls back to
    DuckDuckGo HTML search (no API key required).

    Returns a structured list of search results. To read the full content of any
    result, pass its URL to fetch_page.
    """
    num_results = max(1, min(num_results, _MAX_SEARCH_RESULTS))
    results = _search(query, num_results=num_results, recency=recency)

    if not results:
        return f"No results found for: {query!r}"
    if len(results) == 1 and "error" in results[0]:
        return f"Search error: {results[0]['error']}"

    lines = [f"## Web Search: {query!r}", f"*{len(results)} results*\n"]
    for i, r in enumerate(results, 1):
        if "error" in r:
            lines.append(f"{i}. [Error: {r['error']}]")
            continue
        lines.append(f"### {i}. [{r['title']}]({r['url']})")
        lines.append(f"**Domain:** {r['domain']}")
        if r.get("snippet"):
            lines.append(f"**Summary:** {r['snippet']}")
        if r.get("age"):
            lines.append(f"**Published:** {r['age']}")
        lines.append("")

    return "\n".join(lines)


@tool
def fetch_page(
    url: Annotated[str, "URL to fetch"],
    max_chars: Annotated[int, "Maximum characters of content to return (default 8000, max 20000)"] = 8_000,
    include_links: Annotated[bool, "Include hyperlinks in the output"] = False,
) -> str:
    """
    Fetch a web page and return its content as clean, readable markdown.

    Strips navigation, ads, scripts, and boilerplate. Preserves headings,
    paragraphs, code blocks, lists, and (optionally) links. Suitable for
    reading documentation, articles, blog posts, and API reference pages.
    """
    err = _validate_url(url)
    if err:
        return f"ERROR: {err}"

    max_chars = max(500, min(max_chars, 20_000))

    try:
        html = _make_request(url, timeout=_FETCH_TIMEOUT)
    except urllib.error.HTTPError as exc:
        return f"ERROR: HTTP {exc.code} — {exc.reason} ({url})"
    except urllib.error.URLError as exc:
        return f"ERROR: Network error — {exc.reason} ({url})"
    except TimeoutError:
        return f"ERROR: Timed out fetching {url}"
    except Exception as exc:
        return f"ERROR: {exc}"

    # Strip links from the converted output when not requested (cleaner for reading)
    raw_html = html
    if not include_links:
        raw_html = re.sub(
            r'<a[^>]+href=["\'][^"\']*["\'][^>]*>(.*?)</a>',
            r"\1",
            html,
            flags=re.DOTALL | re.IGNORECASE,
        )

    text = _html_to_markdown(raw_html, base_url=url)

    if not text.strip():
        return f"ERROR: No readable content found at {url}"

    # Add source header
    domain = _get_domain(url)
    header = f"**Source:** [{domain}]({url})\n\n"
    content = header + text

    if len(content) > max_chars:
        content = content[:max_chars] + f"\n\n[… truncated — {max_chars:,} / {len(text):,} chars total]"

    return content


@tool
def extract_links(
    url: Annotated[str, "URL to extract links from"],
    filter_domain: Annotated[str | None, "Only return links from this domain (e.g. 'docs.python.org')"] = None,
    limit: Annotated[int, "Maximum number of links to return"] = 30,
) -> str:
    """
    Extract all hyperlinks from a web page, with optional domain filtering.

    Returns a deduplicated list of (anchor text, URL) pairs. Useful for
    discovering related pages, documentation sections, or follow-up sources.
    """
    err = _validate_url(url)
    if err:
        return f"ERROR: {err}"

    try:
        html = _make_request(url, timeout=_FETCH_TIMEOUT)
    except Exception as exc:
        return f"ERROR: {exc}"

    # Remove noise so we don't pick up nav / footer links unless intentional
    html_clean = _remove_noise(html)

    # Extract all <a href> pairs
    raw_links = re.findall(
        r'<a[^>]+href=["\']([^"\'#][^"\']*)["\'][^>]*>(.*?)</a>',
        html_clean,
        re.DOTALL | re.IGNORECASE,
    )

    seen: set[str] = set()
    results: list[tuple[str, str]] = []
    base_parsed = urllib.parse.urlparse(url)

    for href, anchor in raw_links:
        href = href.strip()
        # Resolve relative URLs
        if href.startswith("//"):
            href = base_parsed.scheme + ":" + href
        elif href.startswith("/"):
            href = f"{base_parsed.scheme}://{base_parsed.netloc}{href}"
        elif not href.startswith("http"):
            continue  # skip mailto:, javascript:, etc.

        if _validate_url(href):
            continue

        if filter_domain and filter_domain.lower() not in _get_domain(href):
            continue

        href_norm = href.split("?")[0].rstrip("/")  # deduplicate ignoring query/fragment
        if href_norm in seen:
            continue
        seen.add(href_norm)

        text = _strip_tags(anchor).strip()[:120]
        results.append((text or "—", href))

        if len(results) >= limit:
            break

    if not results:
        return f"No links found at {url}" + (f" (filter: {filter_domain})" if filter_domain else "")

    lines = [f"## Links on {_get_domain(url)}", f"*{len(results)} unique links*\n"]
    for text, href in results:
        lines.append(f"- [{text}]({href})")
    return "\n".join(lines)


@tool
def get_page_metadata(
    url: Annotated[str, "URL to inspect"],
) -> str:
    """
    Return metadata from a web page without downloading its full content.

    Extracts: page title, meta description, Open Graph tags (og:title, og:description,
    og:image, og:type), canonical URL, publication/modification date, and HTTP headers
    (Content-Type, Last-Modified, X-Robots-Tag).

    Use this to quickly assess a page before deciding whether to fetch_page it.
    """
    err = _validate_url(url)
    if err:
        return f"ERROR: {err}"

    try:
        html = _make_request(url, timeout=_FETCH_TIMEOUT)
    except Exception as exc:
        return f"ERROR: {exc}"

    meta: dict[str, str] = {"url": url, "domain": _get_domain(url)}

    # <title>
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.DOTALL | re.IGNORECASE)
    if m:
        meta["title"] = _strip_tags(m.group(1)).strip()

    # Standard meta tags
    for name, key in (
        ("description", "description"),
        ("keywords", "keywords"),
        ("author", "author"),
        ("robots", "robots"),
        ("article:published_time", "published"),
        ("article:modified_time", "modified"),
        ("date", "date"),
    ):
        m = re.search(
            rf'<meta[^>]+(?:name|property)=["\'](?:article:)?{re.escape(name)}["\'][^>]+content=["\']([^"\']*)["\']',
            html,
            re.IGNORECASE,
        )
        if not m:
            m = re.search(
                rf'<meta[^>]+content=["\']([^"\']*)["\'][^>]+(?:name|property)=["\'](?:article:)?{re.escape(name)}["\']',
                html,
                re.IGNORECASE,
            )
        if m:
            meta[key] = m.group(1).strip()

    # Open Graph tags
    og_tags = re.findall(
        r'<meta[^>]+property=["\']og:([^"\']+)["\'][^>]+content=["\']([^"\']*)["\']',
        html,
        re.IGNORECASE,
    )
    for og_key, og_val in og_tags:
        meta[f"og:{og_key.strip()}"] = og_val.strip()

    # Canonical URL
    m = re.search(r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)["\']', html, re.IGNORECASE)
    if m:
        meta["canonical"] = m.group(1).strip()

    # JSON-LD for publication date and schema type
    ld_matches = re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
                            html, re.DOTALL | re.IGNORECASE)
    for ld_raw in ld_matches[:2]:
        try:
            ld = json.loads(ld_raw.strip())
            for key_path in (("datePublished",), ("dateCreated",), ("dateModified",)):
                val = ld.get(key_path[0])
                if val and "published" not in meta:
                    meta["published"] = str(val)
            if "@type" in ld and "schema_type" not in meta:
                meta["schema_type"] = str(ld["@type"])
        except (json.JSONDecodeError, AttributeError):
            pass

    lines = [f"## Page Metadata: {meta.get('title', url)}", ""]
    field_order = [
        "url", "domain", "canonical", "title", "description",
        "published", "modified", "date", "author", "keywords",
        "robots", "schema_type",
        "og:title", "og:description", "og:image", "og:type", "og:site_name",
    ]
    shown: set[str] = set()
    for field in field_order:
        if field in meta:
            lines.append(f"**{field}:** {meta[field]}")
            shown.add(field)
    for field, val in meta.items():
        if field not in shown:
            lines.append(f"**{field}:** {val}")

    return "\n".join(lines)


@tool
def research_topic(
    query: Annotated[str, "Research question or topic to investigate"],
    max_sources: Annotated[int, "Number of web sources to fetch content from (1–6)"] = 4,
    focus: Annotated[str | None, "Optional sub-topic or angle to narrow the research"] = None,
    recency: Annotated[
        str | None,
        "Limit to recent content: 'd' (day), 'w' (week), 'm' (month), 'y' (year)",
    ] = None,
) -> str:
    """
    Conduct multi-source web research on a topic.

    Searches the web, fetches content from the top sources, and returns a
    structured research brief containing:
    - Search result summary with ranked sources
    - Full extracted content from each source
    - Source attribution for every piece of information

    This is the primary deep-research tool. Use it when a question requires
    synthesising information from multiple web sources. After receiving the brief,
    synthesise the findings into a response with inline citations [1], [2], etc.
    """
    max_sources = max(1, min(max_sources, 6))
    search_query = f"{query} {focus}".strip() if focus else query

    # ── Step 1: Search ──────────────────────────────────────────────────────────
    raw_results = _search(search_query, num_results=max_sources + 3, recency=recency)
    if not raw_results:
        return f"No results found for: {query!r}"
    if len(raw_results) == 1 and "error" in raw_results[0]:
        return f"Search failed: {raw_results[0]['error']}"

    valid_results = [r for r in raw_results if "error" not in r]
    sources_to_fetch = valid_results[:max_sources]

    # ── Step 2: Build brief header ──────────────────────────────────────────────
    ts = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
    parts: list[str] = [
        f"# Research Brief: {query}",
        f"*Query: `{search_query}` · {len(valid_results)} search results · "
        f"fetching {len(sources_to_fetch)} sources · {ts}*",
        "",
        "## Search Results Overview",
    ]
    for i, r in enumerate(valid_results, 1):
        marker = " ← fetching" if i <= len(sources_to_fetch) else ""
        parts.append(f"{i}. **[{r['title']}]({r['url']})** — {r['domain']}{marker}")
        if r.get("snippet"):
            parts.append(f"   > {r['snippet']}")
    parts.append("")

    # ── Step 3: Fetch each source ───────────────────────────────────────────────
    parts.append("## Source Content")
    fetched = 0
    for i, r in enumerate(sources_to_fetch, 1):
        parts.append(f"\n### [{i}] {r['title']}")
        parts.append(f"**URL:** {r['url']}  \n**Domain:** {r['domain']}\n")

        content = _fetch_url_text(r["url"], max_chars=4_000)
        if content.startswith("ERROR"):
            parts.append(f"*⚠ Could not fetch content: {content}*")
            if r.get("snippet"):
                parts.append(f"\n**Search preview:** {r['snippet']}")
        else:
            parts.append(content)
            fetched += 1

    # ── Step 4: Citation index ──────────────────────────────────────────────────
    parts.append("\n---")
    parts.append(f"## Source Index ({fetched}/{len(sources_to_fetch)} sources fetched)\n")
    for i, r in enumerate(sources_to_fetch, 1):
        parts.append(f"[{i}] [{r['title']}]({r['url']}) — {r['domain']}")

    parts.append(
        "\n*Use inline citation numbers [1], [2], etc. when referencing specific claims.*"
    )

    return "\n".join(parts)
