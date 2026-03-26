from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime


@dataclass(slots=True)
class EventCandidate:
    id: str
    title: str
    description: str = ""
    why_relevant: str = ""
    confidence: str = "средний"
    outlet_fit: str = ""
    source_notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class ScenarioSet:
    event_id: str
    current_context: str = ""
    trends: list[str] = field(default_factory=list)
    base_scenario: str = ""
    cautious_scenario: str = ""
    stronger_scenario: str = ""
    selected_scenario: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class OutletStyleProfile:
    outlet_name: str
    headline_logic: str = ""
    lead_logic: str = ""
    typical_patterns: list[str] = field(default_factory=list)
    do_rules: list[str] = field(default_factory=list)
    dont_rules: list[str] = field(default_factory=list)
    generation_instruction: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class GeneratedDraft:
    model_name: str
    outlet_name: str
    event_id: str
    scenario_type: str
    variant_type: str
    headline: str
    lead: str
    why_plausible: str = ""
    selected_by_model: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class SessionManifest:
    session_id: str
    target_date: str
    chosen_outlet: str = ""
    chosen_event: str = ""
    current_step: str = "created"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    files: list[str] = field(default_factory=list)
    country: str = "Россия"
    topic: str = ""
    chosen_scenario: str = ""
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)
