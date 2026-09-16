"""Tests must never touch a real database. Point the engine at in-memory sqlite
before any spam_bot module imports core.config (load_dotenv won't override an
env var that's already set). This file is auto-loaded by pytest before test
modules, so the Postgres driver (psycopg2) is never needed to run the suite.
"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite://")
