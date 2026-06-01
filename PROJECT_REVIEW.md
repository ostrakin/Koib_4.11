# Аудит проекта KOIB RAG и список улучшений

## Главный вывод

Проект является не набором микросервисов, а модульным монолитом: FastAPI API, VK Callback API и RAG pipeline живут в одном процессе. Это нормально для VPS 1 vCPU / 2 GB RAM, но в исходной версии были архитектурные несостыковки между слоями API, retrieval, generation, validation и ingest.

## Критичные проблемы исходной версии

1. **Несогласованные версии**: `.env.example` и API app указывали v4.8, README и health — v4.6, многие модули — v4.5.
2. **Отсутствовал `LLMClient.generate()`**: `evaluation.py`, `validation.py` и HyDE в `retrieval.py` вызывали синхронный метод, которого не было. Работал только `generate_async()`.
3. **VK bypass валидации**: VK route вызывал pipeline с `validate=False`, хотя публичный бот должен валидировать ответы.
4. **README обещал Rate Limiting**, но в `vk_callback.py` его не было.
5. **Safety блокировал технические сбои**, хотя справка по техническим неисправностям КОИБ — основной сценарий проекта.
6. **Incremental ingest был небезопасным**: manifest хранил только имя файла; файлы с одинаковым именем в разных папках конфликтовали, изменённые/удалённые документы могли оставить старые чанки в FAISS/SQLite.
7. **Кастомный `--output-dir` ломал DocStore**: FAISS мог писаться в один output, а `docstore.db` — в глобальный путь из config.
8. **E5 prefix использовался только для query**, но не для passages, что ухудшало качество векторного поиска.
9. **`.doc` был заявлен как поддерживаемый**, но `python-docx` не умеет читать старый бинарный `.doc`.
10. **CLI принудительно включал offline режим HuggingFace**, из-за чего первый запуск на новой машине мог не скачать embedding-модель.

## Что сделано в готовой версии v4.9.0

- Централизована версия через `APP_VERSION`.
- Добавлен sync/async LLMClient с кэшированием GigaChat token.
- Добавлен `POST /query` для прямого API.
- Добавлен `/ready` для проверки наличия индексов.
- Переписан VK Callback: `secret/group_id`, rate limit, `validate=True`, безопасная отправка сообщений.
- Переписан ingest manifest: теперь хранятся относительный путь, size, mtime, sha256, число чанков.
- При изменённых/удалённых документах incremental автоматически делает full rebuild.
- Исправлены output-пути для IndexBuilder/DocStore.
- Добавлен `passage:` prefix для локальных E5 embeddings.
- Добавлен fallback `Document` для unit-тестов без полного LangChain окружения.
- Добавлена обратная совместимость `detect_model_in_text`: результат можно распаковывать как `(model, confidence)` и сравнивать со строкой в старых тестах.
- Тесты приведены к зелёному статусу: `57 passed`.

## Проверки

Выполнено:

```bash
python -m compileall -q .
pytest -q
```

Результат:

```text
57 passed
```

## Рекомендации на следующий этап

1. Вынести ingestion в отдельный job/service, если документов станет много.
2. Добавить Dockerfile и systemd unit под VPS.
3. Добавить end-to-end тест с маленьким fixture PDF/DOCX и реальным индексом.
4. Добавить observability: structured JSON logs + Prometheus metrics.
5. Добавить админ-команды для карантина чанков и ручной переиндексации одного документа.
