"""ADD webtop column

Revision ID: 8c17dcffa2be
Revises: 400b53e79568
Create Date: 2022-02-25 16:45:29.471545

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "8c17dcffa2be"
down_revision = "400b53e79568"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column(
        "theia_image", sa.Column("webtop", sa.Boolean(), nullable=True)
    )
    conn = op.get_bind()
    conn.execute('update theia_image set webtop = 0;')
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column("theia_image", "webtop")
    # ### end Alembic commands ###