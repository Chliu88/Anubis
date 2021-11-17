"""ADD beta_ui_enabled to course

Revision ID: 99e32b8689c9
Revises: 22b0d9fdb52f
Create Date: 2021-11-09 19:36:03.097041

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "99e32b8689c9"
down_revision = "22b0d9fdb52f"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column(
        "course", sa.Column("beta_ui_enabled", sa.Boolean(), nullable=True)
    )
    conn = op.get_bind()
    with conn.begin():
        conn.execute('update course set beta_ui_enabled = 0;')
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column("course", "beta_ui_enabled")
    # ### end Alembic commands ###