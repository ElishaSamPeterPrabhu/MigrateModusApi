import os
import json
import re
from langchain_community.vectorstores import FAISS
from langchain_openai import AzureChatOpenAI
import tiktoken
from embeddings import AzureEmbeddings

# --- Config ---
VECTOR_INDEX_PATH = "vector_index"
DEPLOYMENT_NAME = "text-embedding-3-large"
STATE_FILE = "data/workflow_state.json"

# Load migration state from JSON

chat_llm = AzureChatOpenAI(
    azure_endpoint=os.environ.get("AZURE_OPENAI_ENDPOINT"),
    azure_deployment=os.environ.get("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME"),
    openai_api_version=os.environ.get("AZURE_OPENAI_API_VERSION"),
    openai_api_key=os.environ.get("AZURE_OPENAI_API_KEY"),
)


def load_vector_index():
    """Load the FAISS vector index from disk."""
    embeddings = AzureEmbeddings(deployment_name=DEPLOYMENT_NAME)
    return FAISS.load_local(
        VECTOR_INDEX_PATH, embeddings, allow_dangerous_deserialization=True
    )


def retrieve_context(code: str, k: int = 20) -> str:
    """
    Retrieve relevant context chunks for the given code using vector search.
    Returns a concatenated string of the top-k relevant chunks.
    """
    db = load_vector_index()
    results = db.similarity_search(code, k=k)
    return "\n\n".join([doc.page_content for doc in results])


def retrieve_context_by_section(
    code: str, k_search: int = 30, k_pick: int = 10, state: dict = None
) -> str:
    """
    Retrieve context by section (v1_component, v2_component, etc.) for the given code.
    Returns a formatted string with context blocks per section.
    """
    db = load_vector_index()
    all_results = db.similarity_search(code, k=k_search)
    # Extract every <modus-...> tag
    raw_tags = re.findall(r"<(modus(?:-wc)?-[a-z-]+)", code)
    tags = list(dict.fromkeys(raw_tags))
    mapping = state.get("Mapping_v1_v2", {}) if state else {}
    section_hits = {"v1_component": [], "v2_component": []}
    for tag in tags:
        v1_key = f"{tag}.tsx"
        v2_file = mapping.get(v1_key)
        # V2
        if v2_file and v2_file != "Not Found":
            source_key = f"v2_component:{v2_file}"
            exact_hits = [
                doc for doc in all_results if doc.metadata["source"] == source_key
            ]
            if not exact_hits:
                full = db.similarity_search("", k=1000)
                exact_hits = [d for d in full if d.metadata["source"] == source_key]
            if exact_hits:
                picks = exact_hits[:k_pick]
                section_hits["v2_component"].extend(d.page_content for d in picks)
        # V1
        v1_source = f"v1_component:{v1_key}"
        v1_hits = [d for d in all_results if d.metadata["source"] == v1_source]
        if v1_hits:
            section_hits["v1_component"].extend(
                d.page_content for d in v1_hits[:k_pick]
            )
    # Combine into blocks
    combined = []
    for section in ["v1_component", "v2_component"]:
        header = section.upper().replace("_", " ")
        snippets = section_hits[section] or ["<no content>"]
        combined.append(f"### {header}\n" + "\n\n".join(snippets))
    return "\n\n".join(combined)


def migrate_with_llm(code: str, context: str = None, state: dict = None) -> str:
    """
    Migrate code using the LLM, given the code, context, and migration state.
    Returns the migrated code as a string.
    """
    state = state or {}
    print("state available:", state)
    mapping_json = json.dumps(state["Mapping_v1_v2"], indent=2)
    verification_rules = json.dumps(state["verification_rules"], indent=2)
    migration_plan = json.dumps(state["migration_plan"], indent=2)
    prompt = f"""
    You have a mapping of old Modus 1.0 component filenames to new Modus 2.0 filenames:

    Mapping of V1 components to V2 components:
    {mapping_json}

    Use this mapping *exactly*—do not invent or alter component names.

    Use the following migration context:
    -------------------------
    {context}
    -------------------------
    Original Code:
    -------------------------
    {code}
    -------------------------
    Migration Plan:
    -------------------------
    {migration_plan}
    -------------------------
    Verification Rules:
    -------------------------
    {verification_rules}

    Migrate as per Mapping of V1 components to V2 components, follow the migration plan and verify the code against the verification rules.
    Do not change any other logic or attributes, and do not introduce new tags.

    Return *only* the final migrated code.
    """
    enc = tiktoken.encoding_for_model("text-davinci-003")
    tokens = enc.encode(prompt)
    print("Prompt tokens: ", len(tokens))
    response = chat_llm.invoke(prompt)
    return response.content.strip()


if __name__ == "__main__":
    query = '<modus-alert message="Info alert with action button" button-text="Action"></modus-alert>'
    print("Retrieving context for:", query)
    context = retrieve_context(query, k=20)
    with open(STATE_FILE, encoding="utf-8") as sf:
        state = json.load(sf)
    print("\n--- Retrieved Context ---\n", context)

    # Check number of tokens in the context
    enc = tiktoken.encoding_for_model("text-davinci-003")
    tokens = enc.encode(context)
    print(f"\nToken count in retrieved context: {len(tokens)}")

    # Always run LLM migration regardless of token count
    migrated = migrate_with_llm(query, context=context, state=state)
    print("\n--- Migrated Code ---\n", migrated)
    output_tokens = len(enc.encode(migrated))
    print(f"Output tokens: {output_tokens}")
