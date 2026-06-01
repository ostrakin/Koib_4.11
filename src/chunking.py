# -*- coding: utf-8 -*-
"""
Smart chunking for KOIB RAG.

v4.11 fixes made for OCR/DOCX/CSV artifacts:
- service prefixes such as ``passage:`` are stripped before storage/display;
- false ``formula`` fragments produced by OCR/PDF extraction are reclassified;
- text is flushed on source/page/heading changes, improving citations;
- figure/table/formula chunk ids include artifact-specific metadata to avoid collisions.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

try:
    from langchain_core.documents import Document
except Exception:  # lightweight fallback for tests / minimal environments
    class Document:
        def __init__(self, page_content: str, metadata: dict | None = None):
            self.page_content = page_content
            self.metadata = metadata or {}

from .parsing import DocumentElement
from .utils import clean_text, estimate_tokens, normalize_ocr_text, strip_embedding_prefix, text_hash
from config import TEXT_CHUNK_SIZE, TEXT_CHUNK_OVERLAP, MIN_CHUNK_LENGTH

logger = logging.getLogger("koib.chunking")

_MATH_STRICT_RE = re.compile(
    r"(" 
    r"\b[A-Za-zА-Яа-я]\s*[=+*/^]\s*[-+]?\d"  # N = 3, x+2
    r"|\d+(?:[.,]\d+)?\s*[=+*/^]\s*[-+]?\d"  # 20 + 3
    r"|\b\d+\s*%\b"
    r"|[∑∫√∞≈≠≤≥±αβγδεζηθλμπρσφψω]"
    r")",
    re.IGNORECASE,
)
_LATEX_RE = re.compile(r"(\\[a-zA-Z]+|\$[^$]+\$|\$\$.+?\$\$)", re.DOTALL)
_CAPTION_RE = re.compile(r"^\s*(рисунок|рис\.|схема|таблица)\s+\S+", re.IGNORECASE)
_NOISE_RE = re.compile(r"^[\W_\d\s.-]{1,20}$", re.UNICODE)


def sanitize_chunk_content(text: str) -> str:
    """Normalize chunk text without changing domain wording."""
    return normalize_ocr_text(strip_embedding_prefix(text or ""))


def is_noise_text(text: str, min_alpha: int = 3) -> bool:
    """Return True for OCR fragments that should not become standalone chunks."""
    if not text:
        return True
    stripped = sanitize_chunk_content(text)
    if not stripped:
        return True
    if _NOISE_RE.match(stripped):
        return True
    alpha = sum(ch.isalpha() for ch in stripped)
    if alpha < min_alpha and not _MATH_STRICT_RE.search(stripped):
        return True
    # Typical PDF line-wrap garbage: one short hyphenated syllable such as "изме-".
    if len(stripped) <= 8 and stripped.endswith("-") and alpha <= 6:
        return True
    return False


def is_true_formula_text(text: str, formula_type: str = "") -> bool:
    """Strict formula detector. Avoids classifying normal phrases with '-' or '/' as formulas."""
    t = sanitize_chunk_content(text)
    if not t or is_noise_text(t, min_alpha=0):
        return False
    if formula_type in {"latex_inline", "latex_block"}:
        return True
    if _LATEX_RE.search(t):
        return True
    if _CAPTION_RE.match(t):
        return False
    if len(t) > 260 and not _MATH_STRICT_RE.search(t):
        return False
    return bool(_MATH_STRICT_RE.search(t))


def normalized_element_type(element_type: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> str:
    """Repair element type produced by old OCR/PDF parsing."""
    metadata = metadata or {}
    etype = (element_type or "text").lower().strip()
    text = sanitize_chunk_content(content)
    if etype == "formula" and not is_true_formula_text(text, str(metadata.get("formula_type", ""))):
        if _CAPTION_RE.match(text) and text.lower().startswith(("рис", "рисунок", "схема")):
            return "figure"
        return "text"
    if etype not in {"text", "table", "formula", "figure", "heading"}:
        return "text"
    return etype


@dataclass
class Chunk:
    """Document chunk ready for indexing."""

    chunk_id: str
    content: str
    full_content: Optional[str] = None
    chunk_type: str = "text"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.content = sanitize_chunk_content(self.content)
        if self.full_content is not None:
            self.full_content = sanitize_chunk_content(self.full_content)
        self.chunk_type = normalized_element_type(self.chunk_type, self.full_content or self.content, self.metadata)

    def to_langchain_doc(self) -> Document:
        """Convert to LangChain Document for vector indexing. The content is never prefixed here."""
        return Document(
            page_content=self.content,
            metadata={
                "chunk_id": self.chunk_id,
                "chunk_type": self.chunk_type,
                **self.metadata,
            },
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "content": self.content,
            "full_content": self.full_content,
            "chunk_type": self.chunk_type,
            "metadata": self.metadata,
        }

    @property
    def source(self) -> str:
        return str(self.metadata.get("source", ""))

    @property
    def page(self) -> int:
        try:
            return int(self.metadata.get("page", 0))
        except Exception:
            return 0

    @property
    def heading(self) -> str:
        return str(self.metadata.get("heading", ""))

    @property
    def model(self) -> str:
        return str(self.metadata.get("model", "unknown"))


def _split_text_semantic(
    text: str,
    max_tokens: int = TEXT_CHUNK_SIZE,
    overlap_tokens: int = TEXT_CHUNK_OVERLAP,
) -> List[str]:
    """Split text into paragraph-aware chunks."""
    text = sanitize_chunk_content(text)
    if not text or len(text.strip()) < MIN_CHUNK_LENGTH:
        return []

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if len(paragraphs) <= 1 and "\n" in text:
        paragraphs = [p.strip() for p in text.splitlines() if p.strip()]
    if not paragraphs:
        paragraphs = [text.strip()]

    chunks: List[str] = []
    current_parts: List[str] = []
    current_tokens = 0

    for para in paragraphs:
        if is_noise_text(para):
            continue
        para_tokens = estimate_tokens(para)
        if current_tokens + para_tokens > max_tokens and current_parts:
            chunks.append("\n\n".join(current_parts))

            overlap_parts: List[str] = []
            overlap_tok = 0
            for p in reversed(current_parts):
                pt = estimate_tokens(p)
                if overlap_tok + pt > overlap_tokens:
                    break
                overlap_parts.insert(0, p)
                overlap_tok += pt

            current_parts = overlap_parts
            current_tokens = overlap_tok

        current_parts.append(para)
        current_tokens += para_tokens

    if current_parts:
        chunk_text = "\n\n".join(current_parts)
        if estimate_tokens(chunk_text) >= MIN_CHUNK_LENGTH // 4:
            chunks.append(chunk_text)

    return chunks


def _markdown_cells(line: str) -> List[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _generate_table_summary(table_markdown: str, metadata: Dict) -> str:
    """Heuristic table summary for vector search."""
    table_markdown = sanitize_chunk_content(table_markdown)
    lines = [l for l in table_markdown.split("\n") if l.strip()]
    header_line = lines[0] if lines else ""
    num_rows = int(metadata.get("num_rows", 0) or max(0, len(lines) - 2))
    num_cols = int(metadata.get("num_cols", 0) or (len(_markdown_cells(header_line)) if header_line else 0))

    headers = [h for h in _markdown_cells(header_line) if h and h != "---"]
    summary_parts = [f"Таблица ({num_rows} строк, {num_cols} столбцов)."]
    if headers:
        summary_parts.append(f"Столбцы: {', '.join(headers[:10])}.")

    data_lines = [l for l in lines[2:] if l.strip() and "---" not in l][:3]
    if data_lines:
        summary_parts.append("Пример данных:")
        for dl in data_lines:
            cells = [c for c in _markdown_cells(dl) if c]
            if cells:
                summary_parts.append("  " + " | ".join(cells[:6]))

    if len(summary_parts) == 1 and table_markdown:
        summary_parts.append(table_markdown[:300])
    return sanitize_chunk_content(" ".join(summary_parts))


def _generate_formula_summary(formula_content: str, metadata: Dict) -> str:
    """Heuristic formula summary for indexing."""
    formula_content = sanitize_chunk_content(formula_content)
    formula_type = str(metadata.get("formula_type", "unknown"))
    type_desc = {
        "latex_inline": "Формула (LaTeX, строковая)",
        "latex_block": "Формула (LaTeX, блочная)",
        "suspected_formula": "Формула",
        "unknown": "Формула",
    }.get(formula_type, "Формула")
    return f"{type_desc}: {formula_content[:240]}"


class SmartChunker:
    """Chunk text and structured document elements."""

    def __init__(
        self,
        chunk_size: int = TEXT_CHUNK_SIZE,
        chunk_overlap: int = TEXT_CHUNK_OVERLAP,
        min_chunk_length: int = MIN_CHUNK_LENGTH,
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_length = min_chunk_length

    def chunk_elements(self, elements: List[DocumentElement]) -> List[Chunk]:
        chunks: List[Chunk] = []
        text_buffer: List[DocumentElement] = []
        current_heading = ""
        last_scope: tuple[str, int, str] | None = None

        def flush() -> None:
            nonlocal text_buffer
            if text_buffer:
                chunks.extend(self._chunk_text_buffer(text_buffer, current_heading))
                text_buffer = []

        for element in elements:
            element.content = sanitize_chunk_content(element.content)
            if is_noise_text(element.content) and element.element_type != "table":
                continue

            if element.element_type == "heading":
                flush()
                current_heading = element.content or element.heading or current_heading
                last_scope = None
                continue

            effective_type = normalized_element_type(element.element_type, element.content, element.metadata)
            element.element_type = effective_type
            if element.heading:
                current_heading = element.heading

            scope = (element.source, int(element.page or 0), current_heading or element.heading or "")
            if effective_type in {"table", "formula", "figure"}:
                flush()
                structured = self._chunk_structured_element(element, current_heading)
                if structured.content and not is_noise_text(structured.content, min_alpha=0):
                    chunks.append(structured)
                last_scope = None
            else:
                if last_scope is not None and scope != last_scope:
                    flush()
                text_buffer.append(element)
                last_scope = scope

        flush()
        logger.info("Создано %s чанков из %s элементов", len(chunks), len(elements))
        return chunks

    def _chunk_text_buffer(self, elements: List[DocumentElement], heading: str) -> List[Chunk]:
        combined = "\n\n".join(sanitize_chunk_content(e.content) for e in elements if e.content.strip())
        if not combined or len(combined.strip()) < self.min_chunk_length:
            return []

        text_chunks = _split_text_semantic(combined, max_tokens=self.chunk_size, overlap_tokens=self.chunk_overlap)
        chunks: List[Chunk] = []
        source = elements[0].source if elements else ""
        pages = [int(e.page or 0) for e in elements if int(e.page or 0) > 0]
        page = min(pages) if pages else (elements[0].page if elements else 0)
        page_end = max(pages) if pages else page
        model = elements[0].model if elements else "unknown"
        heading_value = heading or elements[0].heading if elements else heading

        for i, text in enumerate(text_chunks):
            text = sanitize_chunk_content(text)
            if len(text) < self.min_chunk_length or is_noise_text(text):
                continue
            chunk_id = f"txt_{text_hash(f'{source}:{page}:{page_end}:{i}:{text[:800]}')}"
            metadata = {
                "source": source,
                "page": page,
                "heading": heading_value,
                "model": model,
                "chunk_index": i,
            }
            if page_end and page_end != page:
                metadata["page_end"] = page_end
            chunks.append(Chunk(chunk_id=chunk_id, content=text, chunk_type="text", metadata=metadata))
        return chunks

    def _chunk_structured_element(self, element: DocumentElement, heading: str) -> Chunk:
        element.content = sanitize_chunk_content(element.content)
        effective_type = normalized_element_type(element.element_type, element.content, element.metadata)
        if effective_type == "table":
            summary = _generate_table_summary(element.content, element.metadata)
            full_content: Optional[str] = element.content
        elif effective_type == "formula":
            summary = _generate_formula_summary(element.content, element.metadata)
            full_content = element.content
        elif effective_type == "figure":
            summary = element.content
            full_content = element.content
        else:
            summary = element.content
            full_content = None

        id_material = "|".join(
            [
                str(element.source),
                str(element.page),
                str(effective_type),
                str(element.element_id),
                str(element.metadata.get("image_path", "")),
                str(element.metadata.get("table_index", "")),
                str(element.metadata.get("figure_index", "")),
                element.content[:800],
            ]
        )
        chunk_id = f"{effective_type}_{text_hash(id_material)}"
        return Chunk(
            chunk_id=chunk_id,
            content=summary,
            full_content=full_content,
            chunk_type=effective_type,
            metadata={
                "source": element.source,
                "page": element.page,
                "heading": heading or element.heading,
                "model": element.model,
                "element_id": element.element_id,
                **element.metadata,
            },
        )
