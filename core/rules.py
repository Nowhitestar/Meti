"""Platform rules-as-code: declarative per-platform constraints + lint."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol


class Severity(str, Enum):
    error = "error"
    warning = "warning"
    info = "info"


@dataclass
class Violation:
    code: str
    message: str
    severity: Severity = Severity.error
    target: str | None = None
    field_path: str | None = None


class _ManifestLike(Protocol):
    title: str
    body: str
    images: list[str]
    tags: list[str]


LintFn = Callable[[Any, str], list[Violation]]


@dataclass
class PlatformRules:
    title_max: int | None = None
    body_max: int | None = None
    image_count_min: int | None = None
    image_count_max: int | None = None
    image_aspect_ratios: list[str] | None = None
    tag_max: int | None = None
    cover_required: bool = False
    cover_aspect_ratios: list[str] | None = None
    extra_lints: list[LintFn] = field(default_factory=list)

    def lint(self, manifest: _ManifestLike, target_name: str) -> list[Violation]:
        violations: list[Violation] = []

        title = getattr(manifest, "title", "") or ""
        body = getattr(manifest, "body", "") or ""
        images = getattr(manifest, "images", []) or []
        tags = getattr(manifest, "tags", []) or []

        if self.title_max is not None and len(title) > self.title_max:
            violations.append(
                Violation(
                    code="TITLE_TOO_LONG",
                    message=f"title length {len(title)} exceeds {self.title_max}",
                    target=target_name,
                    field_path="title",
                )
            )
        if self.body_max is not None and len(body) > self.body_max:
            violations.append(
                Violation(
                    code="BODY_TOO_LONG",
                    message=f"body length {len(body)} exceeds {self.body_max}",
                    target=target_name,
                    field_path="body",
                )
            )
        if self.image_count_min is not None and len(images) < self.image_count_min:
            violations.append(
                Violation(
                    code="IMAGE_COUNT_BELOW_MIN",
                    message=f"image count {len(images)} below min {self.image_count_min}",
                    target=target_name,
                    field_path="assets.images",
                )
            )
        if self.image_count_max is not None and len(images) > self.image_count_max:
            violations.append(
                Violation(
                    code="IMAGE_COUNT_ABOVE_MAX",
                    message=f"image count {len(images)} above max {self.image_count_max}",
                    target=target_name,
                    field_path="assets.images",
                )
            )
        if self.tag_max is not None and len(tags) > self.tag_max:
            violations.append(
                Violation(
                    code="TAG_COUNT_ABOVE_MAX",
                    message=f"tag count {len(tags)} above max {self.tag_max}",
                    target=target_name,
                    field_path="tags",
                )
            )

        for fn in self.extra_lints:
            violations.extend(fn(manifest, target_name))

        return violations
