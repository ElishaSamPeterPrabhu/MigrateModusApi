from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ValidationError
import json
import tiktoken

from core.vector_retrieval import (
    retrieve_context,
    retrieve_context_by_section,
    migrate_with_llm,
)

STATE_FILE = "data/workflow_state.json"
if not Path(STATE_FILE).exists():
    raise FileNotFoundError(f"State file not found: {STATE_FILE}")

with open(STATE_FILE, encoding="utf-8") as sf:
    MIGRATION_STATE = json.load(sf)

app = FastAPI(title="Modus Vector Retrieval API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RetrieveRequest(BaseModel):
    query: str
    k: int = 5


class MigrateRequest(BaseModel):
    code: str


@app.exception_handler(ValidationError)
async def validation_exception_handler(request: Request, exc: ValidationError):
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "body": exc.body},
    )


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/retrieve_tokens")
async def retrieve_tokens(req: RetrieveRequest):
    context = retrieve_context(req.query, k=req.k)
    enc = tiktoken.encoding_for_model("text-davinci-003")
    input_tokens = len(enc.encode(context))
    return {"context": context, "input_tokens": input_tokens}


@app.post("/retrieve_by_section")
async def retrieve_by_section(req: RetrieveRequest):
    context = retrieve_context_by_section(
        req.query, k_search=30, k_pick=req.k, state=MIGRATION_STATE
    )
    enc = tiktoken.encoding_for_model("text-davinci-003")
    input_tokens = len(enc.encode(context))
    return {"context": context, "input_tokens": input_tokens}


@app.post("/migrate")
async def migrate(req: MigrateRequest):
    context = retrieve_context(req.code, k=20)
    enc = tiktoken.encoding_for_model("text-davinci-003")
    input_tokens = len(enc.encode(context))
    migrated = migrate_with_llm(req.code, context=context)
    output_tokens = len(enc.encode(migrated))
    return {
        "migrated_code": migrated,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }
