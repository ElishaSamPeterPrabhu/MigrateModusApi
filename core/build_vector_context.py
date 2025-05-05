import os
import json
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from db.schema import ContextUnit
from langchain_community.vectorstores import FAISS
from langchain.schema import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter

from embeddings import AzureEmbeddings

# --- Config ---
DB_URL = "sqlite:///db/migration_context.db"
VECTOR_INDEX_PATH = "vector_index"
DEPLOYMENT_NAME = "text-embedding-3-large"


# --- Chunking Helper ---
def chunk_content(content, section_name, name):
    splitter = RecursiveCharacterTextSplitter(chunk_size=512, chunk_overlap=100)
    header = f"{section_name.upper()} - {name}"
    content_str = f"{header}:\n{content}"
    return [
        {
            "content": chunk,
            "metadata": {"source": f"{section_name}:{name}"},
        }
        for chunk in splitter.split_text(content_str)
    ]


# --- Main Build Function ---
def build_vector_index():
    # 1. Connect to DB and fetch v1/v2 components
    engine = create_engine(DB_URL)
    Session = sessionmaker(bind=engine)
    session = Session()
    v1_units = session.query(ContextUnit).filter(
        ContextUnit.type.in_(["v1_component", "v1_components"])
    )
    v2_units = session.query(ContextUnit).filter(
        ContextUnit.type.in_(["v2_component", "v2_components"])
    )
    docs = []
    for unit in v1_units:
        docs.extend(chunk_content(unit.content, "v1_component", unit.name))
    for unit in v2_units:
        docs.extend(chunk_content(unit.content, "v2_component", unit.name))
    print(f"Indexed {len(docs)} chunks from v1/v2 components.")

    print(f"Total chunks: {len(docs)}")

    # 2. Build and save FAISS vector index using custom embedding function
    texts = [d["content"] for d in docs]
    metadatas = [d["metadata"] for d in docs]
    documents = [Document(page_content=t, metadata=m) for t, m in zip(texts, metadatas)]

    embeddings = AzureEmbeddings(deployment_name=DEPLOYMENT_NAME)
    db = FAISS.from_documents(documents, embedding=embeddings)
    db.save_local(VECTOR_INDEX_PATH)
    print(f"✅ Vector DB saved at '{VECTOR_INDEX_PATH}' with {len(docs)} chunks.")


if __name__ == "__main__":
    build_vector_index()
