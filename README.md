# KOIB RAG v4.11.0 — OCR/artifact-ready VK-ready версия

Production-ready RAG-система для вопросов и ответов по технической документации КОИБ. Версия v4.11.0 сохраняет возможности v4.10.0 и добавляет полноценный VK-бот для операторов, подробный GigaChat prompt и обязательное регламентное уведомление при нештатных ситуациях.

## Главное в v4.11.0

- Добавлен отдельный сервисный модуль `src/vk_bot.py`: VK API, команды, rate limiting, dedup, отправка сообщений и post-processing больше не смешаны с FastAPI route.
- `api/routes/vk_callback.py` теперь только принимает webhook, валидирует событие и быстро возвращает VK `ok`.
- Добавлена SQLite-дедупликация VK callback events по `event_id`, чтобы повтор webhook не запускал повторный RAG-ответ.
- Добавлен global/user rate limiting.
- Ответы VK автоматически режутся на части под лимит сообщения.
- Добавлен typing indicator через `messages.setActivity`.
- Добавлены команды `/start`, `/help`, `/reset`, `/health`.
- Групповые беседы выключены по умолчанию, чтобы бот не спамил в чатах; включаются через `.env`.
- Добавлен модуль `src/procedures.py`, который определяет технические инциденты и гарантированно добавляет регламентное уведомление.
- `src/generation.py` получил усиленный GigaChat system prompt с RAG-границами, защитой от prompt injection и процессуальным правилом для нештатных ситуаций.
- Добавлены документы `docs/VK_BOT_SETUP.md` и `prompts/GIGACHAT_SYSTEM_PROMPT.md`.
- Unit-тесты расширены до 63 проверок.

## Регламентное требование для нештатных ситуаций

При вопросах вида «КОИБ не включается», «завис», «застрял бюллетень», «ошибка печати», «нет питания», «не сканирует» система добавляет отдельный блок:

```text
Регламентное уведомление: Важно: при устранении нештатной ситуации оператор обязан проинформировать председателя участковой комиссии и сообщить об инциденте на горячую линию технической поддержки в порядке, предусмотренном регламентом ЦИК.
```

Это реализовано на двух уровнях:

1. В system prompt для GigaChat.
2. В программном post-processing `src/procedures.py`, чтобы уведомление не зависело от поведения LLM.

## Архитектура

```text
koib-rag/
├── api/
│   ├── app.py                  # FastAPI app + lifespan
│   ├── routes/
│   │   ├── health.py            # /, /health, /ready
│   │   ├── query.py             # POST /query
│   │   └── vk_callback.py       # тонкий VK Callback route
│   └── middleware/logging.py
├── src/
│   ├── vk_bot.py                # VK bot service: команды, dedup, rate limit, send
│   ├── procedures.py            # регламентные правила для инцидентов
│   ├── parsing.py               # PDF/DOCX/OCR parsing
│   ├── chunking.py              # Smart chunks + table/formula summaries
│   ├── indexing.py              # FAISS + SQLite FTS5 + DocStore
│   ├── retrieval.py             # Hybrid search + reranker + cache
│   ├── generation.py            # GigaChat/OpenAI/Ollama clients + prompt builder
│   ├── validation.py            # citation/authenticity validation
│   ├── rag_pipeline.py          # end-to-end RAG pipeline
│   ├── safety.py                # request/answer safety
│   ├── quarantine.py            # quarantined chunks
│   ├── logging_module.py        # JSONL query logs
│   └── evaluation.py            # RAG metrics / LLM-as-judge
├── docs/
│   └── VK_BOT_SETUP.md          # настройка VK Callback API
├── prompts/
│   └── GIGACHAT_SYSTEM_PROMPT.md # полный prompt для GigaChat
├── tests/
├── batch_ingest.py
├── config.py
├── main.py
├── requirements.txt
└── .env.example
```

Это модульный монолит: API, VK callback и RAG pipeline работают в одном процессе FastAPI. Для VPS 2 GB это проще и надёжнее, чем набор микросервисов. При росте нагрузки можно вынести generation или ingestion в отдельный сервис.

## Установка

```bash
python -m venv .venv
source .venv/bin/activate
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
cp .env.example .env
```

Для OCR установите Tesseract и русский язык:

```bash
sudo apt-get update
sudo apt-get install -y tesseract-ocr tesseract-ocr-rus
```

## Индексация документов

Положите документы в `data/docs` и выполните полный rebuild:

```bash
python main.py --ingest --rebuild
```

Следующие добавления новых документов можно индексировать incremental:

```bash
python main.py --ingest
```

Если существующий файл изменён или удалён, ingest автоматически запустит полный rebuild, чтобы FAISS, FTS5 и DocStore не противоречили друг другу.

## CLI-запрос

```bash
python main.py --query "Как выполнить проверку сканирующего устройства?" --top-k 4
```

## HTTP API

```bash
python main.py --serve
```

Проверки:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/ready
```

Запрос к RAG:

```bash
curl -X POST http://127.0.0.1:8000/query \
  -H 'Content-Type: application/json' \
  -d '{"query":"Как перезагрузить КОИБ?","top_k":4,"validate":true}'
```

## VK Callback API

Минимальные переменные в `.env`:

```env
VK_CONFIRM_CODE=...
VK_GROUP_ID=...
VK_SECRET_KEY=...
VK_ACCESS_TOKEN=...
VK_API_VERSION=5.131
```

Production-настройки:

```env
VK_RATE_LIMIT_PER_MINUTE=20
VK_GLOBAL_RATE_LIMIT_PER_MINUTE=120
VK_MAX_INCOMING_CHARS=1500
VK_MAX_OUTGOING_CHARS=3900
VK_OUTBOUND_TIMEOUT=10
VK_DEDUP_TTL_SECONDS=86400
VK_SEND_TYPING=true
VK_REPLY_IN_GROUP_CHATS=false
VK_BOT_MENTION_ALIASES=коиб,koib
VK_ADMIN_IDS=
PROCEDURAL_REMINDER_ENABLED=true
```

URL callback:

```text
https://your-domain.example/vk_callback
```

Подробная инструкция: `docs/VK_BOT_SETUP.md`.

## GigaChat prompt

Полный prompt лежит в:

```text
prompts/GIGACHAT_SYSTEM_PROMPT.md
```

Кодовая версия prompt используется в `src/generation.py`. Для боевого режима рекомендуется:

```env
GIGACHAT_TEMPERATURE=0.1
GIGACHAT_MAX_TOKENS=1536
```

## Перенос на VPS

1. На ПК выполните `python main.py --ingest --rebuild`.
2. Перенесите папку `output/` и код проекта на VPS.
3. Убедитесь, что `LOCAL_EMBEDDING_MODEL` на VPS совпадает с машиной индексации.
4. Заполните `.env` на VPS.
5. Запустите `python main.py --serve`.
6. В VK Callback API укажите `https://your-domain.example/vk_callback`.

## Тесты и статическая проверка

```bash
python -m compileall -q .
pytest -q
```

Ожидаемый результат для этой сборки:

```text
63 passed
```

## v4.11.0: распознанные DOCX/CSV и импорт старых артефактов

В v4.11.0 добавлена обработка распознанных `.docx`, `.csv`, `.txt/.md` и отдельный импорт старых JSONL-артефактов индекса. Это важно, потому что файлы `chunks*.txt`, `docstore*.txt`, `bm25*.txt` нельзя класть в `data/docs` как обычные документы: они должны импортироваться через `data/artifacts`.

Рекомендуемая структура:

```text
data/docs/        # PDF, DOCX, CSV, TXT с распознанным текстом
data/artifacts/   # chunks*.txt, docstore*.txt, bm25*.txt из старого индекса
output/           # новые индексы
```

Полная переиндексация документов и старых артефактов:

```bash
python main.py --ingest --rebuild --ingest-artifacts
```

Импорт старых артефактов исправляет две найденные проблемы: удаляет служебный `passage:` из пользовательского текста и переклассифицирует ложные `formula`-чанки в обычный текст или подписи рисунков. `bm25*.txt` по умолчанию не используется как источник контента, потому что он содержит лемматизированный текст; включайте его только как fallback через `ARTIFACT_ALLOW_BM25_FALLBACK=true`.
