import os
import re
from pathlib import Path
import json
import sys
from difflib import SequenceMatcher

# Add the project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)


def similar(a, b):
    """Return similarity ratio between two strings."""
    return SequenceMatcher(None, a, b).ratio()


def find_similar_component(workflow_state, component_name):
    """Find the most similar component in workflow state."""
    if not workflow_state:
        return None

    best_match = None
    best_ratio = 0.5  # Minimum similarity threshold

    for component in workflow_state.get("components", []):
        state_name = component.get("name", "")
        if not state_name:
            continue

        ratio = similar(component_name.lower(), state_name.lower())
        if ratio > best_ratio:
            best_ratio = ratio
            best_match = component

    return best_match


def get_comments_from_similar_component(similar_component, item_type, item_name):
    """Get comments from a similar component if available."""
    if not similar_component:
        return None

    if item_type == "prop":
        for prop in similar_component.get("props", []):
            if similar(prop.get("name", "").lower(), item_name.lower()) > 0.8:
                return prop.get("comment", "")
    elif item_type == "event":
        for event in similar_component.get("events", []):
            if similar(event.get("name", "").lower(), item_name.lower()) > 0.8:
                return event.get("comment", "")
    elif item_type == "slot":
        for slot in similar_component.get("slots", []):
            if similar(slot.get("name", "").lower(), item_name.lower()) > 0.8:
                return slot.get("comment", "")
    return None


def load_workflow_state():
    """Load workflow state from file."""
    try:
        with open("src/data/workflow_state.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading workflow state: {e}")
        return None


def get_comments_from_workflow_state(
    workflow_state, component_name, item_type, item_name
):
    """Get comments from workflow state if available."""
    if not workflow_state:
        return None

    # Look for the component in the workflow state
    for component in workflow_state.get("components", []):
        if component.get("name", "").lower() == component_name.lower():
            if item_type == "prop":
                for prop in component.get("props", []):
                    if prop.get("name", "").lower() == item_name.lower():
                        return prop.get("comment", "")
            elif item_type == "event":
                for event in component.get("events", []):
                    if event.get("name", "").lower() == item_name.lower():
                        return event.get("comment", "")
            elif item_type == "slot":
                for slot in component.get("slots", []):
                    if slot.get("name", "").lower() == item_name.lower():
                        return slot.get("comment", "")
    return None


def extract_prop_comments(content, prop_name):
    """Extract comments for a specific prop from the content."""
    # Look for JSDoc comments before the prop definition
    pattern = rf"/\*\*[\s\S]*?\*/\s*@prop\s*{prop_name}"
    match = re.search(pattern, content)
    if match:
        comment = match.group(0)
        # Extract the description from the comment
        description = re.search(r"@description\s*(.*?)(?=\n\s*\*|$)", comment)
        if description:
            return description.group(1).strip()

    # If no JSDoc comment found, look for inline comments
    pattern = rf"//\s*{prop_name}:.*$"
    match = re.search(pattern, content, re.MULTILINE)
    if match:
        return match.group(0).replace(f"// {prop_name}:", "").strip()

    return None


def extract_event_comments(content, event_name):
    """Extract comments for a specific event from the content."""
    # Look for JSDoc comments before the event definition
    pattern = rf"/\*\*[\s\S]*?\*/\s*@event\s*{event_name}"
    match = re.search(pattern, content)
    if match:
        comment = match.group(0)
        # Extract the description from the comment
        description = re.search(r"@description\s*(.*?)(?=\n\s*\*|$)", comment)
        if description:
            return description.group(1).strip()

    # If no JSDoc comment found, look for inline comments
    pattern = rf"//\s*{event_name}:.*$"
    match = re.search(pattern, content, re.MULTILINE)
    if match:
        return match.group(0).replace(f"// {event_name}:", "").strip()

    return None


def extract_slot_comments(content, slot_name):
    """Extract comments for a specific slot from the content."""
    # Look for JSDoc comments before the slot definition
    pattern = rf"/\*\*[\s\S]*?\*/\s*@slot\s*{slot_name}"
    match = re.search(pattern, content)
    if match:
        comment = match.group(0)
        # Extract the description from the comment
        description = re.search(r"@description\s*(.*?)(?=\n\s*\*|$)", comment)
        if description:
            return description.group(1).strip()

    # If no JSDoc comment found, look for inline comments
    pattern = rf"//\s*{slot_name}:.*$"
    match = re.search(pattern, content, re.MULTILINE)
    if match:
        return match.group(0).replace(f"// {slot_name}:", "").strip()

    return None


def generate_context_with_llm(component_name, item_type, item_name):
    """Generate context using LLM."""
    prompt = f"""Generate a clear and concise description for the {item_type} '{item_name}' in the Modus component '{component_name}'.
The description should explain:
1. What this {item_type} is used for
2. What type of data it accepts/emits
3. Any important behavior or constraints

Keep the description brief but informative.
"""
    try:
        response = llm_invoke(prompt)
        if response:
            return response.strip()
        return f"Generated description for {item_type} {item_name}"
    except Exception as e:
        print(f"Error generating context with LLM: {e}")
        return f"Generated description for {item_type} {item_name}"


def find_component_in_workflow_state(workflow_state, component_name, is_v1=True):
    """Find the exact component in workflow state."""
    if not workflow_state:
        print("No workflow state available")
        return None

    # Add .tsx extension if not present
    if not component_name.endswith(".tsx"):
        component_name = f"{component_name}.tsx"

    # Get the correct components section
    components_key = "v1_components" if is_v1 else "v2_components"
    components = workflow_state.get(components_key, {})

    # First try exact match
    component = components.get(component_name)
    if component:
        print(f"Found exact match for {component_name} in {components_key}")
        return component

    # Try case-insensitive match
    for key in components.keys():
        if key.lower() == component_name.lower():
            print(
                f"Found case-insensitive match: {key} for {component_name} in {components_key}"
            )
            return components[key]

    # Try partial match
    for key in components.keys():
        if component_name.lower() in key.lower():
            print(
                f"Found partial match: {key} for {component_name} in {components_key}"
            )
            return components[key]

    print(f"No match found for {component_name} in {components_key}")
    return None


def get_comments_from_workflow_component(component_data, item_type, item_name):
    """Get comments from a workflow component if available."""
    if not component_data:
        return None

    items = []
    if item_type == "prop":
        items = component_data.get("props", [])
    elif item_type == "event":
        items = component_data.get("events", [])
    elif item_type == "slot":
        items = component_data.get("slots", [])

    # Look for exact name match
    for item in items:
        if item.get("name", "").lower() == item_name.lower():
            comment = item.get("comment")
            if comment:
                print(f"Found comment for {item_type} {item_name}: {comment[:50]}...")
                return comment

    print(f"No comment found for {item_type} {item_name}")
    return None


def process_component(file_path, component_data, workflow_state, is_v1=True):
    """Process a component file and update its data with comments."""
    try:
        stats = {
            "props_found": 0,
            "props_generated": 0,
            "events_found": 0,
            "events_generated": 0,
            "slots_found": 0,
            "slots_generated": 0,
        }

        component_name = component_data.get("name", "Unknown")
        print(f"\nProcessing component: {component_name}")

        # Find component in workflow state
        workflow_component = find_component_in_workflow_state(
            workflow_state, component_name, is_v1
        )
        if workflow_component:
            print(f"Found component data in workflow state")
            print(f"Props: {len(workflow_component.get('props', []))}")
            print(f"Events: {len(workflow_component.get('events', []))}")
            print(f"Slots: {len(workflow_component.get('slots', []))}")

        # Process props
        for prop in component_data.get("props", []):
            prop_name = prop.get("name", "")
            if not prop_name:
                continue

            # Try to get comment from workflow component
            comment = get_comments_from_workflow_component(
                workflow_component, "prop", prop_name
            )
            if comment:
                # Use comment exactly as it appears in workflow state
                prop["comment"] = comment
                stats["props_found"] += 1
            else:
                # Only use LLM if prop doesn't exist in workflow state
                comment = generate_context_with_llm(component_name, "prop", prop_name)
                prop["comment"] = f"// {comment}"  # Add comment marker for consistency
                stats["props_generated"] += 1

        # Process events
        for event in component_data.get("events", []):
            event_name = event.get("name", "")
            if not event_name:
                continue

            # Try to get comment from workflow component
            comment = get_comments_from_workflow_component(
                workflow_component, "event", event_name
            )
            if comment:
                # Use comment exactly as it appears in workflow state
                event["comment"] = comment
                stats["events_found"] += 1
            else:
                # Only use LLM if event doesn't exist in workflow state
                comment = generate_context_with_llm(component_name, "event", event_name)
                event["comment"] = f"// {comment}"  # Add comment marker for consistency
                stats["events_generated"] += 1

        # Process slots
        for slot in component_data.get("slots", []):
            slot_name = slot.get("name", "")
            if not slot_name:
                continue

            # Try to get comment from workflow component
            comment = get_comments_from_workflow_component(
                workflow_component, "slot", slot_name
            )
            if comment:
                # Use comment exactly as it appears in workflow state
                slot["comment"] = comment
                stats["slots_found"] += 1
            else:
                # Only use LLM if slot doesn't exist in workflow state
                comment = generate_context_with_llm(component_name, "slot", slot_name)
                slot["comment"] = f"// {comment}"  # Add comment marker for consistency
                stats["slots_generated"] += 1

        return component_data, stats
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return component_data, None


def process_repository(repo_path, components_file, is_v1=True):
    """Process all components in a repository and update their data with comments."""
    total_stats = {
        "props_found": 0,
        "props_generated": 0,
        "events_found": 0,
        "events_generated": 0,
        "slots_found": 0,
        "slots_generated": 0,
    }

    try:
        # Load workflow state
        workflow_state = load_workflow_state()
        if not workflow_state:
            print("Failed to load workflow state")
            return total_stats

        # Try to load components data
        try:
            with open(components_file, "r", encoding="utf-8") as f:
                components_data = json.load(f)
        except json.JSONDecodeError as e:
            print(f"Error loading {components_file}: {e}")
            print("Creating new components data...")
            components_data = {}

        # Create a list of items to avoid dictionary size changes during iteration
        component_items = list(components_data.items())

        for component_name, component_data in component_items:
            print(f"\nProcessing component: {component_name}")

            # Find component in workflow state
            workflow_component = find_component_in_workflow_state(
                workflow_state, component_name, is_v1
            )
            if workflow_component:
                print(f"Found component data in workflow state")
                print(f"Props: {len(workflow_component.get('props', []))}")
                print(f"Events: {len(workflow_component.get('events', []))}")
                print(f"Slots: {len(workflow_component.get('slots', []))}")

            # Process props
            for prop in component_data.get("props", []):
                prop_name = prop.get("name", "")
                if not prop_name:
                    continue

                # Try to get comment from workflow component
                comment = get_comments_from_workflow_component(
                    workflow_component, "prop", prop_name
                )
                if comment:
                    # Use comment exactly as it appears in workflow state
                    prop["comment"] = comment
                    total_stats["props_found"] += 1
                else:
                    # Only use LLM if prop doesn't exist in workflow state
                    comment = generate_context_with_llm(
                        component_name, "prop", prop_name
                    )
                    prop["comment"] = (
                        f"// {comment}"  # Add comment marker for consistency
                    )
                    total_stats["props_generated"] += 1

            # Process events
            for event in component_data.get("events", []):
                event_name = event.get("name", "")
                if not event_name:
                    continue

                # Try to get comment from workflow component
                comment = get_comments_from_workflow_component(
                    workflow_component, "event", event_name
                )
                if comment:
                    # Use comment exactly as it appears in workflow state
                    event["comment"] = comment
                    total_stats["events_found"] += 1
                else:
                    # Only use LLM if event doesn't exist in workflow state
                    comment = generate_context_with_llm(
                        component_name, "event", event_name
                    )
                    event["comment"] = (
                        f"// {comment}"  # Add comment marker for consistency
                    )
                    total_stats["events_generated"] += 1

            # Process slots
            for slot in component_data.get("slots", []):
                slot_name = slot.get("name", "")
                if not slot_name:
                    continue

                # Try to get comment from workflow component
                comment = get_comments_from_workflow_component(
                    workflow_component, "slot", slot_name
                )
                if comment:
                    # Use comment exactly as it appears in workflow state
                    slot["comment"] = comment
                    total_stats["slots_found"] += 1
                else:
                    # Only use LLM if slot doesn't exist in workflow state
                    comment = generate_context_with_llm(
                        component_name, "slot", slot_name
                    )
                    slot["comment"] = (
                        f"// {comment}"  # Add comment marker for consistency
                    )
                    total_stats["slots_generated"] += 1

            # Update the component data
            components_data[component_name] = component_data

        # Save updated data
        with open(components_file, "w", encoding="utf-8") as f:
            json.dump(components_data, f, indent=2)

        return total_stats
    except Exception as e:
        print(f"Error processing repository: {e}")
        return total_stats


def extract_all_comments():
    """Extract comments for both V1 and V2 components and print stats."""
    v1_stats = process_repository(
        "context/v1_components", "context/v1_components/components.json", is_v1=True
    )
    v2_stats = process_repository(
        "context/v2_components", "context/v2_components/components.json", is_v1=False
    )
    print("\nStatistics:")
    print("\nV1 Repository:")
    print(
        f"Props: {v1_stats['props_found']} found, {v1_stats['props_generated']} generated"
    )
    print(
        f"Events: {v1_stats['events_found']} found, {v1_stats['events_generated']} generated"
    )
    print(
        f"Slots: {v1_stats['slots_found']} found, {v1_stats['slots_generated']} generated"
    )
    print("\nV2 Repository:")
    print(
        f"Props: {v2_stats['props_found']} found, {v2_stats['props_generated']} generated"
    )
    print(
        f"Events: {v2_stats['events_found']} found, {v2_stats['events_generated']} generated"
    )
    print(
        f"Slots: {v2_stats['slots_found']} found, {v2_stats['slots_generated']} generated"
    )
