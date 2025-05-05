from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class MigrationState(BaseModel):
    v1_components: Dict[str, dict] = Field(default_factory=dict)
    v2_components: Dict[str, dict] = Field(default_factory=dict)
    component_map: Dict[str, dict] = Field(default_factory=dict)
    constraints: List[dict] = Field(default_factory=list)
    migration_plan: List[dict] = Field(default_factory=list)
    verification_rules: List[dict] = Field(default_factory=list)
    current_file: Optional[str] = None
    modified_code: Dict[str, str] = Field(default_factory=dict)
    action: str = "PENDING"
