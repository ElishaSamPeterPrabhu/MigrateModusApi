from sqlalchemy import Column, Integer, String, Text, LargeBinary, JSON
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class ContextUnit(Base):
    __tablename__ = "context_units"
    id = Column(Integer, primary_key=True)
    type = Column(
        String(50), nullable=False
    )  # e.g., 'v1_component', 'migration_rule', etc.
    name = Column(String(100), nullable=True)  # e.g., component name
    content = Column(Text, nullable=False)
    embedding = Column(
        LargeBinary, nullable=True
    )  # Store as bytes (can use numpy to/from bytes)
    meta = Column(JSON, nullable=True)
