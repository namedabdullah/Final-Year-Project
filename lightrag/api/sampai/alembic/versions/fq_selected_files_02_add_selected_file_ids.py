"""add selected_file_ids to folder_quizzes

Revision ID: fq_selected_files_02
Revises: fqa_topic_scores_01
Create Date: 2026-06-12 10:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "fq_selected_files_02"
down_revision: Union[str, None] = "fqa_topic_scores_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "folder_quizzes",
        sa.Column("selected_file_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("folder_quizzes", "selected_file_ids")
