import os
import sys
import json
import argparse  # Import argparse for better CLI parsing
from pathlib import Path
from db import schema, setup
from workflow.langgraph_workflow import build_workflow, MigrationState

# Import functions directly
from ingest.ingest_repos import ingest_repos
from ingest.analyze_repos import main_analyze
from ingest.ingest_context import main_ingest_context
from ingest.update_context import main_update_context
from ingest.extract_comments import extract_all_comments
from build_vector_context import build_vector_index


def run_ingest_repos():
    v1_url = "https://github.com/trimble-oss/modus-web-components.git"
    v2_url = "https://github.com/Trimble-Construction/modus-wc-2.0.git"
    ingest_repos(v1_url, v2_url)


def run_analyze_repos():
    print("Analyzing repositories...")
    main_analyze()


def run_ingest_context():
    print("Ingesting context into DB...")
    main_ingest_context()


def run_full_ingest():
    print("--- Running Full Ingestion Pipeline ---")
    run_ingest_repos()
    run_analyze_repos()
    print("--- Extracting Comments ---")
    extract_all_comments()
    print("--- Comment Extraction Complete ---")
    run_ingest_context()
    print("--- Full Ingestion Complete ---")
    print("--- Building Vector Index ---")
    build_vector_index()
    print("--- Vector Index Build Complete ---")


def run_update_context():
    main_update_context()


def run_workflow(args):
    print("Running migration workflow...")
    workflow = build_workflow()
    initial_state = MigrationState()

    # Prepare initial state based on CLI args
    if args.file:
        file_path = Path(args.file).resolve()
        if not file_path.is_file():
            print(f"Error: File not found: {file_path}")
            return
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                original_code = f.read()
            initial_state.current_file = str(file_path)
            initial_state.modified_code = {str(file_path): original_code}
            print(f"Target: File - {file_path}")
        except Exception as e:
            print(f"Error reading file {file_path}: {e}")
            return
    elif args.code:
        initial_state.current_file = "code_snippet"
        initial_state.modified_code = {"code_snippet": args.code}
        print(f"Target: Code Snippet - {args.code[:50]}...")
    elif args.project:
        print(
            "Project migration not yet fully implemented. Running planning workflow only."
        )
        # For project, workflow might stop after planning or iterate through files
        # For now, just run the planning part (load_context to generate_verification_rules)
        result = workflow.invoke(initial_state, {"recursion_limit": 10})
        print("\n=== Final Planned State (Project Level) ===")
        print(json.dumps(result.dict(), indent=2, default=str))
        return  # Stop here for project planning
    else:
        # Default: Run workflow for inspection (no migration)
        print("Running planning workflow for inspection...")
        result = workflow.invoke(initial_state, {"recursion_limit": 10})
        print("\n=== Final State (Inspection) ===")
        print(json.dumps(result.dict(), indent=2, default=str))
        return

    # Run the full workflow for file/code snippet
    result = workflow.invoke(initial_state, {"recursion_limit": 10})
    print("\n=== Final Migration State ===")
    print(json.dumps(result.dict(), indent=2, default=str))

    # Output migrated code if available
    if result.current_file and result.modified_code.get(result.current_file):
        print("\n--- Migrated Code ---")
        print(result.modified_code[result.current_file])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Modus Migration Tool")
    parser.add_argument(
        "--ingest-repos", action="store_true", help="Clone V1/V2 repos."
    )
    parser.add_argument(
        "--analyze-repos",
        action="store_true",
        help="Analyze cloned repos and extract context.",
    )
    parser.add_argument(
        "--ingest-context",
        action="store_true",
        help="Ingest extracted context into DB.",
    )
    parser.add_argument(
        "--full-ingest",
        action="store_true",
        help="Run full ingestion pipeline (clone, analyze, ingest).",
    )
    parser.add_argument(
        "--update-context",
        action="store_true",
        help="Pull repo changes, re-analyze, and update DB.",
    )
    parser.add_argument(
        "--project", action="store_true", help="Run migration planning for a project."
    )
    parser.add_argument("--file", type=str, help="Migrate a single file.")
    parser.add_argument("--code", type=str, help="Migrate a code snippet.")
    parser.add_argument(
        "--run-workflow",
        action="store_true",
        help="Run the planning workflow for inspection.",
    )

    args = parser.parse_args()

    # Initialize DB if it doesn't exist
    db_file = Path("db/migration_context.db")
    if not db_file.exists():
        print("Initializing database...")
        import subprocess

        subprocess.run([sys.executable, "-m", "db.setup"])

    if args.ingest_repos:
        run_ingest_repos()
    elif args.analyze_repos:
        run_analyze_repos()
    elif args.ingest_context:
        run_ingest_context()
    elif args.full_ingest:
        run_full_ingest()
    elif args.update_context:
        run_update_context()
    elif args.project or args.file or args.code or args.run_workflow:
        run_workflow(args)
    else:
        parser.print_help()
