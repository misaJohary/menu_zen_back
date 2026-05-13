"""add restaurant location

Revision ID: 7160a8a79a36
Revises: 7e07858422ed
Create Date: 2026-05-11 11:58:31.336018

"""
from typing import Sequence, Union

import geoalchemy2
import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = '7160a8a79a36'
down_revision: Union[str, Sequence[str], None] = '7e07858422ed'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'restaurant',
        sa.Column(
            'location',
            geoalchemy2.types.Geography(
                geometry_type='POINT',
                srid=4326,
                from_text='ST_GeogFromText',
                name='geography',
            ),
            nullable=True,
        ),
    )

    # Backfill location from existing lat/long columns.
    # GeoAlchemy2 creates the GIST index `idx_restaurant_location` automatically
    # when the Geography column is added, so no explicit create_index is needed.
    op.execute(
        """
        UPDATE restaurant
           SET location = ST_SetSRID(ST_MakePoint(long, lat), 4326)::geography
         WHERE lat IS NOT NULL AND long IS NOT NULL
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    # GeoAlchemy2's drop_column removes the auto-created spatial index.
    op.drop_column('restaurant', 'location')
