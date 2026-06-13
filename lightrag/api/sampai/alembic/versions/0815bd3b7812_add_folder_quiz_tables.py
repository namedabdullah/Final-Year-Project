"""add_folder_quiz_tables

Revision ID: 0815bd3b7812
Revises: b2c0seeduser01
Create Date: 2026-06-11 17:55:01.622733
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0815bd3b7812'
down_revision: Union[str, None] = 'b2c0seeduser01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Use raw SQL to reuse the existing quizstatus/quizdifficulty PG enum types
    # (Alembic autogenerate always re-emits CREATE TYPE, which fails on the second
    # table that shares the same type — raw SQL references the type by name instead).
    op.execute("""
        CREATE TABLE folder_quizzes (
            id                SERIAL PRIMARY KEY,
            folder_id         INTEGER NOT NULL
                              REFERENCES folders(id) ON DELETE CASCADE,
            user_id           INTEGER NOT NULL
                              REFERENCES users(id) ON DELETE CASCADE,
            status            quizstatus NOT NULL DEFAULT 'pending',
            difficulty        quizdifficulty NOT NULL,
            difficulty_source VARCHAR(20) NOT NULL,
            num_questions     INTEGER NOT NULL
                              CONSTRAINT fq_num_questions CHECK (num_questions IN (10, 20, 30)),
            questions         JSONB,
            generation_meta   JSONB,
            error_msg         TEXT,
            created_at        TIMESTAMP NOT NULL DEFAULT now(),
            ready_at          TIMESTAMP
        )
    """)
    op.execute("CREATE INDEX ix_fq_status ON folder_quizzes (status)")
    op.execute("CREATE INDEX ix_fq_user_folder ON folder_quizzes (user_id, folder_id)")

    op.execute("""
        CREATE TABLE folder_quiz_attempts (
            id            SERIAL PRIMARY KEY,
            quiz_id       INTEGER NOT NULL UNIQUE
                          REFERENCES folder_quizzes(id) ON DELETE CASCADE,
            user_id       INTEGER NOT NULL
                          REFERENCES users(id) ON DELETE CASCADE,
            folder_id     INTEGER NOT NULL
                          REFERENCES folders(id) ON DELETE CASCADE,
            score         FLOAT,
            correct_count INTEGER,
            total_count   INTEGER NOT NULL,
            answers       JSONB NOT NULL,
            submitted_at  TIMESTAMP NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX ix_fqa_user_folder ON folder_quiz_attempts (user_id, folder_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_fqa_user_folder")
    op.drop_table('folder_quiz_attempts')
    op.execute("DROP INDEX IF EXISTS ix_fq_user_folder")
    op.execute("DROP INDEX IF EXISTS ix_fq_status")
    op.drop_table('folder_quizzes')
