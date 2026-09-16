from dataclasses import dataclass
@dataclass(frozen=True)
class Candidate:
    item_id: str
    distance: float
