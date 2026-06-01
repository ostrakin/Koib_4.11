# VK-бот KOIB RAG: настройка и эксплуатация

## Что реализовано

VK-бот работает через VK Callback API и FastAPI endpoint:

```text
POST /vk_callback
```

Сервер сразу возвращает VK строку `ok`, а тяжёлая обработка вопроса уходит в `BackgroundTasks`. Это важно: VK не должен ждать, пока RAG найдёт контекст и GigaChat сгенерирует ответ.

## Возможности бота

- Проверка `secret` и `group_id` для защиты callback endpoint.
- Быстрый ответ `confirmation` кодом для подключения сервера в настройках VK.
- SQLite-дедупликация `event_id`, чтобы повтор webhook не запускал повторный ответ.
- Rate limiting на пользователя и глобально по боту.
- Поддержка личных сообщений сообщества; групповые беседы выключены по умолчанию.
- Команды `/start`, `/help`, `/reset`, `/health`.
- Индикатор «печатает...» через `messages.setActivity`.
- Разбиение длинных ответов под лимит VK.
- Безопасная постобработка ответа: sanitation, fallback-сообщение, добавление источников при необходимости.
- Обязательное регламентное уведомление при нештатных ситуациях.

## Переменные окружения

Минимум:

```env
VK_CONFIRM_CODE=код_подтверждения_из_VK
VK_GROUP_ID=123456789
VK_SECRET_KEY=сложный_секрет_из_настроек_callback
VK_ACCESS_TOKEN=токен_сообщества_с_правами_messages
VK_API_VERSION=5.131
```

Рекомендуемые production-настройки:

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
VK_ADMIN_IDS=12345678,87654321
PROCEDURAL_REMINDER_ENABLED=true
```

## Настройка сообщества VK

1. Откройте управление сообществом VK.
2. Включите сообщения сообщества.
3. Создайте ключ доступа сообщества с правами на сообщения.
4. Откройте раздел Callback API.
5. Укажите URL сервера:

```text
https://your-domain.example/vk_callback
```

6. Укажите `Secret key`; это значение должно совпадать с `VK_SECRET_KEY`.
7. Скопируйте confirmation code в `VK_CONFIRM_CODE`.
8. В событиях включите `Входящее сообщение` / `message_new`.
9. Сохраните настройки и нажмите подтверждение сервера.

## Запуск сервера

```bash
cp .env.example .env
# заполните .env
python main.py --serve
```

Проверки:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/ready
```

## Проверка callback вручную

Confirmation:

```bash
curl -X POST http://127.0.0.1:8000/vk_callback \
  -H 'Content-Type: application/json' \
  -d '{"type":"confirmation","group_id":123456789,"secret":"YOUR_SECRET"}'
```

Ожидаемый ответ — значение `VK_CONFIRM_CODE`.

Тестовое сообщение:

```bash
curl -X POST http://127.0.0.1:8000/vk_callback \
  -H 'Content-Type: application/json' \
  -d '{
    "type":"message_new",
    "event_id":"manual-test-1",
    "group_id":123456789,
    "secret":"YOUR_SECRET",
    "object":{
      "message":{
        "from_id":123,
        "peer_id":123,
        "text":"Что делать, если КОИБ не включается?",
        "id":1,
        "conversation_message_id":1,
        "date":1710000000
      }
    }
  }'
```

Сервер должен вернуть `ok`. Реальная отправка ответа в VK произойдёт только при корректном `VK_ACCESS_TOKEN`.

## Команды пользователя

```text
/start  — приветствие и краткая инструкция
/help   — справка по использованию
/reset  — очистить историю диалога пользователя
/health — статус бота, только для VK_ADMIN_IDS
```

## Групповые беседы

По умолчанию:

```env
VK_REPLY_IN_GROUP_CHATS=false
```

Так бот не будет случайно отвечать в беседах. Для включения:

```env
VK_REPLY_IN_GROUP_CHATS=true
VK_BOT_MENTION_ALIASES=коиб,koib
```

Тогда можно писать:

```text
Коиб, что делать, если сканер не принимает бюллетень?
```

## Регламентное уведомление при инцидентах

Если вопрос похож на технический инцидент, например:

```text
КОИБ завис
не включается сканер
застрял бюллетень
ошибка печати
нет питания
```

бот гарантированно добавляет:

```text
Регламентное уведомление: Важно: при устранении нештатной ситуации оператор обязан проинформировать председателя участковой комиссии и сообщить об инциденте на горячую линию технической поддержки в порядке, предусмотренном регламентом ЦИК.
```

Это сделано на двух уровнях:

1. В system prompt для GigaChat.
2. В программном post-processing `src/procedures.py`, чтобы уведомление не зависело от поведения LLM.

## Безопасность

- Держите `VK_ACCESS_TOKEN`, `VK_SECRET_KEY` и `GIGACHAT_CREDENTIALS` только в `.env` или секретах сервера.
- Не публикуйте `.env` в репозитории.
- Используйте HTTPS перед VK Callback API.
- Укажите `VK_GROUP_ID`, чтобы endpoint не принимал callback от чужого сообщества.
- Оставьте `VK_REPLY_IN_GROUP_CHATS=false`, если бот нужен только для личных сообщений операторов.
- Следите за `output/logs` и rate limit при реальной нагрузке.
