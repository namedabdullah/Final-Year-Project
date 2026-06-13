"""SAMpai ORM models. Importing this package registers all tables on Base.metadata
(used by Alembic autogenerate)."""

from __future__ import annotations

from lightrag.api.sampai.models.base import Base
from lightrag.api.sampai.models.user import User
from lightrag.api.sampai.models.classroom import Classroom, Folder, classroom_members
from lightrag.api.sampai.models.file import File, ProcessingStatus
from lightrag.api.sampai.models.chat import ChatMessage, MessageRole
from lightrag.api.sampai.models.quiz import Quiz, QuizAttempt, QuizStatus, QuizDifficulty
from lightrag.api.sampai.models.flashcard import (
    FlashcardDeck,
    Flashcard,
    FlashcardReview,
    FlashcardDeckStatus,
    FlashcardCardType,
)
from lightrag.api.sampai.models.mindmap import (
    Mindmap,
    MindmapNodeChat,
    MindmapStatus,
    MindmapMessageRole,
)
from lightrag.api.sampai.models.group_chat import (
    GroupChat,
    GroupChatMember,
    GroupChatInvite,
    GroupChatMessage,
    GroupRole,
    InviteStatus,
    GroupMessageRole,
)
from lightrag.api.sampai.models.announcement import Announcement, AnnouncementComment

__all__ = [
    "Base",
    "User",
    "Classroom",
    "Folder",
    "classroom_members",
    "File",
    "ProcessingStatus",
    "ChatMessage",
    "MessageRole",
    "Quiz",
    "QuizAttempt",
    "QuizStatus",
    "QuizDifficulty",
    "FlashcardDeck",
    "Flashcard",
    "FlashcardReview",
    "FlashcardDeckStatus",
    "FlashcardCardType",
    "Mindmap",
    "MindmapNodeChat",
    "MindmapStatus",
    "MindmapMessageRole",
    "GroupChat",
    "GroupChatMember",
    "GroupChatInvite",
    "GroupChatMessage",
    "GroupRole",
    "InviteStatus",
    "GroupMessageRole",
    "Announcement",
    "AnnouncementComment",
]
