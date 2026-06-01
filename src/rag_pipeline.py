# -*- coding: utf-8 -*-
"""Высокоуровневый RAG-пайплайн: memory -> retrieval -> generation -> validation."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict

from config import EMBEDDING_PROVIDER, MAX_CONCURRENT_GENERATIONS, PROCEDURAL_REMINDER_ENABLED, QUERY_PREFIX, USE_USHAPED_CONTEXT
from .generation import LLMClient, build_prompt
from .procedures import ensure_procedural_reminder
from .indexing import get_global_embeddings
from .retrieval import HybridRetriever, SemanticCache, reorder_u_shape
from .utils import ConversationMemory, rewrite_query
from .validation import AnswerValidator, get_blocked_response

logger = logging.getLogger("koib.rag_pipeline")
CONTEXT_PRONOUNS = {
    "он", "она", "оно", "они", "его", "её", "их", "нему", "ней", "ними",
    "этом", "этот", "тот", "такой", "там", "это", "неё", "него", "у", "него", "неё",
}


class RAGPipeline:
    def __init__(self):
        self.retriever = HybridRetriever()
        self.llm = LLMClient()
        self.semantic_cache = SemanticCache()
        self.memory = ConversationMemory()
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_GENERATIONS)

    async def close(self) -> None:
        await self.llm.close()

    async def answer(
        self,
        query: str,
        user_id: str = "anonymous",
        k: int = 4,
        model_filter: str = "",
        use_memory: bool = True,
        validate: bool = True,
    ) -> Dict[str, Any]:
        query = (query or "").strip()
        t0 = time.time()
        if not query:
            return {"answer": "Пустой запрос.", "sources": [], "status": "review", "latency": 0.0}

        async with self._semaphore:
            history = await self.memory.get_history(user_id) if use_memory and user_id != "anonymous" else []
            search_query = query
            if history and any(w.strip(",.!?").lower() in CONTEXT_PRONOUNS for w in query.split()):
                search_query = await rewrite_query(query, history, self.llm)

            query_embedding = None
            try:
                emb = get_global_embeddings()
                embedding_text = (QUERY_PREFIX + search_query) if EMBEDDING_PROVIDER == "local" else search_query
                query_embedding = await asyncio.to_thread(emb.embed_query, embedding_text)
            except Exception as exc:
                logger.warning("Embedding недоступен, будет использован только BM25/FTS: %s", exc)

            if query_embedding:
                cached = self.semantic_cache.get(search_query, query_embedding)
                if cached:
                    answer = cached["answer"]
                    if PROCEDURAL_REMINDER_ENABLED:
                        answer = ensure_procedural_reminder(answer, query)
                    if use_memory and user_id != "anonymous":
                        await self.memory.add_message(user_id, "user", query)
                        await self.memory.add_message(user_id, "assistant", answer[:500])
                    return {
                        "answer": answer,
                        "sources": cached.get("sources", []),
                        "status": "approved",
                        "latency": time.time() - t0,
                    }

            results = await asyncio.to_thread(self.retriever.search, search_query, k=k, model_filter=model_filter)
            if not results:
                answer = "По вашему запросу не найдено релевантных фрагментов в официальной документации."
                if PROCEDURAL_REMINDER_ENABLED:
                    answer = ensure_procedural_reminder(answer, query)
                if use_memory and user_id != "anonymous":
                    await self.memory.add_message(user_id, "user", query)
                    await self.memory.add_message(user_id, "assistant", answer[:500])
                return {"answer": answer, "sources": [], "status": "review", "latency": time.time() - t0}

            if USE_USHAPED_CONTEXT and len(results) > 2:
                results = reorder_u_shape(results)

            prompt = build_prompt(search_query, results)
            answer = await self.llm.generate_async(prompt)

            status = "approved"
            if answer.startswith("Ошибка"):
                status = "review"
            elif validate:
                try:
                    validation_result = AnswerValidator().validate(answer, results, query)
                    if validation_result.status == "rejected":
                        status = "rejected"
                        answer = get_blocked_response()
                    elif validation_result.status == "review":
                        status = "review"
                except Exception as exc:
                    logger.warning("Validation error: %s", exc)

            if PROCEDURAL_REMINDER_ENABLED:
                answer = ensure_procedural_reminder(answer, query)

            if use_memory and user_id != "anonymous":
                await self.memory.add_message(user_id, "user", query)
                await self.memory.add_message(user_id, "assistant", answer[:500])

            sources = [
                {
                    "document": r.source,
                    "page": r.page,
                    "heading": r.heading,
                    "chunk_type": r.chunk_type,
                    "score": r.score,
                }
                for r in results
            ]
            if status == "approved" and query_embedding:
                self.semantic_cache.set(search_query, query_embedding, answer, sources)

            return {"answer": answer, "sources": sources, "status": status, "latency": time.time() - t0}
