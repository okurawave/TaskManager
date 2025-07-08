import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import task_bot.bot as bot


@pytest.mark.asyncio
async def test_handle_add_task(monkeypatch):
    # Google Sheetsのadd_taskをモック
    monkeypatch.setattr(bot.google_sheets, "add_task", lambda ws, title, assignee, due: 1)
    # gs_worksheetをダミーでセット
    bot.gs_worksheet = MagicMock()
    # Discord Messageのモック
    message = MagicMock()
    message.mentions = []
    message.channel.send = AsyncMock()
    args = {"title": "Test Task", "due_date": "2025-07-08", "assignee": "Tester"}
    await bot.handle_add_task(message, args)
    message.channel.send.assert_called()


@pytest.mark.asyncio
async def test_handle_list_tasks(monkeypatch):
    # Google Sheetsのread_tasksをモック
    monkeypatch.setattr(bot.google_sheets, "read_tasks", lambda ws, **kwargs: [
        {bot.google_sheets.COL_TASK_ID: 1, bot.google_sheets.COL_TITLE: "Task1", bot.google_sheets.COL_DUE_DATE: "2025-07-08", bot.google_sheets.COL_ASSIGNEE_ID: "Tester"}
    ])
    bot.gs_worksheet = MagicMock()
    message = MagicMock()
    message.mentions = []
    message.author.id = 123
    message.author.display_name = "Tester"
    message.channel.send = AsyncMock()
    args = {"assignee": "me", "due_date_range": None}
    await bot.handle_list_tasks(message, args)
    message.channel.send.assert_called()
