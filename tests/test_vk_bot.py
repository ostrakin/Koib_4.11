# -*- coding: utf-8 -*-
from src.vk_bot import VKBotService, split_vk_message


def test_split_vk_message_respects_limit():
    text = ("Абзац с инструкцией. " * 20 + "\n\n") * 8
    chunks = split_vk_message(text, max_chars=120)
    assert len(chunks) > 1
    assert all(len(chunk) <= 120 for chunk in chunks)
    assert "Абзац" in chunks[0]


def test_parse_vk_message_event():
    service = VKBotService(lambda: None)
    try:
        payload = {
            "type": "message_new",
            "event_id": "evt-test-1",
            "group_id": 123,
            "object": {
                "message": {
                    "from_id": 42,
                    "peer_id": 42,
                    "text": "Что делать, если КОИБ не включается?",
                    "id": 7,
                    "conversation_message_id": 8,
                    "date": 1710000000,
                }
            },
        }
        message = service.parse_message(payload)
        assert message is not None
        assert message.event_key == "evt-test-1"
        assert message.user_id == 42
        assert message.peer_id == 42
        assert "не включается" in message.text
    finally:
        service.close()


def test_prepare_group_chat_mention_is_removed():
    service = VKBotService(lambda: None)
    try:
        assert service._prepare_text("Коиб, что делать?", is_group_chat=True) == "что делать?"
        assert service._prepare_text("[club123|KOIB] помоги", is_group_chat=True) == "помоги"
    finally:
        service.close()
