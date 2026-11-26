from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from .contracts import DailyFinish, RecordError, Rejection
from .analysis import Curve, points, center_scale, chronological_sample, fit, one, predict


@dataclass(frozen=True, slots=True)
class Intake:
    records: tuple[DailyFinish, ...]
    rejected: tuple[Rejection, ...]
    read_count: int

    @property
    def accepted_count(self) -> int:
        return len(self.records)

    def rejection_counts(self) -> dict[str, int]:
        return dict(sorted(Counter(item.reason for item in self.rejected).items()))

    def evidence(self) -> dict:
        return {
            "read": self.read_count,
            "accepted": self.accepted_count,
            "excluded": len(self.rejected),
            "reason_counts": self.rejection_counts(),
            "rejected": [item.evidence() for item in self.rejected],
        }


def inspect(documents: Iterable[Mapping]) -> Intake:
    accepted: list[DailyFinish] = []
    refused: list[Rejection] = []
    read_count = 0
    for read_count, document in enumerate(documents, start=1):
        try:
            entry = DailyFinish.parse(document)
        except RecordError as exc:
            raw_key = document.get('historical_lot') if isinstance(document, Mapping) else None
            identifier = str(raw_key)[:140] if raw_key is not None else ""
            refused.append(Rejection(read_count, identifier, exc.field, exc.reason))
        else:
            accepted.append(entry)
    return Intake(tuple(accepted), tuple(refused), read_count)

from .replay import recent_replay, replay_summary, replay_held_stations
