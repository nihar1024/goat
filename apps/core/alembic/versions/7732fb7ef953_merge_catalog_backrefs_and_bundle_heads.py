"""merge catalog backrefs and bundle heads

Revision ID: 7732fb7ef953
Revises: a1c4b2d9e001, e7b3c9a15d42
Create Date: 2026-08-24 12:10:59.693925

"""
from alembic import op
import sqlalchemy as sa
import geoalchemy2
import sqlmodel  



# revision identifiers, used by Alembic.
revision = '7732fb7ef953'
down_revision = ('a1c4b2d9e001', 'e7b3c9a15d42')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
