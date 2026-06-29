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
