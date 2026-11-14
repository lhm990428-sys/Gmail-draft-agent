"""Encrypted documents, hash chained events, outbox and execution claims."""
from alembic import op
from mail_tools.app.store import metadata
revision="0001_runtime"
down_revision=None
branch_labels=None
depends_on=None


def upgrade():
    metadata.create_all(bind=op.get_bind(),checkfirst=True)


def downgrade():
    raise RuntimeError("Destructive downgrade is not supported; restore a verified encrypted backup")
