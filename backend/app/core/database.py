"""数据库连接和会话管理"""

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    connect_args={"timeout": 30},  # SQLite busy_timeout：写锁冲突时等待最多30秒
)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# SQLite 并发优化：开启 WAL 模式（允许读写并发），解决后台任务更新进度时的 database is locked
@event.listens_for(engine.sync_engine, "connect")
def _set_sqlite_pragma(dbapi_conn, connection_record):
    if settings.DATABASE_URL.startswith("sqlite"):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")      # WAL：读写并发，写不阻塞读
        cursor.execute("PRAGMA busy_timeout=30000")    # 写锁冲突等待30秒
        cursor.execute("PRAGMA synchronous=NORMAL")    # WAL 下 NORMAL 足够安全且更快
        cursor.close()


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # 自动补列：确保已有表的列和模型一致（SQLite 不支持完整 migration，这里做兜底）
        if settings.DATABASE_URL.startswith("sqlite"):
            await conn.run_sync(_auto_add_missing_columns)


def _auto_add_missing_columns(connection):
    """检测已有表是否缺少模型定义的列，缺少则 ALTER TABLE ADD COLUMN。

    这不是完整的 migration（不处理列改名/删除），只做加列兜底，
    确保新增的 Column（如 is_hidden）不会导致查询崩溃。
    """
    from sqlalchemy import inspect, text

    inspector = inspect(connection)
    for table_name, table_obj in Base.metadata.tables.items():
        if not inspector.has_table(table_name):
            continue
        existing_cols = {col["name"] for col in inspector.get_columns(table_name)}
        for col in table_obj.columns:
            if col.name not in existing_cols:
                # 构造 ALTER TABLE ADD COLUMN
                col_type = col.type.compile(connection.dialect)
                nullable = "" if col.nullable else " NOT NULL"
                default = ""
                if col.server_default is not None:
                    default = f" DEFAULT {col.server_default.arg}"
                elif not col.nullable:
                    # NOT NULL 列需要默认值，否则旧行会报错
                    default = " DEFAULT ''"
                sql = f"ALTER TABLE {table_name} ADD COLUMN {col.name} {col_type}{nullable}{default}"
                try:
                    connection.execute(text(sql))
                    print(f"[DB] 自动补列：{table_name}.{col.name} ({col_type})")
                except Exception as e:
                    print(f"[DB] 补列失败 {table_name}.{col.name}: {e}")
