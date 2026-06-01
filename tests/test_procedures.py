# -*- coding: utf-8 -*-
from src.generation import build_prompt
from src.procedures import contains_procedural_reminder, detect_incident, ensure_procedural_reminder
from src.retrieval import RetrievalResult


def test_detects_technical_incident_query():
    assert detect_incident("КОИБ не включается, что делать оператору?")
    assert detect_incident("Застрял бюллетень в сканере")
    assert not detect_incident("Какие параметры указаны в таблице?")


def test_ensure_procedural_reminder_for_incident():
    answer = ensure_procedural_reminder("Проверьте питание КОИБ.", "КОИБ не работает")
    assert contains_procedural_reminder(answer)
    assert "председателя участковой комиссии" in answer
    assert "горячую линию технической поддержки" in answer
    assert "регламентом ЦИК" in answer


def test_build_prompt_adds_incident_instruction():
    results = [RetrievalResult(chunk_id="1", content="Контекст", source="doc.pdf", page=1)]
    prompt = build_prompt("КОИБ завис, что делать?", results)
    assert "технический инцидент" in prompt
    assert "Регламентное уведомление" in prompt
