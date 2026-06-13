"""seed SAMpai system user

Revision ID: b2c0seeduser01
Revises: f7b90dc364e3
Create Date: 2026-06-07
"""
from typing import Sequence, Union

import secrets

import sqlalchemy as sa
from alembic import op

from lightrag.api.sampai.constants import SAMPAI_USERNAME
from lightrag.api.sampai.security import hash_password

revision: str = "b2c0seeduser01"
down_revision: Union[str, None] = "f7b90dc364e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SYSTEM_EMAIL = "sampai@system.local"


def upgrade() -> None:
    bind = op.get_bind()
    exists = bind.execute(
        sa.text("SELECT 1 FROM users WHERE is_system = true LIMIT 1")
    ).first()
    if exists:
        return
    # The system agent never logs in — give it an unguessable random password hash.
    bind.execute(
        sa.text(
            "INSERT INTO users (username, email, hashed_password, is_system) "
            "VALUES (:u, :e, :p, true)"
        ),
        {
            "u": SAMPAI_USERNAME,
            "e": _SYSTEM_EMAIL,
            "p": hash_password(secrets.token_urlsafe(32)),
        },
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("DELETE FROM users WHERE is_system = true"))
