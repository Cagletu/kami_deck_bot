import asyncio
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from typing import Callable, Awaitable, Dict, Any
from datetime import datetime

class AutoCleanupMiddleware(BaseMiddleware):
    def __init__(self, bot, max_messages=20, user_msg_ttl=30, bot_msg_ttl=300):
        super().__init__()
        self.bot = bot
        self.max_messages = max_messages
        self.user_msg_ttl = user_msg_ttl
        self.bot_msg_ttl = bot_msg_ttl

        # chat_id -> list[(msg_id, timestamp)]
        self.history: Dict[int, list[tuple[int, datetime]]] = {}

    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:

        chat_id = event.message.chat.id if isinstance(event, CallbackQuery) else event.chat.id

        if chat_id not in self.history:
            self.history[chat_id] = []

        # Входящее сообщение пользователя
        if isinstance(event, Message) and not event.from_user.is_bot:
            self._track(chat_id, event.message_id)

            if not self._is_card_message(event):
                asyncio.create_task(self._delete_later(chat_id, event.message_id, self.user_msg_ttl))

        # Выполняем хендлер
        result = await handler(event, data)

        # Если хендлер вернул одно сообщение
        if isinstance(result, Message):
            self._track(chat_id, result.message_id)

            if not self._is_card_message(result):
                asyncio.create_task(self._delete_later(chat_id, result.message_id, self.bot_msg_ttl))

        # Если хендлер вернул media_group
        if isinstance(result, list):
            for msg in result:
                if isinstance(msg, Message):
                    self._track(chat_id, msg.message_id)

                    if not self._is_card_message(msg):
                        asyncio.create_task(self._delete_later(chat_id, msg.message_id, self.bot_msg_ttl))

        await self._cleanup_if_needed(chat_id)
        return result

    def _is_card_message(self, msg: Message) -> bool:
        """Определяем, является ли сообщение карточкой (включая media_group)"""
        return bool(msg.photo)

    def _track(self, chat_id: int, msg_id: int):
        self.history[chat_id].append((msg_id, datetime.now()))

    async def _delete_later(self, chat_id: int, msg_id: int, delay: int):
        await asyncio.sleep(delay)
        try:
            await self.bot.delete_message(chat_id, msg_id)
        except Exception:
            pass

    async def _cleanup_if_needed(self, chat_id: int):
        msgs = self.history[chat_id]

        if len(msgs) <= self.max_messages:
            return

        to_delete = msgs[:-self.max_messages]
        self.history[chat_id] = msgs[-self.max_messages:]

        for msg_id, _ in to_delete:
            try:
                await self.bot.delete_message(chat_id, msg_id)
            except:
                pass
