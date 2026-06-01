# -*- coding: utf-8 -*-
"""FastAPI route для VK Callback API.

Route отвечает VK строкой "ok" максимально быстро. Вся тяжелая работа
(RAG, GigaChat, отправка сообщений) уходит в BackgroundTasks.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Request

from src.rag_pipeline import RAGPipeline
from src.vk_bot import VKBotService

logger = logging.getLogger("koib.api.vk")
router = APIRouter()
_pipeline: Optional[RAGPipeline] = None
_vk_service: Optional[VKBotService] = None


def _get_pipeline() -> RAGPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = RAGPipeline()
    return _pipeline


def _get_vk_service() -> VKBotService:
    global _vk_service
    if _vk_service is None:
        _vk_service = VKBotService(pipeline_factory=_get_pipeline)
    return _vk_service


async def close_pipeline() -> None:
    global _pipeline, _vk_service
    if _vk_service is not None:
        _vk_service.close()
        _vk_service = None
    if _pipeline is not None:
        await _pipeline.close()
        _pipeline = None


@router.post("/vk_callback")
async def vk_webhook(request: Request, background_tasks: BackgroundTasks) -> str:
    service = _get_vk_service()
    try:
        raw_data = await request.json()
    except Exception:
        logger.warning("VK callback без валидного JSON")
        return "ok"

    if not service.validate_callback(raw_data):
        return "ok"

    if service.is_confirmation(raw_data):
        return service.confirmation_code()

    message = service.parse_message(raw_data)
    if message is None:
        return "ok"

    should_process, reason = service.should_process(message)
    if not should_process:
        logger.debug("VK callback пропущен: %s", reason)
        return "ok"

    session = request.app.state.vk_session
    background_tasks.add_task(service.process_message, message, session)
    return "ok"
