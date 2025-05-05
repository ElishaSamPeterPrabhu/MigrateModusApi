import os
import json
from pathlib import Path
from typing import Dict
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Assuming these modules are in the same directory or accessible via PYTHONPATH
from db.schema import ContextUnit
from ingest.ingest_repos import ingest_repos  # To ensure repos are up-to-date
from ingest.analyze_repos import extract_component_details, load_component_docs
from core.embeddings import compute_embedding

DB_URL = "sqlite:///db/migration_context.db"
CONTEXT_DIR = "context/"  # Base directory where analyze_repos saves files
REPO_DIR = "repos/"


def load_current_db_state(session) -> Dict[str, Dict]:
    """Load the current state of context units from the database."""
    db_state = {"components": {}, "docs": {}}
    for unit in session.query(ContextUnit).all():
        key = f"{unit.type}/{unit.name}"
        # Deserialize JSON content for components
        content = unit.content
        if unit.type.endswith("_components"):
            try:
                content = json.loads(unit.content)
            except json.JSONDecodeError:
                print(f"Warning: Could not parse JSON for DB unit {key}")

        if unit.type.startswith("v1_") or unit.type.startswith("v2_"):
            category = "components" if "_components" in unit.type else "docs"
            version_prefix = unit.type.split("_")[0]  # v1 or v2
            item_key = f"{version_prefix}/{unit.name}"  # e.g., v1/modus-button.tsx or v1/modus-button

            if category == "components":
                db_state[category][unit.name] = (
                    {  # Keyed by filename e.g., modus-button.tsx
                        "id": unit.id,
                        "content": content,  # This is the parsed dict
                        "embedding_present": bool(unit.embedding),
                    }
                )
            else:  # category == "docs"
                db_state[category][item_key] = (
                    {  # Keyed by version/name e.g., v1/modus-button
                        "id": unit.id,
                        "content": content,  # This is the raw doc string
                        "embedding_present": bool(unit.embedding),
                    }
                )
    return db_state


def get_new_analysis_state() -> Dict[str, Dict]:
    """Run analysis and return the new state based on current repo files."""
    new_state = {"components": {}, "docs": {}}
    context_base_dir = Path(CONTEXT_DIR)
    repo_base_dir = Path(REPO_DIR)

    v1_repo_path = repo_base_dir / "modus-web-components.git"
    v2_repo_path = repo_base_dir / "modus-wc-2.0.git"

    if v1_repo_path.exists():
        v1_details = extract_component_details(v1_repo_path, "v1")
        v1_docs = load_component_docs(v1_repo_path, "v1")
        new_state["components"].update(v1_details)
        for name, content in v1_docs.items():
            new_state["docs"][f"v1/{name}"] = content  # Key format: v1/component_name

    if v2_repo_path.exists():
        v2_details = extract_component_details(v2_repo_path, "v2")
        v2_docs = load_component_docs(v2_repo_path, "v2")
        new_state["components"].update(v2_details)
        for name, content in v2_docs.items():
            new_state["docs"][f"v2/{name}"] = content  # Key format: v2/component_name

    return new_state


def main_update_context():
    print("--- Starting Context Update --- ")
    # 1. Ensure repos are up-to-date (using default URLs for simplicity here)
    # In a real scenario, you might get URLs from config or args
    try:
        ingest_repos(
            "https://github.com/trimble-oss/modus-web-components.git",
            "https://github.com/Trimble-Construction/modus-wc-2.0.git",
            dest_dir=REPO_DIR,
        )
    except Exception as e:
        print(f"Error updating repositories: {e}. Aborting update.")
        return

    # 2. Run analysis to get the new state
    print("\nAnalyzing current repository states...")
    new_state = get_new_analysis_state()

    # 3. Connect to DB and load old state
    print("\nConnecting to database...")
    engine = create_engine(DB_URL)
    Session = sessionmaker(bind=engine)
    session = Session()
    print("Loading current state from database...")
    db_state = load_current_db_state(session)

    # 4. Compare and Update
    print("\nComparing new analysis with database state and updating...")

    # --- Components ---
    db_components = db_state["components"]
    new_components = new_state["components"]

    added_comps, updated_comps, deleted_comp_ids = 0, 0, 0

    # Check for new/updated components
    for comp_filename, new_content_dict in new_components.items():
        version_prefix = (
            "v1"
            if "modus-web-components" in str(new_content_dict.get("path", "v1"))
            else "v2"
        )  # Infer version
        db_entry = db_components.get(comp_filename)
        type_ = f"{version_prefix}_components"

        # Convert new content dict to JSON string for comparison/storage
        new_content_json = json.dumps(new_content_dict, sort_keys=True)

        if db_entry:
            # Existing component: Check for changes
            old_content_json = json.dumps(db_entry["content"], sort_keys=True)
            if old_content_json != new_content_json:
                # Update existing DB record
                db_unit = session.query(ContextUnit).get(db_entry["id"])
                if db_unit:
                    print(f"  Updating component: {comp_filename}")
                    db_unit.content = json.dumps(
                        new_content_dict
                    )  # Store as JSON string
                    db_unit.embedding = compute_embedding(
                        db_unit.content
                    )  # Recompute embedding
                    session.add(db_unit)
                    updated_comps += 1
        else:
            # New component: Add to DB
            print(f"  Adding new component: {comp_filename}")
            embedding = compute_embedding(new_content_json)
            unit = ContextUnit(
                type=type_,
                name=comp_filename,  # Use filename as name
                content=new_content_json,  # Store as JSON string
                embedding=embedding,
            )
            session.add(unit)
            added_comps += 1

    # Check for deleted components
    new_comp_filenames = set(new_components.keys())
    for comp_filename, db_entry in db_components.items():
        if comp_filename not in new_comp_filenames:
            print(f"  Deleting component: {comp_filename}")
            db_unit = session.query(ContextUnit).get(db_entry["id"])
            if db_unit:
                session.delete(db_unit)
                deleted_comp_ids += 1

    # --- Docs ---
    db_docs = db_state["docs"]
    new_docs = new_state["docs"]
    added_docs, updated_docs, deleted_doc_ids = 0, 0, 0

    # Check for new/updated docs
    for doc_key, new_content_str in new_docs.items():  # key e.g., v1/modus-button
        db_entry = db_docs.get(doc_key)
        version_prefix, doc_name = doc_key.split("/")
        type_ = f"{version_prefix}_docs"

        if db_entry:
            # Existing doc: Check for changes
            if db_entry["content"] != new_content_str:
                # Update existing DB record
                db_unit = session.query(ContextUnit).get(db_entry["id"])
                if db_unit:
                    print(f"  Updating doc: {doc_key}")
                    db_unit.content = new_content_str
                    db_unit.embedding = compute_embedding(new_content_str)
                    session.add(db_unit)
                    updated_docs += 1
        else:
            # New doc: Add to DB
            print(f"  Adding new doc: {doc_key}")
            embedding = compute_embedding(new_content_str)
            unit = ContextUnit(
                type=type_, name=doc_name, content=new_content_str, embedding=embedding
            )
            session.add(unit)
            added_docs += 1

    # Check for deleted docs
    new_doc_keys = set(new_docs.keys())
    for doc_key, db_entry in db_docs.items():
        if doc_key not in new_doc_keys:
            print(f"  Deleting doc: {doc_key}")
            db_unit = session.query(ContextUnit).get(db_entry["id"])
            if db_unit:
                session.delete(db_unit)
                deleted_doc_ids += 1

    # 5. Commit changes and close session
    try:
        session.commit()
        print("\nDatabase update committed.")
        print(
            f"Summary: Components Added={added_comps}, Updated={updated_comps}, Deleted={deleted_comp_ids}"
        )
        print(
            f"Summary: Docs Added={added_docs}, Updated={updated_docs}, Deleted={deleted_doc_ids}"
        )
    except Exception as e:
        session.rollback()
        print(f"Error committing DB changes: {e}")
    finally:
        session.close()
        print("DB session closed.")

    print("--- Context Update Complete --- ")


if __name__ == "__main__":
    main_update_context()
