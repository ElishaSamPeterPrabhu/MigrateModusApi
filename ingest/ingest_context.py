import os
import sys
import json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add the project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

from db.schema import ContextUnit
from core.embeddings import compute_embedding
from pathlib import Path

DB_URL = "sqlite:///db/migration_context.db"  # Path relative to project root
CONTEXT_DIR_REL = "context/"  # Path relative to project root


def main_ingest_context():
    print("Starting context ingestion...")
    engine = create_engine(DB_URL)
    Session = sessionmaker(bind=engine)
    session = Session()
    if session.query(ContextUnit).count() > 0:
        print("Clearing existing context units...")
        session.query(ContextUnit).delete()
    context_abs_dir = os.path.abspath(CONTEXT_DIR_REL)
    if not os.path.isdir(context_abs_dir):
        print(f"Context directory not found: {context_abs_dir}")
        return

    for root, dirs, files in os.walk(context_abs_dir):
        # Exclude .gitkeep or other hidden files if necessary
        files = [f for f in files if not f.startswith(".")]

        for file in files:
            path = os.path.join(root, file)
            # Skip directories if os.walk includes them in files list (rare)
            if os.path.isdir(path):
                continue
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()

                # Infer type and name from path relative to CONTEXT_DIR
                rel_path = os.path.relpath(path, context_abs_dir)
                parts = Path(rel_path).parts
                type_ = parts[0] if len(parts) > 1 else "misc"
                name = Path(file).stem

                # Handle JSON files specially
                if file.endswith(".json"):
                    try:
                        json_data = json.loads(content)
                        # For components.json, process each component
                        if file == "components.json":
                            for component_name, component_data in json_data.items():
                                # Create a structured content with all component info (no comments field)
                                structured_content = json.dumps(
                                    {
                                        "name": component_name,
                                        "props": component_data.get("props", []),
                                        "events": component_data.get("events", []),
                                        "slots": component_data.get("slots", []),
                                        "documentation": component_data.get(
                                            "documentation", ""
                                        ),
                                    }
                                )
                                embedding = compute_embedding(structured_content)
                                unit = ContextUnit(
                                    type=type_,
                                    name=component_name,
                                    content=structured_content,
                                    embedding=embedding,
                                )
                                session.add(unit)
                                print(f"Ingested {type_}/{component_name}")
                        else:
                            # For other JSON files, process as before
                            embedding = compute_embedding(content)
                            unit = ContextUnit(
                                type=type_,
                                name=name,
                                content=content,
                                embedding=embedding,
                            )
                            session.add(unit)
                            print(f"Ingested {type_}/{name}")
                    except json.JSONDecodeError as e:
                        print(f"Error parsing JSON file {path}: {e}")
                else:
                    # For non-JSON files, process as before
                    embedding = compute_embedding(content)
                    unit = ContextUnit(
                        type=type_, name=name, content=content, embedding=embedding
                    )
                    session.add(unit)
                    print(f"Ingested {type_}/{name}")
            except Exception as e:
                print(f"Error ingesting file {path}: {e}")

    session.commit()
    session.close()
    print("Ingestion complete.")


if __name__ == "__main__":
    main_ingest_context()
