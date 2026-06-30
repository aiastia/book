"""数据库连接和会话管理"""

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    connect_args={"timeout": 30} if settings.DATABASE_URL.startswith("sqlite") else {},
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
    """初始化数据库：创建表 + 自动补列（SQLite 兜底）。"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # 自动补列：确保已有表的列和模型一致（SQLite 不支持完整 migration，这里做兜底）
        if settings.DATABASE_URL.startswith("sqlite"):
            await conn.run_sync(_auto_add_missing_columns)


def _auto_add_missing_columns(connection):
    """检测已有表是否缺少模型定义的列，缺少则 ALTER TABLE ADD COLUMN。

    兼容 SQLite 和 PostgreSQL 方言。非完整 migration（不处理列改名/删除）。
    """
    from sqlalchemy import inspect, text

    dialect = connection.dialect.name
    inspector = inspect(connection)
    for table_name, table_obj in Base.metadata.tables.items():
        if not inspector.has_table(table_name):
            continue
        existing_cols = {col["name"] for col in inspector.get_columns(table_name)}
        for col in table_obj.columns:
            if col.name not in existing_cols:
                col_type = col.type.compile(connection.dialect)
                nullable = "" if col.nullable else " NOT NULL"
                default_clause = ""
                if col.server_default is not None:
                    default_clause = f" DEFAULT {col.server_default.arg}"
                elif not col.nullable:
                    # 为 NOT NULL 列提供一个安全的默认值
                    default_clause = _safe_default_for(col.type)
                # PostgreSQL 支持 IF NOT EXISTS，SQLite 不支持但会忽略未知 SQL 关键字吗？不，
                # SQLite < 3.24 不支持 IF NOT EXISTS。但对已有列会报错，所以只在 PG 时加。
                if_not_exists = " IF NOT EXISTS" if dialect == "postgresql" else ""
                sql = (
                    f"ALTER TABLE {table_name}"
                    f" ADD COLUMN{if_not_exists} {col.name} {col_type}{nullable}{default_clause}"
                )
                try:
                    connection.execute(text(sql))
                    print(f"[DB] 自动补列：{table_name}.{col.name} ({col_type})")
                except Exception as e:
                    print(f"[DB] 补列失败 {table_name}.{col.name}: {e}")


def _safe_default_for(col_type) -> str:
    """根据列类型返回一个安全的默认值，避免 PostgreSQL 的类型转换错误。"""
    type_name = str(col_type).upper()
    if any(t in type_name for t in ("INTEGER", "BIGINT", "SMALLINT", "FLOAT", "REAL", "NUMERIC", "BOOLEAN")):
        return " DEFAULT 0"
    if any(t in type_name for t in ("DATE", "TIME", "TIMESTAMP")):
        return " DEFAULT '1970-01-01'"
    return " DEFAULT ''"
