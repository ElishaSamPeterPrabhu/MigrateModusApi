import os
import json
import re
from pathlib import Path
from typing import Dict

# Import the LLM invocation function
from cache import cached_llm_invoke


# --- LLM Context Generation Helpers (similar to original utils.py) ---
def get_prop_context(content: str, prop: str) -> str:
    prompt = f"""
    Given the following component code snippet:
    --------------------------
    {content[:2000]} # Limit context length for prompt
    --------------------------
    Explain the purpose and usage of the prop '{prop}' in this component based *only* on the provided code snippet.
    Provide a concise, one-sentence comment.
    """
    response = cached_llm_invoke(prompt, max_tokens=100)
    return response.strip()


def get_event_context(content: str, event: str) -> str:
    prompt = f"""
    Given the following component code snippet:
    --------------------------
    {content[:2000]} # Limit context length for prompt
    --------------------------
    Explain the purpose and usage of the event '{event}' in this component based *only* on the provided code snippet.
    Provide a concise, one-sentence comment.
    """
    response = cached_llm_invoke(prompt, max_tokens=100)
    return response.strip()


def get_slot_context(content: str, slot: str) -> str:
    prompt = f"""
    Given the following component code snippet:
    --------------------------
    {content[:2000]} # Limit context length for prompt
    --------------------------
    Explain the purpose and usage of the slot '{slot}' in this component based *only* on the provided code snippet.
    Provide a concise, one-sentence comment.
    """
    response = cached_llm_invoke(prompt, max_tokens=100)
    return response.strip()


# --- Adapted functions from original utils.py ---


def identify_components(directory):
    """Find all .tsx files, optionally check for @Component."""
    components = []
    try:
        for f in os.listdir(directory):
            if f.endswith(".tsx"):
                components.append(f)
    except Exception as e:
        print(f"Error reading directory {directory}: {e}")
    return components


def load_component_docs(repo_path: Path, version: str) -> Dict[str, str]:
    """Load component documentation from a repository."""
    docs = {}
    if version.lower() == "v1":
        docs_path = repo_path / "stencil-workspace/storybook/stories/components"
        if docs_path.exists():
            for folder in docs_path.glob("*"):
                for file in folder.glob("*"):
                    if file.suffix in [".md", ".txt"]:
                        component_name = (
                            file.stem.lower()
                            .replace("-storybook-docs", "")
                            .replace(".stories", "")
                        )
                        try:
                            with file.open("r", encoding="utf-8", errors="ignore") as f:
                                docs[component_name] = f.read()
                        except Exception as e:
                            print(f"Error reading doc file {file}: {e}")
    elif version.lower() == "v2":
        comp_dir = repo_path / "src/components"
        if comp_dir.exists():
            for folder in comp_dir.glob("*"):
                for stories_file in folder.glob("*.stories.ts"):
                    component_name = folder.name
                    try:
                        with stories_file.open(
                            "r", encoding="utf-8", errors="ignore"
                        ) as f:
                            docs[component_name] = f.read()
                    except Exception as e:
                        print(f"Error reading {stories_file}: {e}")
    return docs


def extract_comment_above(content: str, keyword: str, name: str) -> str:
    """Extract the comment immediately above a prop/event/slot definition."""
    # Look for JSDoc or single-line comments above the definition
    # Example: @Prop() foo: string; or @Event() bar: CustomEvent<any>;
    pattern = rf"((?:/\*\*[\s\S]*?\*/\s*)|(?://.*\n)*)\s*@{keyword}\(\)\s+{name}:"
    match = re.search(pattern, content)
    if match:
        comment_block = match.group(1).strip()
        # Prefer JSDoc
        jsdoc_match = re.search(r"/\*\*([\s\S]*?)\*/", comment_block)
        if jsdoc_match:
            return jsdoc_match.group(1).replace("*", "").strip()
        # Else, use single-line comment
        single_line_match = re.findall(r"//(.*)", comment_block)
        if single_line_match:
            return " ".join([s.strip() for s in single_line_match])
    return ""


def extract_prop_blocks(content: str):
    """
    Extract all prop blocks with their comments, decorator, and name.
    Returns a list of (comment, name) tuples.
    """
    prop_pattern = re.compile(
        r"""(
            (?:\s*/\*\*[\s\S]*?\*/\s*)?      # Optional JSDoc comment
            (?:\s*//.*\n)*                      # Optional single-line comments
        )
        @Prop(?:\([^)]*\))?                     # @Prop() or @Prop({...})
        \s+(\w+)                                # prop name
        \s*[!?:]*\s*                            # optional ! or ? or :
        :\s*                                     # colon and optional spaces
        [^=;]+                                   # type (not captured)
        (?:=\s*[^;]+)?                          # optional default value
        \s*;                                    # semicolon
        """,
        re.VERBOSE,
    )
    return [(m[0], m[1]) for m in prop_pattern.findall(content)]


def extract_event_blocks(content: str):
    """
    Extract all event blocks with their comments, decorator, and name.
    Returns a list of (comment, name) tuples.
    """
    event_pattern = re.compile(
        r"""(
            (?:\s*/\*\*[\s\S]*?\*/\s*)?      # Optional JSDoc comment
            (?:\s*//.*\n)*                      # Optional single-line comments
        )
        @Event(?:\([^)]*\))?                    # @Event() or @Event({...})
        \s+(\w+)                                # event name
        \s*[!?:]*\s*                            # optional ! or ? or :
        :\s*                                     # colon and optional spaces
        [^=;]+                                   # type (not captured)
        (?:=\s*[^;]+)?                          # optional default value
        \s*;                                    # semicolon
        """,
        re.VERBOSE,
    )
    return [(m[0], m[1]) for m in event_pattern.findall(content)]


def extract_slot_blocks(content: str):
    """
    Extract all slot blocks with their comments and name.
    Returns a list of (comment, name) tuples.
    """
    # This will look for comments above <slot name="...">
    slot_pattern = re.compile(
        r"""(
            (?:\s*/\*\*[\s\S]*?\*/\s*)?      # Optional JSDoc comment
            (?:\s*//.*\n)*                      # Optional single-line comments
        )
        <slot\s+name=["'](\w+)["']
        """,
        re.VERBOSE,
    )
    return [(m[0], m[1]) for m in slot_pattern.findall(content)]


llm_call_count = 0
llm_filled_props = 0
llm_filled_events = 0
llm_filled_slots = 0


def get_llm_comments_for_missing_items(
    content, missing_props, missing_events, missing_slots
):
    global llm_call_count
    llm_call_count += 1
    prompt = f"""
Given the following component code:
--------------------------
{content[:2000]}
--------------------------
For each of the following items, write a concise, one-sentence description. Return your answer as a JSON object with keys 'props', 'events', and 'slots', each mapping to an object of name: comment pairs.

Missing props: {', '.join(missing_props) if missing_props else 'None'}
Missing events: {', '.join(missing_events) if missing_events else 'None'}
Missing slots: {', '.join(missing_slots) if missing_slots else 'None'}

Example output:
{{
  "props": {{"prop1": "...", "prop2": "..."}},
  "events": {{"event1": "..."}},
  "slots": {{"slot1": "..."}}
}}
"""
    try:
        response = cached_llm_invoke(prompt)
        json_start = response.find("{")
        json_end = response.rfind("}") + 1
        if json_start != -1 and json_end != -1:
            json_str = response[json_start:json_end]
            return json.loads(json_str)
        return {"props": {}, "events": {}, "slots": {}}
    except Exception as e:
        print(f"Error getting LLM comments: {e}")
        return {"props": {}, "events": {}, "slots": {}}


def parse_component_file(path: Path) -> Dict:
    global llm_filled_props, llm_filled_events, llm_filled_slots
    props, events, slots = [], [], []
    content = ""
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        missing_props, missing_events, missing_slots = [], [], []
        prop_objs = []
        for comment_block, prop_name in extract_prop_blocks(content):
            comment = ""
            jsdoc_match = re.search(r"/\*\*([\s\S]*?)\*/", comment_block)
            if jsdoc_match:
                comment = jsdoc_match.group(1).replace("*", "").strip()
            else:
                single_line_match = re.findall(r"//(.*)", comment_block)
                if single_line_match:
                    comment = " ".join([s.strip() for s in single_line_match])
            if not comment:
                missing_props.append(prop_name)
            prop_objs.append({"name": prop_name, "comment": comment})
        event_objs = []
        for comment_block, event_name in extract_event_blocks(content):
            comment = ""
            jsdoc_match = re.search(r"/\*\*([\s\S]*?)\*/", comment_block)
            if jsdoc_match:
                comment = jsdoc_match.group(1).replace("*", "").strip()
            else:
                single_line_match = re.findall(r"//(.*)", comment_block)
                if single_line_match:
                    comment = " ".join([s.strip() for s in single_line_match])
            if not comment:
                missing_events.append(event_name)
            event_objs.append({"name": event_name, "comment": comment})
        slot_objs = []
        for comment_block, slot_name in extract_slot_blocks(content):
            comment = ""
            jsdoc_match = re.search(r"/\*\*([\s\S]*?)\*/", comment_block)
            if jsdoc_match:
                comment = jsdoc_match.group(1).replace("*", "").strip()
            else:
                single_line_match = re.findall(r"//(.*)", comment_block)
                if single_line_match:
                    comment = " ".join([s.strip() for s in single_line_match])
            if not comment:
                missing_slots.append(slot_name)
            slot_objs.append({"name": slot_name, "comment": comment})
        # If any missing, call LLM once for all
        if missing_props or missing_events or missing_slots:
            llm_comments = get_llm_comments_for_missing_items(
                content, missing_props, missing_events, missing_slots
            )
            for obj in prop_objs:
                if not obj["comment"] and obj["name"] in llm_comments.get("props", {}):
                    obj["comment"] = llm_comments["props"][obj["name"]]
                    llm_filled_props += 1
            for obj in event_objs:
                if not obj["comment"] and obj["name"] in llm_comments.get("events", {}):
                    obj["comment"] = llm_comments["events"][obj["name"]]
                    llm_filled_events += 1
            for obj in slot_objs:
                if not obj["comment"] and obj["name"] in llm_comments.get("slots", {}):
                    obj["comment"] = llm_comments["slots"][obj["name"]]
                    llm_filled_slots += 1
        props, events, slots = prop_objs, event_objs, slot_objs
    except Exception as e:
        print(f"Error parsing file {path}: {e}")

    return {
        "props": props,
        "events": events,
        "slots": slots,
    }


def extract_component_details(repo_path: Path, version: str) -> Dict:
    """Extract component details, combining parsing and docs."""
    components = {}
    docs = load_component_docs(repo_path, version)

    # Find all potential component files first
    all_potential_components = []
    for root, _, files in os.walk(repo_path):
        for file in files:
            if file.endswith(".tsx") and file.startswith("modus-"):
                all_potential_components.append(Path(root) / file)

    print(
        f"Found {len(all_potential_components)} potential TSX components in {version} repo."
    )

    count = 0
    for component_file in all_potential_components:
        count += 1
        print(
            f"Processing component {count}/{len(all_potential_components)}: {component_file.name}"
        )
        if component_file.exists():
            parsed = parse_component_file(component_file)
            component_key = component_file.stem.lower()
            doc_content = docs.get(component_key, "")
            parsed["documentation"] = doc_content
            components[component_file.name] = parsed

    return components


# --- Main analysis and saving logic ---


def analyze_and_save(repo_dir, version, context_dir):
    repo_path = Path(repo_dir)
    print(f"Analyzing {version} repo at {repo_path}...")

    # Extract structured component details (props, events, slots, docs)
    component_details = extract_component_details(repo_path, version)

    # Save structured component details as JSON
    comp_out_dir = Path(f"{context_dir}/{version}_components")
    comp_out_dir.mkdir(parents=True, exist_ok=True)
    comp_file_path = comp_out_dir / "components.json"
    with open(comp_file_path, "w", encoding="utf-8") as f:
        json.dump(component_details, f, indent=2)
    print(f"Saved {len(component_details)} component details to {comp_file_path}")

    # Save raw documentation files (as found by load_component_docs)
    raw_docs = load_component_docs(repo_path, version)
    docs_out_dir = Path(f"{context_dir}/{version}_docs")
    docs_out_dir.mkdir(parents=True, exist_ok=True)
    for name, content in raw_docs.items():
        # Recreate a simple file structure for docs based on component name
        out_path = docs_out_dir / f"{name}.md"  # Assuming saving as markdown
        try:
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception as e:
            print(f"Error writing doc file {out_path}: {e}")
    print(f"Saved {len(raw_docs)} raw documentation files to {docs_out_dir}")

    # At the end of main_analyze or analyze_and_save, print the stats:
    print(
        f"LLM called {llm_call_count} times. Filled {llm_filled_props} props, {llm_filled_events} events, {llm_filled_slots} slots."
    )


def main_analyze():
    context_base_dir = (
        Path(__file__).parent.parent / "context"
    )  # Adjusted path relative to script
    context_base_dir.mkdir(exist_ok=True)
    repo_base_dir = (
        Path(__file__).parent.parent / "repos"
    )  # Assuming repos are cloned here

    v1_repo_path = repo_base_dir / "modus-web-components.git"
    v2_repo_path = repo_base_dir / "modus-wc-2.0.git"

    if v1_repo_path.exists():
        analyze_and_save(v1_repo_path, "v1", context_base_dir)
    else:
        print(f"V1 repo not found at {v1_repo_path}. Please clone first.")

    if v2_repo_path.exists():
        analyze_and_save(v2_repo_path, "v2", context_base_dir)
    else:
        print(f"V2 repo not found at {v2_repo_path}. Please clone first.")


if __name__ == "__main__":
    main_analyze()
