from langgraph.graph import StateGraph
from .migration_state import MigrationState
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from db.schema import ContextUnit
import json
import re

# Use the centralized LLM call
from cache import cached_llm_invoke

# Adjust DB path to be relative to main.py
DB_PATH = "sqlite:///db/migration_context.db"


# Helper to load context units by type
def load_context_units(session, type_):
    units = {}
    for unit in session.query(ContextUnit).filter_by(type=type_).all():
        try:
            if unit.content.strip().startswith("[") or unit.content.strip().startswith(
                "{"
            ):
                content = json.loads(unit.content)
            else:
                content = unit.content
            units[unit.name] = content
        except Exception as e:
            print(f"Error loading {type_} {unit.name}: {e}")
    return units


def load_context(state: MigrationState) -> MigrationState:
    print("[Node] load_context")
    engine = create_engine(DB_PATH)
    Session = sessionmaker(bind=engine)
    session = Session()
    # Load v1/v2 components
    v1_components = load_context_units(session, "v1_components")
    v2_components = load_context_units(session, "v2_components")
    # Load docs, rules, plans
    v1_docs = load_context_units(session, "v1_docs")
    v2_docs = load_context_units(session, "v2_docs")
    migration_plan = load_context_units(session, "migration_plan")
    verification_rules = load_context_units(session, "verification_rules")
    constraints = load_context_units(session, "constraints")
    session.close()
    # Attach docs to components
    for name, comp in v1_components.items():
        doc = v1_docs.get(name.replace(".tsx", ""), "")
        if isinstance(comp, dict):
            comp["documentation"] = doc
    for name, comp in v2_components.items():
        doc = v2_docs.get(name.replace(".tsx", ""), "")
        if isinstance(comp, dict):
            comp["documentation"] = doc
    state.v1_components = v1_components
    state.v2_components = v2_components
    state.migration_plan = list(migration_plan.values())
    state.verification_rules = list(verification_rules.values())
    # Load constraints (flatten if needed)
    if constraints:
        # If constraints is a dict with a 'constraints' key, use that
        if (
            isinstance(list(constraints.values())[0], dict)
            and "constraints" in list(constraints.values())[0]
        ):
            state.constraints = list(constraints.values())[0]["constraints"]
        else:
            state.constraints = list(constraints.values())
    return state


def analyze_components(state: MigrationState) -> MigrationState:
    print("[Node] analyze_components")

    # This node remains rule-based as it involves structural analysis
    def extract_props(doc):
        if not doc:
            return []
        props = set()
        for line in doc.splitlines():
            if ":" in line and ("props" in line.lower() or "property" in line.lower()):
                parts = line.split(":", 1)
                prop = parts[0].strip()
                if prop and prop.lower() not in ("props", "properties"):
                    props.add(prop)
        return list(props)

    for comp in state.v1_components.values():
        doc = comp.get("documentation", "")
        comp["props"] = extract_props(doc)
    for comp in state.v2_components.values():
        doc = comp.get("documentation", "")
        comp["props"] = extract_props(doc)
    return state


def generate_mapping(state: MigrationState) -> MigrationState:
    print("[Node] generate_mapping")
    # Use LLM to generate mapping
    prompt = f"""
    Generate a component mapping from Modus 1.0 to Modus 2.0.
    V1 Components: {json.dumps(list(state.v1_components.keys()), indent=2)}
    V2 Components: {json.dumps(list(state.v2_components.keys()), indent=2)}

    Output the mapping as a JSON object where keys are V1 component filenames 
    and values are objects containing 'new_tag' (V2 filename) and 'props' (list of common prop names).
    Only map components where a clear V2 equivalent exists. Guess common props based on names.
    Example: {{ "modus-button.tsx": {{ "new_tag": "modus-wc-button.tsx", "props": ["size", "variant"] }} }}
    Return ONLY the JSON object.
    """
    response = cached_llm_invoke(prompt)
    try:
        # Clean potential markdown fences
        cleaned_response = response.strip("```json\n").strip("```").strip()
        mapping = json.loads(cleaned_response)
        state.component_map = mapping
    except Exception as e:
        print(f"Error parsing LLM mapping response: {e}\nResponse: {response}")
        state.component_map = {}  # Fallback to empty
    return state


def generate_constraints(state: MigrationState) -> MigrationState:
    print("[Node] generate_constraints")
    # Use LLM to generate constraints
    prompt = f"""
    Based on this component mapping:
    {json.dumps(state.component_map, indent=2)}
    
    Identify potential migration constraints (breaking changes, API differences, styling issues).
    Output constraints as a JSON list of objects, each with 'type', 'description', and 'components'.
    Example: [{{ "type": "breaking", "description": "...", "components": [...] }}]
    Return ONLY the JSON list.
    """
    response = cached_llm_invoke(prompt)
    try:
        # Clean potential markdown fences
        cleaned_response = response.strip("```json\n").strip("```").strip()
        constraints = json.loads(cleaned_response)
        state.constraints = constraints
    except Exception as e:
        print(f"Error parsing LLM constraints response: {e}\nResponse: {response}")
        state.constraints = []  # Fallback to empty
    return state


def generate_plan(state: MigrationState) -> MigrationState:
    print("[Node] generate_plan")
    # Use LLM to generate migration plan
    prompt = f"""
    Generate a step-by-step migration plan based on:
    Mapping: {json.dumps(state.component_map, indent=2)}
    Constraints: {json.dumps(state.constraints, indent=2)}

    Output the plan as a JSON list of objects, each with 'action', 'status', 'type'.
    Example: [{{ "action": "Step 1: ...", "status": "pending", "type": "step" }}]
    Return ONLY the JSON list.
    """
    response = cached_llm_invoke(prompt)
    try:
        # Clean potential markdown fences
        cleaned_response = response.strip("```json\n").strip("```").strip()
        plan = json.loads(cleaned_response)
        state.migration_plan = plan
    except Exception as e:
        print(f"Error parsing LLM plan response: {e}\nResponse: {response}")
        state.migration_plan = []  # Fallback to empty
    return state


def generate_verification_rules(state: MigrationState) -> MigrationState:
    print("[Node] generate_verification_rules")
    # Use LLM to generate verification rules
    prompt = f"""
    Generate verification rules based on:
    Plan: {json.dumps(state.migration_plan, indent=2)}
    Constraints: {json.dumps(state.constraints, indent=2)}
    Mapping: {json.dumps(state.component_map, indent=2)}

    Output rules as a JSON list of objects, each with 'rule', 'status', 'details'.
    Example: [{{ "rule": "Check tags...", "status": "pending", "details": [...] }}]
    Return ONLY the JSON list.
    """
    response = cached_llm_invoke(prompt)
    try:
        # Clean potential markdown fences
        cleaned_response = response.strip("```json\n").strip("```").strip()
        rules = json.loads(cleaned_response)
        state.verification_rules = rules
    except Exception as e:
        print(
            f"Error parsing LLM verification rules response: {e}\nResponse: {response}"
        )
        state.verification_rules = []  # Fallback to empty
    return state


def migrate_code(state: MigrationState) -> MigrationState:
    print("[Node] migrate_code")
    # This node needs the actual code to migrate, passed via state
    if not state.current_file or not state.modified_code.get(state.current_file):
        print("Error: No code provided in state for migration.")
        return state

    original_code = state.modified_code[
        state.current_file
    ]  # Assume initial code is placed here

    # TODO: Enhance context retrieval (semantic search based on code)
    # For now, use all context for simplicity
    context = f"""
    V1 Components: {json.dumps(state.v1_components, indent=2)}
    V2 Components: {json.dumps(state.v2_components, indent=2)}
    Mapping: {json.dumps(state.component_map, indent=2)}
    Constraints: {json.dumps(state.constraints, indent=2)}
    Plan: {json.dumps(state.migration_plan, indent=2)}
    """

    prompt = f"""
    Migrate the following code from Modus 1.0 to Modus 2.0.
    Use the provided context, mapping, constraints, and plan.
    
    Context:
    {context}
    
    Original Code:
    ```
    {original_code}
    ```
    
    Return ONLY the migrated code, enclosed in ```html ... ```.
    """
    response = cached_llm_invoke(prompt, max_tokens=4096)  # Allow more tokens for code

    # Extract code from potential markdown fences
    match = re.search(r"```(?:html)?\n(.*?)```", response, re.DOTALL)
    migrated_code = match.group(1).strip() if match else response.strip()

    state.modified_code[state.current_file] = migrated_code
    print(f"Migrated code for {state.current_file} generated.")
    return state


def verify_migration(state: MigrationState) -> MigrationState:
    print("[Node] verify_migration")
    if not state.current_file or not state.modified_code.get(state.current_file):
        print("Error: No code provided in state for verification.")
        return state

    migrated_code = state.modified_code[state.current_file]

    prompt = f"""
    Verify the following migrated code against the verification rules.
    
    Migrated Code:
    ```
    {migrated_code}
    ```
    
    Verification Rules:
    {json.dumps(state.verification_rules, indent=2)}
    
    Output the verification results as a JSON list of objects, 
    each matching a rule with an added 'result' ('pass'/'fail'/'warn') and 'comment'.
    Example: [{{ "rule": "...", "status": "verified", "details": [...], "result": "pass", "comment": "..." }}]
    Return ONLY the JSON list.
    """
    response = cached_llm_invoke(prompt)
    try:
        # Clean potential markdown fences
        cleaned_response = response.strip("```json\n").strip("```").strip()
        results = json.loads(cleaned_response)
        # Update verification rules with results
        state.verification_rules = results
    except Exception as e:
        print(f"Error parsing LLM verification response: {e}\nResponse: {response}")
        # Keep original rules if parsing fails
    print(f"Verification for {state.current_file} completed.")
    return state


def build_workflow():
    workflow = StateGraph(MigrationState)
    workflow.add_node("load_context", load_context)
    workflow.add_node("analyze_components", analyze_components)
    workflow.add_node("generate_mapping", generate_mapping)
    workflow.add_node("generate_constraints", generate_constraints)
    workflow.add_node("generate_plan", generate_plan)
    workflow.add_node("generate_verification_rules", generate_verification_rules)
    # Comment out migration and verification nodes
    # workflow.add_node("migrate_code", migrate_code)
    # workflow.add_node("verify_migration", verify_migration)

    workflow.add_edge("load_context", "analyze_components")
    workflow.add_edge("analyze_components", "generate_mapping")
    workflow.add_edge("generate_mapping", "generate_constraints")
    workflow.add_edge("generate_constraints", "generate_plan")
    workflow.add_edge("generate_plan", "generate_verification_rules")
    # Comment out edges involving migration and verification
    # workflow.add_edge("generate_verification_rules", "migrate_code")
    # workflow.add_edge("migrate_code", "verify_migration")

    workflow.set_entry_point("load_context")
    # The workflow now implicitly ends after generate_verification_rules
    return workflow.compile()
