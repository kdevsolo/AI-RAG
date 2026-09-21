from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import config

engine = create_engine(
    config.database_url,
    # logs each executed sql stmt if set true
    echo=False,
    # before handing out connection check if its alive if not creates a fresh connection to db
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
