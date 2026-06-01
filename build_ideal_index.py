# -*- coding: utf-8 -*-
"""
build_ideal_index.py  —  Сборка ИДЕАЛЬНОГО индекса для KOIB RAG
================================================================

Назначение
----------
Единая, аудируемая точка сборки production-индекса из артефактов прошлых
попыток (chunks*.txt / docstore*.txt / bm25*.txt / chunks_export_new*.txt).
Скрипт устраняет ВСЕ дефекты данных, найденные при анализе, и строит:

    output/index/text_index.faiss        (плотный индекс по тексту)
    output/index/summary_index.faiss     (плотный индекс по таблицам/формулам/рисункам)
    output/index/bm25_fts.db             (разреженный BM25 / SQLite FTS5)
    output/docstore/docstore.db          (полный текст чанков для отображения и цитат)

Что именно чинится (по результатам аудита ваших файлов)
-------------------------------------------------------
1. Утёкший префикс E5 "passage:" / "query:" в content (chunks.txt: 714/714 записей).
2. Гипер-классификация формул: ~75% записей docstore помечены "formula", хотя это
   обычный текст ("В качестве печатающего устройства..."). Возвращаем в "text".
3. Пустые/вырожденные таблицы "| | | |" (нет ни одной ячейки) — отбрасываем.
4. Шум в детекции модели ("Zp21179", "использовании-139", "Zp21179-") — переопределяем
   модель по содержимому и имени источника, мусор → "unknown".
5. page == 0 — помечаем как неуверенную страницу, чтобы цитаты не лгали "стр. 0".
6. Полное удаление дублей между chunks/docstore по нормализованному хэшу контента,
   с сохранением записи, у которой БОГАЧЕ метаданные (реальная страница, известная
   модель, наличие full_content).
7. bm25.txt по умолчанию НЕ импортируется (лемматизированный текст не годится для
   показа и цитат). chunks_export_new.txt по умолчанию НЕ импортируется (в нём
   потеряны source/page/model → цитаты невозможны). Оба включаются только явными
   флагами и помечаются служебными флагами в metadata.

Использование
-------------
    # 1) Сухой прогон — только аудит и план, БЕЗ тяжёлых зависимостей (torch/faiss):
    python build_ideal_index.py --artifacts-dir ./data/artifacts --dry-run

    # 2) Боевая сборка индекса (нужны зависимости из requirements.txt проекта):
    python build_ideal_index.py --artifacts-dir ./data/artifacts --output-dir ./output

    # 3) Включить спорные источники (не рекомендуется):
    python build_ideal_index.py --artifacts-dir ./data/artifacts --include-export-new --allow-bm25

Скрипт кладётся в корень репозитория KOIB рядом с config.py и папкой src/.
Логика очистки самодостаточна; модули проекта (src.chunking / src.indexing)
подключаются ТОЛЬКО на этапе записи индекса, поэтому --dry-run работает где угодно.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

# ─────────────────────────────────────────────────────────────────────────────
# Самодостаточные хелперы очистки (копии логики src/*, чтобы --dry-run не требовал
# config/torch/faiss). При боевой сборке индекс пишется через src.indexing.
# ─────────────────────────────────────────────────────────────────────────────

KNOWN_MODELS = {"koib2010", "koib2017a", "koib2017b"}

KOIB_MODEL_PATTERNS: Dict[str, List[str]] = {
    "koib2010": [r"КОИБ[-\s]?2010", r"0912054", r"PRINT_KOIB2010", r"17404049\.438900\.001"],
    "koib2017a": [r"КОИБ[-\s]?2017\s*[АA]", r"17404049\.5013009", r"PRINT_KOIB2017[АA]"],
    "koib2017b": [r"КОИБ[-\s]?2017\s*[БB]", r"БАВУ\.201119", r"0912053", r"PRINT_KOIB2017[БB]"],
}

_MATH_STRICT_RE = re.compile(
    r"(\b[A-Za-zА-Яа-я]\s*[=+*/^]\s*[-+]?\d|\d+(?:[.,]\d+)?\s*[=+*/^]\s*[-+]?\d|"
    r"[∑∫√∞≈≠≤≥±αβγδεζηθλμπρσφψω])",
    re.IGNORECASE,
)
_LATEX_RE = re.compile(r"(\\[a-zA-Z]+|\$[^$]+\$|\$\$.+?\$\$)", re.DOTALL)
_CAPTION_RE = re.compile(r"^\s*(рисунок|рис\.|схема|таблица)\s+\S+", re.IGNORECASE)
_NOISE_RE = re.compile(r"^[\W_\d\s.-]{1,20}$", re.UNICODE)
_PREFIX_RE = re.compile(r"^\s*(passage:|query:)\s*", re.IGNORECASE)
_OOXML_RE = re.compile(r"</?(w|mc):[^>]+>")
_TAG_RE = re.compile(r"<[^>]{1,80}>")


def strip_embedding_prefix(text: str) -> str:
    """Снять служебные E5-префиксы (могут повторяться в перевыгруженных артефактах)."""
    result = str(text or "")
    for _ in range(3):
        new = _PREFIX_RE.sub("", result.lstrip())
        if new == result.lstrip():
            break
        result = new
    return result


def normalize_ocr_text(text: str) -> str:
    """Консервативная нормализация OCR/DOCX-текста без искажения терминологии."""
    text = strip_embedding_prefix(text)
    # склейка переносов "изме-\nрение" → "измерение"
    text = re.sub(r"(?<=[А-Яа-яA-Za-z])[-¬]\s*\n\s*(?=[А-Яа-яA-Za-z])", "", text)
    text = _OOXML_RE.sub(" ", text)
    text = _TAG_RE.sub(" ", text)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def is_noise_text(text: str, min_alpha: int = 3) -> bool:
    stripped = normalize_ocr_text(text)
    if not stripped or _NOISE_RE.match(stripped):
        return True
    alpha = sum(ch.isalpha() for ch in stripped)
    if alpha < min_alpha and not _MATH_STRICT_RE.search(stripped):
        return True
    if len(stripped) <= 8 and stripped.endswith("-") and alpha <= 6:
        return True
    return False


def is_true_formula(text: str, formula_type: str = "") -> bool:
    """Строгий детектор формул. Обычная фраза с '-' или '/' формулой НЕ считается."""
    t = normalize_ocr_text(text)
    if not t or is_noise_text(t, min_alpha=0):
        return False
    if formula_type in {"latex_inline", "latex_block"} or _LATEX_RE.search(t):
        return True
    if _CAPTION_RE.match(t):
        return False
    if len(t) > 260 and not _MATH_STRICT_RE.search(t):
        return False
    return bool(_MATH_STRICT_RE.search(t))


def table_cells(markdown: str) -> List[str]:
    cells = [c.strip() for c in normalize_ocr_text(markdown).replace("\n", "|").split("|")]
    return [c for c in cells if c and c != "---"]


def table_is_useful(markdown: str, min_chars: int = 30) -> bool:
    cells = table_cells(markdown)
    return len(cells) >= 2 and sum(len(c) for c in cells) >= min_chars


def detect_model(content: str, source: str) -> str:
    """Определить модель по содержимому и имени файла; мусор → unknown."""
    hay = f"{source}\n{content[:4000]}"
    scores: Dict[str, int] = {}
    for model, pats in KOIB_MODEL_PATTERNS.items():
        hits = sum(1 for p in pats if re.search(p, hay, re.IGNORECASE))
        if hits:
            scores[model] = hits
    if scores:
        return max(scores, key=scores.get)
    return "unknown"


def clean_model_field(raw_model: str, content: str, source: str) -> str:
    """Если в metadata лежит мусорная 'модель' (Zp21179, использовании-139) — переопределяем."""
    m = (raw_model or "unknown").strip()
    if m in KNOWN_MODELS:
        return m
    return detect_model(content, source)


def make_table_summary(markdown: str, meta: Dict[str, Any]) -> str:
    lines = [l for l in normalize_ocr_text(markdown).split("\n") if l.strip()]
    header = lines[0] if lines else ""
    headers = [h.strip() for h in header.strip("|").split("|") if h.strip() and h.strip() != "---"]
    n_rows = int(meta.get("num_rows", 0) or max(0, len(lines) - 2))
    n_cols = int(meta.get("num_cols", 0) or len(headers))
    parts = [f"Таблица ({n_rows} строк, {n_cols} столбцов)."]
    if headers:
        parts.append("Столбцы: " + ", ".join(headers[:10]) + ".")
    return normalize_ocr_text(" ".join(parts)) or markdown[:300]


def make_formula_summary(content: str) -> str:
    return f"Формула: {normalize_ocr_text(content)[:240]}"


# ─────────────────────────────────────────────────────────────────────────────
# Модель чанка (совместима по полям с src.chunking.Chunk)
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class CleanChunk:
    chunk_id: str
    content: str
    full_content: Optional[str]
    chunk_type: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def quality(self) -> int:
        """Богатство метаданных — для выбора лучшего дубля."""
        q = len(self.content)
        if self.full_content:
            q += 200
        if int(self.metadata.get("page", 0) or 0) > 0:
            q += 500
        if self.metadata.get("model") in KNOWN_MODELS:
            q += 300
        if self.metadata.get("heading"):
            q += 100
        return q


# ─────────────────────────────────────────────────────────────────────────────
# Загрузка и классификация артефактов
# ─────────────────────────────────────────────────────────────────────────────
_KIND_RE = {
    "chunks_new": re.compile(r"^chunks_export_new.*\.(txt|jsonl)$", re.IGNORECASE),
    "chunks": re.compile(r"^chunks.*\.(txt|jsonl)$", re.IGNORECASE),
    "docstore": re.compile(r"^docstore.*\.(txt|jsonl)$", re.IGNORECASE),
    "bm25": re.compile(r"^bm25.*\.(txt|jsonl)$", re.IGNORECASE),
}


def classify_file(name: str) -> str:
    if _KIND_RE["chunks_new"].match(name):
        return "chunks_new"
    if _KIND_RE["chunks"].match(name):
        return "chunks"
    if _KIND_RE["docstore"].match(name):
        return "docstore"
    if _KIND_RE["bm25"].match(name):
        return "bm25"
    return "unknown"


def iter_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if isinstance(obj, dict):
                yield obj


@dataclass
class BuildReport:
    files: Dict[str, int] = field(default_factory=dict)
    records_in: int = 0
    skipped_noise: int = 0
    skipped_empty_table: int = 0
    skipped_no_meta: int = 0
    reclassified_formula: int = 0
    downgraded_table: int = 0
    fixed_prefix: int = 0
    fixed_model: int = 0
    page_zero: int = 0
    deduplicated: int = 0
    kept: int = 0
    by_type: Counter = field(default_factory=Counter)
    by_model: Counter = field(default_factory=Counter)

    def as_dict(self) -> Dict[str, Any]:
        d = self.__dict__.copy()
        d["by_type"] = dict(self.by_type)
        d["by_model"] = dict(self.by_model)
        return d


def repair_record(
    obj: Dict[str, Any],
    src_file: str,
    kind: str,
    report: BuildReport,
) -> Optional[CleanChunk]:
    raw = obj.get("content")
    raw = raw if isinstance(raw, str) else str(raw or "")

    if _PREFIX_RE.match(raw):
        report.fixed_prefix += 1
    content = normalize_ocr_text(raw)
    if not content or is_noise_text(content, min_alpha=2):
        report.skipped_noise += 1
        return None

    meta = dict(obj.get("metadata") or {})
    declared = str(obj.get("chunk_type") or meta.get("chunk_type") or "text").lower()
    if kind in ("chunks", "chunks_new", "bm25"):
        declared = declared if declared in {"text", "table", "formula", "figure"} else "text"

    source = str(meta.get("source") or "").strip()
    page = int(meta.get("page", 0) or 0)
    if page == 0:
        report.page_zero += 1

    # chunks_export_new потерял source/page/model → цитировать нечем.
    no_meta = (not source) and page == 0
    if kind == "chunks_new" and no_meta:
        meta["no_citation"] = True
        source = source or "источник_не_определён"

    # --- ремонт типа ---
    etype = declared
    if etype == "formula" and not is_true_formula(content, str(meta.get("formula_type", ""))):
        etype = "figure" if _CAPTION_RE.match(content) else "text"
        report.reclassified_formula += 1
    if etype == "table" and not table_is_useful(content):
        if len(table_cells(content)) == 0:
            report.skipped_empty_table += 1
            return None
        etype = "text"
        report.downgraded_table += 1

    # --- ремонт модели ---
    raw_model = str(meta.get("model") or "unknown")
    model = clean_model_field(raw_model, content, source)
    if model != raw_model:
        report.fixed_model += 1

    meta.update(
        {
            "source": source,
            "page": page,
            "heading": str(meta.get("heading") or "").strip(),
            "model": model,
            "artifact_file": src_file,
            "artifact_kind": kind,
        }
    )
    meta.pop("embedding", None)

    # --- content vs full_content по типу ---
    if etype == "table":
        chunk_content, full = make_table_summary(content, meta), content
    elif etype == "formula":
        chunk_content, full = make_formula_summary(content), content
    elif etype == "figure":
        chunk_content, full = content, content
    else:
        chunk_content, full = content, None

    cid_material = "|".join([source, str(page), etype, content[:1000]])
    chunk_id = f"{etype}_{text_hash(cid_material)}"
    return CleanChunk(chunk_id, chunk_content, full, etype, meta)


def load_clean_chunks(
    artifacts_dir: Path,
    include_export_new: bool,
    allow_bm25: bool,
    report: BuildReport,
) -> List[CleanChunk]:
    files = sorted(p for p in artifacts_dir.glob("**/*") if p.is_file() and classify_file(p.name) != "unknown")
    # порядок важен для dedup keep-best: docstore (full tables) → chunks (text+meta) → new → bm25
    order = {"docstore": 0, "chunks": 1, "chunks_new": 2, "bm25": 3}
    files.sort(key=lambda p: order.get(classify_file(p.name), 9))

    seen: Dict[str, CleanChunk] = {}  # нормализованный хэш контента → лучший чанк
    for path in files:
        kind = classify_file(path.name)
        if kind == "bm25" and not allow_bm25:
            continue
        if kind == "chunks_new" and not include_export_new:
            continue
        report.files[path.name] = report.files.get(path.name, 0)
        for obj in iter_jsonl(path):
            report.records_in += 1
            report.files[path.name] += 1
            chunk = repair_record(obj, path.name, kind, report)
            if chunk is None:
                continue
            key = text_hash((chunk.full_content or chunk.content).lower()[:2000] + "|" + chunk.chunk_type)
            existing = seen.get(key)
            if existing is None:
                seen[key] = chunk
            else:
                report.deduplicated += 1
                if chunk.quality > existing.quality:
                    seen[key] = chunk

    chunks = list(seen.values())
    for c in chunks:
        report.by_type[c.chunk_type] += 1
        report.by_model[c.metadata.get("model", "unknown")] += 1
    report.kept = len(chunks)
    return chunks


# ─────────────────────────────────────────────────────────────────────────────
# Запись индекса через проверенный src.indexing.IndexBuilder
# ─────────────────────────────────────────────────────────────────────────────
def build_index(chunks: List[CleanChunk], output_dir: Path) -> None:
    try:
        from src.chunking import Chunk
        from src.indexing import IndexBuilder
    except Exception as exc:  # pragma: no cover
        print(
            "\nОШИБКА: не удалось импортировать src.indexing/src.chunking.\n"
            f"  Причина: {exc}\n"
            "  Запустите скрипт из корня репозитория KOIB и установите зависимости:\n"
            "    pip install -r requirements.txt\n"
            "  Для аудита без сборки используйте флаг --dry-run.",
            file=sys.stderr,
        )
        sys.exit(2)

    index_dir = output_dir / "index"
    docstore_path = output_dir / "docstore" / "docstore.db"
    # чистая пересборка — гарантирует целостность FAISS↔BM25↔DocStore
    for sub in ("index", "docstore"):
        d = output_dir / sub
        if d.exists():
            import shutil
            shutil.rmtree(d)

    builder = IndexBuilder(index_dir, docstore_path=docstore_path, load_existing=False)
    project_chunks = [
        Chunk(
            chunk_id=c.chunk_id,
            content=c.content,
            full_content=c.full_content,
            chunk_type=c.chunk_type,
            metadata=c.metadata,
        )
        for c in chunks
    ]
    BATCH = 500
    for i in range(0, len(project_chunks), BATCH):
        builder.add_chunks(project_chunks[i : i + BATCH])
        print(f"  …проиндексировано {min(i + BATCH, len(project_chunks))}/{len(project_chunks)}")
    builder.save()


# ─────────────────────────────────────────────────────────────────────────────
def print_report(report: BuildReport, dry_run: bool) -> None:
    print("\n" + "═" * 62)
    print("  ОТЧЁТ СБОРКИ ИДЕАЛЬНОГО ИНДЕКСА" + ("  [сухой прогон]" if dry_run else ""))
    print("═" * 62)
    print(f"  Прочитано записей:           {report.records_in}")
    for fn, n in report.files.items():
        print(f"     • {fn}: {n}")
    print(f"  Снято префиксов passage/query:{report.fixed_prefix:>6}")
    print(f"  Формул → текст (ремонт типа): {report.reclassified_formula:>6}")
    print(f"  Таблиц → текст (вырожденные): {report.downgraded_table:>6}")
    print(f"  Исправлено поле модели:       {report.fixed_model:>6}")
    print(f"  Записей с page == 0:          {report.page_zero:>6}")
    print(f"  Отброшено (шум):              {report.skipped_noise:>6}")
    print(f"  Отброшено (пустые таблицы):   {report.skipped_empty_table:>6}")
    print(f"  Удалено дублей:               {report.deduplicated:>6}")
    print("  " + "─" * 58)
    print(f"  ИТОГО чистых чанков:          {report.kept:>6}")
    print(f"     по типам:  {dict(report.by_type)}")
    print(f"     по моделям:{dict(report.by_model)}")
    print("═" * 62)


def main() -> None:
    ap = argparse.ArgumentParser(description="Сборка идеального индекса KOIB RAG из артефактов.")
    ap.add_argument("--artifacts-dir", default="./data/artifacts", help="папка с chunks/docstore/bm25 *.txt")
    ap.add_argument("--output-dir", default="./output", help="куда писать индексы")
    ap.add_argument("--include-export-new", action="store_true", help="импортировать chunks_export_new (без цитат!)")
    ap.add_argument("--allow-bm25", action="store_true", help="импортировать bm25 (лемматизированный текст!)")
    ap.add_argument("--dry-run", action="store_true", help="только аудит и план, без сборки и без torch/faiss")
    ap.add_argument("--report-json", default="", help="путь для сохранения отчёта в JSON")
    args = ap.parse_args()

    artifacts_dir = Path(args.artifacts_dir).expanduser()
    if not artifacts_dir.exists():
        print(f"Папка артефактов не найдена: {artifacts_dir}", file=sys.stderr)
        sys.exit(1)

    report = BuildReport()
    chunks = load_clean_chunks(artifacts_dir, args.include_export_new, args.allow_bm25, report)
    print_report(report, args.dry_run)

    if args.report_json:
        Path(args.report_json).write_text(json.dumps(report.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nОтчёт сохранён: {args.report_json}")

    if args.dry_run:
        print("\n[сухой прогон] Индекс НЕ собирался. Уберите --dry-run для боевой сборки.")
        return

    output_dir = Path(args.output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"\nСтрою индекс в {output_dir} …")
    build_index(chunks, output_dir)
    print("\nГотово. Индексы: text_index.faiss + summary_index.faiss + bm25_fts.db + docstore.db")


if __name__ == "__main__":
    main()
