"""Safe incremental update:
- add external_id to attendances (preserve existing id values)
- add performance_score, last_sync to users
- add last_login to admins
- convert call_history.timestamp (BigInt ms) -> DateTime (UTC)
- add indexes if missing

Revision ID: safe_inc_update
Revises: <your_previous_revision_here>
Create Date: 2025-11-18
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text
from sqlalchemy.engine.reflection import Inspector

# revision identifiers, used by Alembic.
revision = 'safe_inc_update'
down_revision = None  # set this to your latest migration id (e.g. 'abcd1234')
branch_labels = None
depends_on = None


def has_table(inspector: Inspector, name: str) -> bool:
    return name in inspector.get_table_names()


def has_column(inspector: Inspector, table_name: str, column_name: str) -> bool:
    cols = [c['name'] for c in inspector.get_columns(table_name)]
    return column_name in cols


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    dialect = bind.dialect.name.lower()

    # ---------------------------
    # 1) USERS: add performance_score, last_sync
    # ---------------------------
    if has_table(inspector, 'users'):
        if not has_column(inspector, 'users', 'performance_score'):
            op.add_column('users', sa.Column('performance_score', sa.Float(), nullable=True, server_default='0'))
        if not has_column(inspector, 'users', 'last_sync'):
            op.add_column('users', sa.Column('last_sync', sa.DateTime(), nullable=True))
        # index on email if not exists
        try:
            op.create_index('ix_users_email', 'users', ['email'])
        except Exception:
            # index may already exist or dialect-specific; ignore
            pass

    # ---------------------------
    # 2) ADMINS: add last_login
    # ---------------------------
    if has_table(inspector, 'admins'):
        if not has_column(inspector, 'admins', 'last_login'):
            op.add_column('admins', sa.Column('last_login', sa.DateTime(), nullable=True))
        # index on email
        try:
            op.create_index('ix_admins_email', 'admins', ['email'])
        except Exception:
            pass

    # ---------------------------
    # 3) ATTENDANCES: add external_id (preserve existing id values)
    # ---------------------------
    if has_table(inspector, 'attendances'):
        # If 'external_id' missing -> add it
        if not has_column(inspector, 'attendances', 'external_id'):
            op.add_column('attendances', sa.Column('external_id', sa.String(64), nullable=True, index=True))
            # try to copy existing id into external_id if id is text-like
            cols = inspector.get_columns('attendances')
            id_col = next((c for c in cols if c['name'] == 'id'), None)
            try:
                if id_col and (isinstance(id_col.get('type'), sa.String) or 'CHAR' in str(id_col.get('type')).upper()):
                    # copy id -> external_id
                    if dialect.startswith('sqlite'):
                        op.execute("UPDATE attendances SET external_id = id WHERE external_id IS NULL;")
                    elif dialect.startswith('postgres'):
                        op.execute("UPDATE attendances SET external_id = id WHERE external_id IS NULL;")
                    elif dialect.startswith('mysql'):
                        op.execute("UPDATE attendances SET external_id = id WHERE external_id IS NULL;")
            except Exception:
                # non-critical; skip copy on failure
                pass

        # ensure index on user_id
        try:
            op.create_index('ix_attendances_user_id', 'attendances', ['user_id'])
        except Exception:
            pass

    # ---------------------------
    # 4) CALL_HISTORY: convert timestamp BigInt(ms) -> DateTime
    # ---------------------------
    if has_table(inspector, 'call_history'):
        cols = inspector.get_columns('call_history')
        col_names = [c['name'] for c in cols]
        # if timestamp exists and is integer-like -> convert
        if 'timestamp' in col_names:
            # We will create 'timestamp_dt', populate it, drop old 'timestamp', then rename
            if not has_column(inspector, 'call_history', 'timestamp_dt'):
                op.add_column('call_history', sa.Column('timestamp_dt', sa.DateTime(), nullable=True))

                # populate timestamp_dt depending on dialect
                try:
                    if dialect.startswith('sqlite'):
                        # SQLite: timestamp in ms -> seconds: timestamp/1000
                        op.execute("""
                            UPDATE call_history
                            SET timestamp_dt = datetime(timestamp / 1000, 'unixepoch')
                            WHERE timestamp IS NOT NULL;
                        """)
                    elif dialect.startswith('postgres'):
                        # Postgres: to_timestamp(ms/1000)
                        op.execute("""
                            UPDATE call_history
                            SET timestamp_dt = to_timestamp(timestamp::double precision / 1000.0)
                            WHERE timestamp IS NOT NULL;
                        """)
                    elif dialect.startswith('mysql'):
                        # MySQL: FROM_UNIXTIME(timestamp_ms/1000)
                        op.execute("""
                            UPDATE call_history
                            SET timestamp_dt = FROM_UNIXTIME(timestamp / 1000)
                            WHERE timestamp IS NOT NULL;
                        """)
                    else:
                        # Generic SQL fallback (attempt using unix epoch seconds)
                        op.execute("""
                            UPDATE call_history
                            SET timestamp_dt = datetime(timestamp / 1000, 'unixepoch')
                            WHERE timestamp IS NOT NULL;
                        """)
                except Exception:
                    # If conversion fails, we will leave timestamp_dt NULL for those rows
                    pass

                # Drop old integer column and rename
                try:
                    op.drop_column('call_history', 'timestamp')
                except Exception:
                    # Some dialects (SQLite) may not support drop_column; in that case, leave both columns
                    pass

                try:
                    # Rename column if drop succeeded or target name free
                    op.alter_column('call_history', 'timestamp_dt', new_column_name='timestamp')
                except Exception:
                    # If rename fails (SQLite), leave timestamp_dt as-is.
                    pass

        # indexes
        try:
            op.create_index('ix_call_history_user_id', 'call_history', ['user_id'])
        except Exception:
            pass
        try:
            op.create_index('ix_call_history_timestamp', 'call_history', ['timestamp'])
        except Exception:
            pass
        try:
            op.create_index('ix_call_history_number', 'call_history', ['number'])
        except Exception:
            pass

    # ---------------------------
    # 5) ACTIVITY LOGS: index actor_id
    # ---------------------------
    if has_table(inspector, 'activity_logs'):
        try:
            op.create_index('ix_activity_logs_actor_id', 'activity_logs', ['actor_id'])
        except Exception:
            pass


def downgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    dialect = bind.dialect.name.lower()

    # Reverse indexes & added columns where safe

    # 1) activity_logs index
    if has_table(inspector, 'activity_logs'):
        try:
            op.drop_index('ix_activity_logs_actor_id', table_name='activity_logs')
        except Exception:
            pass

    # 2) call_history indexes & rename timestamp back if possible
    if has_table(inspector, 'call_history'):
        try:
            op.drop_index('ix_call_history_number', table_name='call_history')
        except Exception:
            pass
        try:
            op.drop_index('ix_call_history_timestamp', table_name='call_history')
        except Exception:
            pass
        try:
            op.drop_index('ix_call_history_user_id', table_name='call_history')
        except Exception:
            pass

        # If we have both timestamp (DateTime) and want to revert to bigint, attempt safe conversion
        try:
            cols = inspector.get_columns('call_history')
            names = [c['name'] for c in cols]
            if 'timestamp' in names and 'timestamp_old' not in names:
                # create backup bigint column
                op.add_column('call_history', sa.Column('timestamp_old', sa.BigInteger(), nullable=True))
                try:
                    if dialect.startswith('sqlite'):
                        op.execute("UPDATE call_history SET timestamp_old = CAST(strftime('%s', timestamp) AS INTEGER) * 1000 WHERE timestamp IS NOT NULL;")
                    elif dialect.startswith('postgres'):
                        op.execute("UPDATE call_history SET timestamp_old = (extract(epoch from timestamp)::bigint * 1000) WHERE timestamp IS NOT NULL;")
                    elif dialect.startswith('mysql'):
                        op.execute("UPDATE call_history SET timestamp_old = UNIX_TIMESTAMP(timestamp) * 1000 WHERE timestamp IS NOT NULL;")
                except Exception:
                    pass
                # drop datetime column
                try:
                    op.drop_column('call_history', 'timestamp')
                except Exception:
                    pass
                # rename timestamp_old -> timestamp
                try:
                    op.alter_column('call_history', 'timestamp_old', new_column_name='timestamp')
                except Exception:
                    pass
        except Exception:
            pass

    # 3) attendances: drop external_id if exists
    if has_table(inspector, 'attendances'):
        try:
            if has_column(inspector, 'attendances', 'external_id'):
                op.drop_column('attendances', 'external_id')
        except Exception:
            pass
        try:
            op.drop_index('ix_attendances_user_id', table_name='attendances')
        except Exception:
            pass

    # 4) admins: drop last_login
    if has_table(inspector, 'admins'):
        try:
            if has_column(inspector, 'admins', 'last_login'):
                op.drop_column('admins', 'last_login')
        except Exception:
            pass
        try:
            op.drop_index('ix_admins_email', table_name='admins')
        except Exception:
            pass

    # 5) users: drop performance_score and last_sync
    if has_table(inspector, 'users'):
        try:
            if has_column(inspector, 'users', 'performance_score'):
                op.drop_column('users', 'performance_score')
        except Exception:
            pass
        try:
            if has_column(inspector, 'users', 'last_sync'):
                op.drop_column('users', 'last_sync')
        except Exception:
            pass
        try:
            op.drop_index('ix_users_email', table_name='users')
        except Exception:
            pass
        try:
            op.drop_index('ix_users_admin_id', table_name='users')
        except Exception:
            pass
