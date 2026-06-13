"""Versioned WebSocket event builders (all events carry ``v: 1`` + a ``type``).

Plain dict builders (not Pydantic) — they're serialized straight to JSON over the
socket. Message payloads are already-serialized GroupMessageOut dicts.
"""

from __future__ import annotations

from typing import Any

V = 1


def message_new(message: dict) -> dict:
    return {"v": V, "type": "message_new", "message": message}


def agent_typing(thread_id: int, is_typing: bool) -> dict:
    return {"v": V, "type": "agent_typing", "thread_id": thread_id, "is_typing": is_typing}


def typing(thread_id: int, user_id: int, username: str, is_typing: bool) -> dict:
    return {"v": V, "type": "typing", "thread_id": thread_id, "user_id": user_id, "username": username, "is_typing": is_typing}


def presence(thread_id: int, online_user_ids: list[int]) -> dict:
    return {"v": V, "type": "presence", "thread_id": thread_id, "online_user_ids": online_user_ids}


def read_receipt(thread_id: int, user_id: int, last_seq: int) -> dict:
    return {"v": V, "type": "read_receipt", "thread_id": thread_id, "user_id": user_id, "last_seq": last_seq}


def member_joined(thread_id: int, user_id: int, username: str) -> dict:
    return {"v": V, "type": "member_joined", "thread_id": thread_id, "user_id": user_id, "username": username}


def member_left(thread_id: int, user_id: int) -> dict:
    return {"v": V, "type": "member_left", "thread_id": thread_id, "user_id": user_id}


def invite_new(invite: dict) -> dict:
    return {"v": V, "type": "invite_new", "invite": invite}


def invite_cancelled(invite_id: int, group_chat_id: int) -> dict:
    return {"v": V, "type": "invite_cancelled", "invite_id": invite_id, "group_chat_id": group_chat_id}


def invite_accepted(invite_id: int, group_chat_id: int, user_id: int) -> dict:
    return {"v": V, "type": "invite_accepted", "invite_id": invite_id, "group_chat_id": group_chat_id, "user_id": user_id}


def thread_unread_bump(thread_id: int, unread_count: int = 1) -> dict:
    return {"v": V, "type": "thread_unread_bump", "thread_id": thread_id, "unread_count": unread_count}


def announcement_new(announcement_id: int, classroom_id: int, author: str) -> dict:
    return {"v": V, "type": "announcement_new", "announcement_id": announcement_id, "classroom_id": classroom_id, "author": author}


def comment_new(announcement_id: int, classroom_id: int, author: str) -> dict:
    return {"v": V, "type": "comment_new", "announcement_id": announcement_id, "classroom_id": classroom_id, "author": author}
