"""simplify reservation flow: drop max_concurrent_guests; split reservation enums

Revision ID: e1f5a7b2c8d3
Revises: c4d3e2b1a0f9
Create Date: 2026-05-19 13:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'e1f5a7b2c8d3'
down_revision: Union[str, Sequence[str], None] = 'c4d3e2b1a0f9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# SQLAlchemy serializes Python `Enum` subclasses by NAME (e.g. ACTIVE), not by
# str value, so the Postgres enum labels are uppercase to match what the ORM
# emits at INSERT time.
def upgrade() -> None:
    """
    Splits the old `reservationstatus` Postgres enum into two:

    * `tablereservationstatus`   — old values `ACTIVE/HONORED/CANCELLED/NO_SHOW`,
                                   still used by `table_reservation.status`.
    * `reservationstatus` (new)  — request lifecycle
                                   `WAITING/ACCEPTED/REFUSED/CANCELED`,
                                   used by `reservation.status`.

    Existing `reservation.status` values are remapped:
      ACTIVE|HONORED    → ACCEPTED
      CANCELLED|NO_SHOW → CANCELED
    """
    op.drop_column('restaurant', 'max_concurrent_guests')

    op.execute("ALTER TYPE reservationstatus RENAME TO tablereservationstatus")
    op.execute(
        "CREATE TYPE reservationstatus AS ENUM "
        "('WAITING', 'ACCEPTED', 'REFUSED', 'CANCELED')"
    )

    op.execute("ALTER TABLE reservation ALTER COLUMN status DROP DEFAULT")
    op.execute(
        "ALTER TABLE reservation ALTER COLUMN status TYPE reservationstatus "
        "USING (CASE status::text "
        "WHEN 'ACTIVE'    THEN 'ACCEPTED'::reservationstatus "
        "WHEN 'HONORED'   THEN 'ACCEPTED'::reservationstatus "
        "WHEN 'CANCELLED' THEN 'CANCELED'::reservationstatus "
        "WHEN 'NO_SHOW'   THEN 'CANCELED'::reservationstatus "
        "ELSE 'WAITING'::reservationstatus END)"
    )


def downgrade() -> None:
    """
    Best-effort inverse. Status remapping is lossy in both directions; we
    pick a representative for each new value.
    """
    op.execute("ALTER TABLE reservation ALTER COLUMN status DROP DEFAULT")
    op.execute(
        "ALTER TABLE reservation ALTER COLUMN status TYPE tablereservationstatus "
        "USING (CASE status::text "
        "WHEN 'WAITING'  THEN 'ACTIVE'::tablereservationstatus "
        "WHEN 'ACCEPTED' THEN 'ACTIVE'::tablereservationstatus "
        "WHEN 'REFUSED'  THEN 'CANCELLED'::tablereservationstatus "
        "WHEN 'CANCELED' THEN 'CANCELLED'::tablereservationstatus "
        "ELSE 'ACTIVE'::tablereservationstatus END)"
    )
    op.execute("DROP TYPE reservationstatus")
    op.execute("ALTER TYPE tablereservationstatus RENAME TO reservationstatus")
    op.add_column(
        'restaurant',
        sa.Column('max_concurrent_guests', sa.Integer(), nullable=True),
    )
