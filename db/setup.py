from sqlalchemy import create_engine
from .schema import Base
import os

# Create the db directory if it doesn't exist
os.makedirs("db", exist_ok=True)

# Use the same path as in ingest_context.py
engine = create_engine("sqlite:///db/migration_context.db")
Base.metadata.create_all(engine)
print("Database initialized.")
