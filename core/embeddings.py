import os
import numpy as np
from openai import AzureOpenAI
from dotenv import load_dotenv
from langchain.embeddings.base import Embeddings

# Load environment variables
load_dotenv()

AZURE_EMBEDDING_ENDPOINT = os.getenv("AZURE_EMBEDDING_ENDPOINT")
AZURE_EMBEDDING_API_VERSION = os.getenv("AZURE_EMBEDDING_API_VERSION", "2023-05-15")
AZURE_EMBEDDING_KEY = os.getenv("AZURE_EMBEDDING_KEY")
DEPLOYMENT_NAME = os.getenv(
    "AZURE_OPENAI_CHAT_DEPLOYMENT_NAME", "text-embedding-3-large"
)

embedding_client = AzureOpenAI(
    azure_endpoint=AZURE_EMBEDDING_ENDPOINT,
    api_version=AZURE_EMBEDDING_API_VERSION,
    api_key=AZURE_EMBEDDING_KEY,
)


def compute_embedding(text: str) -> bytes:
    """Compute embedding for text using Azure OpenAI and return as bytes."""
    try:
        if len(text) > 8000:
            text = text[:8000]
        response = embedding_client.embeddings.create(
            input=[text],
            model=DEPLOYMENT_NAME,
        )
        embedding = response.data[0].embedding
        return np.array(embedding, dtype=np.float32).tobytes()
    except Exception as e:
        raise RuntimeError(f"Embedding failed: {e}")


class AzureEmbeddings(Embeddings):
    """LangChain-compatible embedding class for Azure OpenAI."""

    def __init__(self, deployment_name: str = None):
        self.deployment_name = deployment_name or DEPLOYMENT_NAME
        self.client = embedding_client

    def embed_documents(self, texts):
        results = self.client.embeddings.create(
            input=texts,
            model=self.deployment_name,
        )
        return [np.array(obj.embedding, dtype=np.float32) for obj in results.data]

    def embed_query(self, text):
        return self.embed_documents([text])[0]
