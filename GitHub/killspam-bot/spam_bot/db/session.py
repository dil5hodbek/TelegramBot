from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from ..core.config import DATABASE_URL

_url = DATABASE_URL or ""
if _url.startswith("postgres://"):  # Railway/Heroku style; SQLAlchemy needs postgresql://
    _url = "postgresql://" + _url[len("postgres://"):]
# SSL for genuinely remote hosts; skip sqlite (no SSL), localhost, and Railway's
# private network.
_local = _url.startswith("sqlite") or any(
    h in _url for h in ("localhost", "127.0.0.1", ".railway.internal"))
engine = create_engine(_url, connect_args={} if _local else {"sslmode": "require"})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()