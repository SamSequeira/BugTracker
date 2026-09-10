"""
architecture.py
---------------
Pydantic schemas for the AI Codebase Architecture & Topology API responses.
"""

from typing import List, Optional
from pydantic import BaseModel, ConfigDict


class ArchitectureSummarySchema(BaseModel):
    """Schema representing repository intent, overview, health, and parser."""
    intent: Optional[str] = None
    architecture_overview: Optional[str] = None
    health_assessment: Optional[str] = None
    parser_version: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class TechnologySchema(BaseModel):
    """Schema representing an identified framework, runtime, library, or tool."""
    id: Optional[str] = None
    name: str
    category: str
    version: Optional[str] = None
    detection_source: Optional[str] = None
    is_primary: bool = True

    model_config = ConfigDict(from_attributes=True)


class SourceFileSchema(BaseModel):
    """Schema representing an analyzed source file under a component."""
    id: str
    file_path: str
    file_name: str
    extension: Optional[str] = None
    language: str
    line_count: Optional[int] = None
    role: Optional[str] = None
    intent: Optional[str] = None
    is_supported: bool = True

    model_config = ConfigDict(from_attributes=True)


class ArchitectureComponentSchema(BaseModel):
    """Schema representing a logical architectural layer/component with grouped source files."""
    id: str
    name: str
    component_type: Optional[str] = None
    description: Optional[str] = None
    root_path: Optional[str] = None
    source_files: List[SourceFileSchema] = []

    model_config = ConfigDict(from_attributes=True)


class ArchitectureTopologyResponse(BaseModel):
    """Top-level response payload for the Architecture & Topology (Tab 2) page."""
    analysis_run_id: str
    repository_id: Optional[str] = None
    summary: Optional[ArchitectureSummarySchema] = None
    technologies: List[TechnologySchema] = []
    primary_technologies: List[TechnologySchema] = []
    secondary_technologies: List[TechnologySchema] = []
    components: List[ArchitectureComponentSchema] = []
    uncategorized_files: List[SourceFileSchema] = []
    total_source_files: int = 0
    total_components: int = 0
    total_technologies: int = 0
    total_primary_technologies: int = 0
    total_secondary_technologies: int = 0

    model_config = ConfigDict(from_attributes=True)
