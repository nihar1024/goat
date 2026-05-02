"""add field_config to layer

Revision ID: f3f8f8565361
Revises: ccb2a3c570b2
Create Date: 2026-05-01 19:35:11.788199

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "f3f8f8565361"
down_revision: Union[str, None] = "ccb2a3c570b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "layer",
        sa.Column(
            "field_config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        schema="customer",
    )


def downgrade() -> None:
    op.drop_column("layer", "field_config", schema="customer")
