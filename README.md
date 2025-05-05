# MigrateModusApi

A toolkit and API for migrating and managing Modus Web Components using vector search and LLMs.

## Setup Instructions

### 1. Clone the repository
```sh
git clone <your-repo-url>
cd MigrateModusApi
```

### 2. Create and activate a virtual environment (recommended)
```sh
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

### 3. Install dependencies
```sh
pip install -r requirements.txt
```

### 4. Set up environment variables
Create a `.env` file in the project root with your Azure OpenAI credentials:
```
AZURE_OPENAI_API_KEY=""
AZURE_OPENAI_ENDPOINT=""
AZURE_OPENAI_CHAT_DEPLOYMENT_NAME=""
AZURE_OPENAI_API_VERSION=""
AZURE_EMBEDDING_KEY=""
AZURE_EMBEDDING_ENDPOINT=""
AZURE_EMBEDDING_API_VERSION=""
```

### 5. Ingest repositories and build the vector index
```sh
python main.py --full-ingest
```
This will clone the required repos, analyze them, ingest context, and build the vector index.

### 6. Run the API server
```sh
uvicorn api.vector_api:app --reload
```

### 7. Query the API
Use the `/retrieve_tokens`, `/retrieve_by_section`, or `/migrate` endpoints to interact with the vector search and migration logic.

## Notes
- The following folders/files are **excluded from version control** (see `.gitignore`):
  - `repos/` (cloned repositories)
  - `vector_index/` (vector database)
  - `db/migration_context.db` (main SQLite DB)
  - `data/`, `context/`, `cache/`, `__pycache__/`, etc.
- You may need to re-run `--full-ingest` if you update the source repos or context.

## Project Structure
- `main.py` — CLI entrypoint for ingestion and workflow
- `api/vector_api.py` — FastAPI server for vector retrieval and migration
- `core/vector_retrieval.py` — Core logic for context retrieval and migration
- `core/build_vector_context.py` — Builds the FAISS vector index
- `core/embeddings.py` — Embedding logic for Azure OpenAI
- `ingest/`, `db/`, `workflow/`, etc. — Supporting modules and data

---
For more details, see the code and comments in each file.

## Features
- Database-backed context storage for scalable, granular, and updatable migration knowledge.
- Semantic search for retrieving the most relevant migration context for any code.
- LangGraph workflow for flexible, modular migration pipelines.
- API and CLI for running migrations and testing code. 