"""
Provenance tracking and licence gating for the replacement appearance corpus.

SHHQ became a problem because nobody recorded where the training data came
from or what it permitted. This module exists so that cannot happen again: an
image cannot enter a training archive unless it carries a provenance record,
and a record cannot be written for a source whose terms forbid ML training.

The policy table below is the enforcement point. It is deliberately a denylist
*and* an allowlist: unknown sources are refused, not waved through.

See DATA_LICENSES.md section 4a for the reasoning behind each entry.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Dict, Iterator, List, Optional


class LicenceError(Exception):
    """Raised when an image's source or licence forbids its use for training."""


@dataclass(frozen=True)
class SourcePolicy:
    allowed: bool
    reason: str
    # Licence identifiers accepted for this source. Empty means "any, the
    # platform licence governs".
    accepted_licences: tuple = ()
    # True when the platform lets contributors opt out of AI/ML training and
    # we therefore have to establish, per image, that they did not.
    requires_optout_check: bool = False


# Keep this table and DATA_LICENSES.md section 4a in sync.
SOURCE_POLICY: Dict[str, SourcePolicy] = {
    "pixabay": SourcePolicy(
        allowed=True,
        reason="Pixabay's content licence explicitly permits AI/ML training, "
               "subject to a per-contributor opt-out that must be honoured.",
        requires_optout_check=True,
    ),
    "flickr": SourcePolicy(
        allowed=True,
        reason="Per-image Creative Commons licensing; only public-domain and "
               "attribution licences are accepted here.",
        accepted_licences=("cc0", "publicdomain", "cc-by-4.0", "cc-by-2.0"),
    ),
    "unsplash-lite-dataset": SourcePolicy(
        allowed=True,
        reason="The Unsplash Lite Dataset terms grant ML training for internal "
               "business purposes. The general Unsplash Licence does not, and "
               "Unsplash+ forbids it outright — those are not this source.",
    ),
    "own-recording": SourcePolicy(
        allowed=True,
        reason="Recorded by us under a written commercial release. The only "
               "source that also settles model releases and likeness rights.",
    ),
    "pexels": SourcePolicy(
        allowed=False,
        reason="Pexels' Terms prohibit scraping and data mining 'including for "
               "machine learning purposes'. Using it would trade one licence "
               "problem for another.",
    ),
    "shhq": SourcePolicy(
        allowed=False,
        reason="Non-commercial research only. Its release agreement bars "
               "commercial exploitation of the images 'and any portion of the "
               "derived data', which covers finetuned weights. This is the "
               "dataset we are migrating off.",
    ),
}


@dataclass
class Record:
    """One image's provenance. Written as a line of JSONL."""

    image_id: str          # stable id, also the on-disk filename stem
    source: str            # key into SOURCE_POLICY
    source_url: str        # where a human can go to verify this
    licence: str           # licence identifier as the platform states it
    retrieved_at: str      # ISO-8601 UTC
    author: Optional[str] = None
    # "clear" once someone has confirmed the contributor did not opt out of AI
    # training. Pixabay's API does not expose this, so it starts "unknown" and
    # has to be resolved before the image can be used. See check_optout().
    ai_training_optout: str = "unknown"
    notes: str = ""
    extra: dict = field(default_factory=dict)

    def validate(self) -> None:
        policy = SOURCE_POLICY.get(self.source)
        if policy is None:
            raise LicenceError(
                f"{self.image_id}: unknown source {self.source!r}. Add it to "
                f"SOURCE_POLICY with a reasoned verdict before using it."
            )
        if not policy.allowed:
            raise LicenceError(f"{self.image_id}: source {self.source!r} is not usable. {policy.reason}")
        if policy.accepted_licences and self.licence.lower() not in policy.accepted_licences:
            raise LicenceError(
                f"{self.image_id}: licence {self.licence!r} is not accepted for "
                f"{self.source!r}. Accepted: {', '.join(policy.accepted_licences)}."
            )
        if self.ai_training_optout not in ("clear", "unknown", "opted-out"):
            raise LicenceError(f"{self.image_id}: ai_training_optout must be clear/unknown/opted-out.")
        if self.ai_training_optout == "opted-out":
            raise LicenceError(f"{self.image_id}: contributor opted out of AI training.")

    def is_training_ready(self) -> bool:
        """True when this record needs no further human check before training."""
        try:
            self.validate()
        except LicenceError:
            return False
        policy = SOURCE_POLICY[self.source]
        if policy.requires_optout_check and self.ai_training_optout != "clear":
            return False
        return True


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Manifest:
    """Append-only JSONL manifest. One Record per line, keyed by image_id."""

    def __init__(self, path: str):
        self.path = path
        self._records: Dict[str, Record] = {}
        if os.path.exists(path):
            for record in read_manifest(path):
                self._records[record.image_id] = record

    def __len__(self) -> int:
        return len(self._records)

    def __contains__(self, image_id: str) -> bool:
        return image_id in self._records

    def get(self, image_id: str) -> Optional[Record]:
        return self._records.get(image_id)

    def records(self) -> List[Record]:
        return list(self._records.values())

    def add(self, record: Record) -> None:
        """Validate and append. Refuses anything SOURCE_POLICY disallows."""
        record.validate()
        self._records[record.image_id] = record
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")

    def summary(self) -> dict:
        by_source: Dict[str, int] = {}
        by_licence: Dict[str, int] = {}
        pending = 0
        for record in self._records.values():
            by_source[record.source] = by_source.get(record.source, 0) + 1
            by_licence[record.licence] = by_licence.get(record.licence, 0) + 1
            if not record.is_training_ready():
                pending += 1
        return {
            "total": len(self._records),
            "training_ready": len(self._records) - pending,
            "pending_checks": pending,
            "by_source": by_source,
            "by_licence": by_licence,
            "generated_at": now_iso(),
        }


def read_manifest(path: str) -> Iterator[Record]:
    with open(path, "r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield Record(**json.loads(line))
            except (json.JSONDecodeError, TypeError) as error:
                raise LicenceError(f"{path}:{line_number} is not a valid provenance record: {error}")


def check_optout(manifest: Manifest) -> List[str]:
    """Return image_ids still needing a human opt-out check.

    Pixabay does not expose the AI-training opt-out through its API, so this
    cannot be automated. The list this returns is the work queue: confirm each
    on the image's page, then rewrite the record with ai_training_optout="clear".
    """
    return [
        record.image_id
        for record in manifest.records()
        if SOURCE_POLICY[record.source].requires_optout_check and record.ai_training_optout != "clear"
    ]
