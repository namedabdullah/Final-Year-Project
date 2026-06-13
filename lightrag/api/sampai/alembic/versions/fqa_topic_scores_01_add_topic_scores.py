"""add topic_scores to folder_quiz_attempts

Revision ID: fqa_topic_scores_01
Revises: 0815bd3b7812
Create Date: 2026-06-11 19:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "fqa_topic_scores_01"
down_revision: Union[str, None] = "0815bd3b7812"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "folder_quiz_attempts",
        sa.Column("topic_scores", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("folder_quiz_attempts", "topic_scores")
