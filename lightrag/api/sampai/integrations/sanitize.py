"""HTML sanitization for user-authored rich text.

The original SAMpai stored TipTap HTML **raw** and rendered it with
``dangerouslySetInnerHTML`` — a stored-XSS hole. Here every announcement body is
run through nh3 (Rust ammonia) on write, so only a small, safe tag/attribute
allowlist survives and links are forced to safe schemes with hardened ``rel``.

Allowed (matches the editor's toolbar): paragraphs/breaks, bold, italic,
underline, strikethrough, bullet/ordered lists, and links. Headings, code,
blockquote, images, scripts, styles and inline event handlers are all stripped.
"""

from __future__ import annotations

import nh3

# Editor toolbar = bold / italic / underline / lists / links only.
_ALLOWED_TAGS: set[str] = {"p", "br", "strong", "b", "em", "i", "u", "s", "ul", "ol", "li", "a"}
_ALLOWED_ATTRS: dict[str, set[str]] = {"a": {"href", "title"}}
_URL_SCHEMES: set[str] = {"http", "https", "mailto"}


def clean_announcement_html(raw: str) -> str:
    """Return a sanitized copy of `raw` safe to store and render as HTML."""
    return nh3.clean(
        raw or "",
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRS,
        url_schemes=_URL_SCHEMES,
        link_rel="noopener noreferrer nofollow",  # links open isolated from us
        strip_comments=True,
    )


def is_effectively_empty(html: str) -> bool:
    """True if `html` has no visible text once tags + whitespace/nbsp are removed."""
    text = nh3.clean(html or "", tags=set())  # drop all tags, keep text nodes
    return not text.replace(" ", " ").replace("&nbsp;", " ").strip()
