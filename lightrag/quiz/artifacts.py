"""Detection and redaction helpers for graph-structural noise in the quiz pipeline.

Two responsibilities:

1. ``is_artifact_id`` — recognises multimodal-anchor synthetic entity IDs
   (``tb-…`` for tables, ``im-…`` for images / drawings, ``mm-…`` for
   other multimodal anchors). The KG extractor creates these as structural
   anchors, not pedagogical concepts. The quiz pipeline must not seed off
   them or expose them to the generator as concepts.

2. ``redact_instance_labels`` — replaces instance-specific labels lifted
   from diagrams (``Thread 1``, ``P1``, ``core 3``, ``CPU_7``, …) with
   concept placeholders (``{thread}``, ``{process}``, ``{cpu_core}``, …).
   This prevents the generator from latching onto the literal label
   ("What is the label of Thread A?") and forces it to formulate questions
   about the underlying concept instead.

Used by ``seeds.py``, ``retrieval.py``, and the pedagogical context
formatter in ``RetrievalContext.format_for_prompt``.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Artifact-ID detection
# ---------------------------------------------------------------------------

# tb-<32 hex>-<4 digit slot>  /  im-<32 hex>-<4 digit slot>  /  mm-<32 hex>-<4 digit slot>
_ARTIFACT_ID_RE = re.compile(r"^(tb|im|mm)-[0-9a-f]{32}-\d{4}$")


def is_artifact_id(name: str) -> bool:
    """Return True if ``name`` looks like a multimodal-anchor synthetic entity ID."""
    return bool(_ARTIFACT_ID_RE.match(name or ""))


# ---------------------------------------------------------------------------
# Instance-label redaction
# ---------------------------------------------------------------------------

# Order matters: more specific patterns first. The replacement placeholder is
# wrapped in braces so it reads as a typed slot rather than prose. Each
# pattern accepts the space-separated form (``Thread 1``) AND the underscore-
# separated form (``Thread_1``, ``P_0``) — quiz-caaf0e4a leaked ``P_0`` into
# a question because the original ``\bP\d+\b`` pattern broke on underscores.
_INSTANCE_LABEL_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Threads: "Thread 1", "Thread A", "Thread_1", "Thread_A"
    (re.compile(r"\bThread[\s_][A-Z0-9]\b"), "{thread}"),
    # Processes: "P0", "P_0", "P1", "P_1" … and "process_1", "process 1"
    (re.compile(r"\bP_?\d+\b"), "{process}"),
    (re.compile(r"\bprocess[\s_]\d+\b", re.IGNORECASE), "{process}"),
    # CPU cores: "core 0", "core_3", "Core 3", "CPU_7", "CPU 7"
    (re.compile(r"\bcore[\s_]\d+\b", re.IGNORECASE), "{cpu_core}"),
    (re.compile(r"\bCPU[\s_]\d+\b"), "{cpu_core}"),
    # Memory pages / frames: also "Page_3", "Frame_7"
    (re.compile(r"\bPage[\s_]\d+\b"), "{memory_page}"),
    (re.compile(r"\bFrame[\s_]\d+\b"), "{memory_frame}"),
    # Named semaphores: "Semaphore X", "Semaphore_Y"
    (re.compile(r"\bSemaphore[\s_][A-Z]\b"), "{semaphore}"),
    # Last-resort short instance tokens: "T1", "T_0", "S2", "S_3"
    (re.compile(r"\b[TS]_?\d\b"), "{thread}"),
]


def redact_instance_labels(text: str) -> str:
    """Replace instance-specific diagram labels with concept placeholders.

    The generator cannot ask "What is the label of {thread}?" — there is
    no label to look up, only the underlying concept the label stood for.

    Examples
    --------
    >>> redact_instance_labels("Thread 1 signals Semaphore Y")
    '{thread} signals {semaphore}'
    >>> redact_instance_labels("P1 has arrival time 0 in core 3")
    '{process} has arrival time 0 in {cpu_core}'
    """
    if not text:
        return text
    for pat, repl in _INSTANCE_LABEL_PATTERNS:
        text = pat.sub(repl, text)
    return text


# ---------------------------------------------------------------------------
# Concept-name normalization (target-concept rendering)
# ---------------------------------------------------------------------------

# When the prompt names a target concept (e.g. ``Target concept: Thread 3``),
# we don't want to ship the raw instance label — it tells the LLM to focus
# on a specific labelled instance, which then leaks into the question. We
# also can't ship a ``{thread}`` placeholder because R3+R4 fought hard to
# stop the LLM from echoing braces back. So we normalize: redact, then
# strip the braces, then natural-prose the slot name.
_SLOT_RE = re.compile(r"\{(\w+)\}")


def normalize_concept_name(name: str) -> str:
    """Convert an entity name containing instance labels to its concept form.

    Examples
    --------
    >>> normalize_concept_name("Thread 3")
    'thread'
    >>> normalize_concept_name("P_0")
    'process'
    >>> normalize_concept_name("CPU_2")
    'cpu core'
    >>> normalize_concept_name("Bounded-Buffer Problem")
    'Bounded-Buffer Problem'
    >>> normalize_concept_name("Thread 3 management")
    'thread management'
    """
    if not name:
        return name
    redacted = redact_instance_labels(name)
    if redacted == name:
        return name
    # Replace any {slot} runs left over by redaction with their natural-prose form
    return _SLOT_RE.sub(lambda m: m.group(1).replace("_", " "), redacted)


# ---------------------------------------------------------------------------
# Figure-label entity detection
# ---------------------------------------------------------------------------

# Entity names that describe figures/diagrams rather than concepts. These leak
# into the seed pool because the KG extractor creates a node for every named
# figure caption. They make terrible seeds — "Operating System Structure
# Diagram" anchors no concept, so the LLM drifts to whatever generic OS
# question it pleases.
_FIGURE_LABEL_RE = re.compile(
    r"(?:^|[\s_-])"
    r"(diagram|figure|chart|illustration|visualization|schematic|overview)"
    r"(?:[\s_-]|$)",
    re.IGNORECASE,
)


def is_figure_label_entity(name: str) -> bool:
    """True if ``name`` looks like a label for a figure/diagram, not a concept.

    Caught:
      - ``Multilevel Queue Scheduling Diagram``
      - ``process_scheduling_overview_diagram``
      - ``Logical Address Space Segmentation Diagram``

    Not caught (legitimate concepts):
      - ``Bounded-Buffer Problem``
      - ``Memory-Management Unit``
      - ``Page Faults``
    """
    return bool(_FIGURE_LABEL_RE.search(name or ""))


__all__ = [
    "is_artifact_id",
    "redact_instance_labels",
    "normalize_concept_name",
    "is_figure_label_entity",
]
