"""merge custom_basemaps and document_asset branches

Revision ID: d1e2f3a4b5c6
Revises: c4d5e6f7a8b2, f3f8f8565361
Create Date: 2026-05-02 12:00:00.000000

"""

from typing import Sequence, Union

revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, tuple] = ("c4d5e6f7a8b2", "f3f8f8565361")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
