"""bundle_dependency: which revision of the dependency the artifacts were built from

A bundle's artifacts can be derived from another *bundle*, not only from its own
layers: a public-transport bundle's stop-to-street linkage is computed against
the street network bundle it depends on. `bundle_artifact.revision` records
which of the bundle's *own* layers an artifact came from, and readiness is
derived by comparing it with the bundle's current `layers_revision`. Nothing
recorded the equivalent across the dependency edge, so editing a street network
left every linkage built from it reporting `ready` while describing edges that
no longer exist, and nothing could detect it.

The fact belongs to the relationship, and this is the relationship table: the
row already says which bundle depends on which, for which kind. One integer
completes it — the dependency's `layers_revision` at the time the dependent's
artifacts were built.

Readiness stays derived, and the comparison is a join:

    d.built_revision IS DISTINCT FROM dep.layers_revision  ->  outdated

Null means linked but never built against — which is what a fresh link is, so
re-pointing a bundle at a different street network invalidates structurally
rather than by comparing identifiers. Recording the revision rather than the
dependency's artifact path is deliberate: a manual rebuild of unchanged layers
produces an equivalent graph and must not mark dependents stale, while an edit
must.

Revision ID: f6b2d84e1c47
Revises: e5a1c73f9b28
"""

import sqlalchemy as sa
from alembic import op

revision = "f6b2d84e1c47"
down_revision = "e5a1c73f9b28"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "bundle_dependency",
        sa.Column("built_revision", sa.Integer(), nullable=True),
        schema="customer",
    )


def downgrade() -> None:
    op.drop_column("bundle_dependency", "built_revision", schema="customer")
