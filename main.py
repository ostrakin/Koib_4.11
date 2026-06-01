# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(ROOT))

from config import API_HOST, API_PORT, APP_VERSION, ARTIFACTS_DIR, DOCS_DIR, FINAL_TOP_K, HF_OFFLINE_MODE, OUTPUT_DIR, ensure_dirs

if HF_OFFLINE_MODE:
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S")


def cmd_ingest(args) -> None:
    from batch_ingest import BatchIngester

    BatchIngester(Path(args.docs_dir), Path(args.output_dir), incremental=not args.rebuild, artifacts_dir=Path(args.artifacts_dir), ingest_artifacts=args.ingest_artifacts).process_all()


def cmd_query(args) -> None:
    from src.rag_pipeline import RAGPipeline

    async def run() -> None:
        pipeline = RAGPipeline()
        t0 = time.time()
        try:
            result = await pipeline.answer(
                query=args.query,
                user_id="cli",
                k=args.top_k,
                model_filter=args.model_filter,
                use_memory=False,
                validate=True,
            )
            print(f"\nОТВЕТ:\n{result['answer']}")
            if result.get("sources"):
                print("\nИсточники:")
                seen = set()
                for s in result["sources"]:
                    key = f"{s.get('document')}_{s.get('page')}"
                    if key not in seen:
                        seen.add(key)
                        print(f"  - {s.get('document')}, стр. {s.get('page')}")
            print(f"\nСтатус: {result.get('status')} | Время: {time.time() - t0:.2f}с")
        finally:
            await pipeline.close()

    asyncio.run(run())


def cmd_serve(args) -> None:
    import uvicorn

    uvicorn.run("api.app:app", host=args.host, port=args.port, log_level="info")


def cmd_evaluate(args) -> None:
    from src.evaluation import RAGEvaluator, print_report

    path = Path(args.evaluate)
    if not path.exists():
        raise FileNotFoundError(f"Файл оценки не найден: {path}")
    questions = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(questions, list):
        raise ValueError("Файл оценки должен содержать JSON-массив объектов")
    evaluator = RAGEvaluator()
    out_path = Path(args.output_dir) / "metadata" / "evaluation_results.json"
    results = evaluator.evaluate_batch(questions, save_path=out_path)
    print_report(results)
    print(f"\nРезультаты сохранены: {out_path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=f"Koib RAG v{APP_VERSION}")
    parser.add_argument("--ingest", action="store_true", help="проиндексировать документы")
    parser.add_argument("--query", type=str, default="", help="задать вопрос из CLI")
    parser.add_argument("--serve", action="store_true", help="запустить FastAPI сервер")
    parser.add_argument("--evaluate", type=str, default="", help="JSON-файл для оценки качества")
    parser.add_argument("--docs-dir", type=str, default=str(DOCS_DIR))
    parser.add_argument("--output-dir", type=str, default=str(OUTPUT_DIR))
    parser.add_argument("--artifacts-dir", type=str, default=str(ARTIFACTS_DIR), help="папка со старыми артефактами chunks/docstore/bm25 JSONL")
    parser.add_argument("--ingest-artifacts", action="store_true", help="импортировать очищенные старые артефакты chunks/docstore/bm25")
    parser.add_argument("--top-k", type=int, default=FINAL_TOP_K)
    parser.add_argument("--model-filter", type=str, default="")
    parser.add_argument("--rebuild", action="store_true", help="полностью пересобрать индексы вместо incremental")
    parser.add_argument("--host", type=str, default=API_HOST)
    parser.add_argument("--port", type=int, default=API_PORT)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    ensure_dirs()
    if args.ingest:
        cmd_ingest(args)
    elif args.query:
        cmd_query(args)
    elif args.serve:
        cmd_serve(args)
    elif args.evaluate:
        cmd_evaluate(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
