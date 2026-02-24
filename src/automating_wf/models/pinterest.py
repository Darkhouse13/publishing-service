from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(slots=True)
class PinRecord:
    seed_keyword: str
    rank: int
    pin_url: str
    pin_id: str
    title: str
    description: str
    tags: list[str]
    engagement: dict[str, float]
    scraped_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SeedScrapeResult:
    blog_suffix: str
    seed_keyword: str
    source_url: str
    records: list[PinRecord]
    scraped_at: str
    source_file: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "blog_suffix": self.blog_suffix,
            "seed_keyword": self.seed_keyword,
            "source_url": self.source_url,
            "scraped_at": self.scraped_at,
            "source_file": self.source_file,
            "records": [record.to_dict() for record in self.records],
        }


@dataclass(slots=True)
class TrendExportRecord:
    seed_keyword: str
    keyword: str
    trend_index: float
    growth_rate: float
    consistency_score: float
    region: str
    time_range: str
    source_file: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class TrendKeywordCandidate:
    keyword: str
    hybrid_score: float
    trend_index_norm: float
    growth_norm: float
    consistency_norm: float
    source_count: int
    rank: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PinClicksExportRecord:
    keyword: str
    title: str
    description: str
    tags: list[str]
    pin_url: str
    pin_id: str
    engagement: dict[str, float]
    source_url: str
    source_file: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PinClicksKeywordScore:
    keyword: str
    total_score: float
    frequency_score: float
    engagement_score: float
    intent_score: float
    record_count: int
    trend_rank: int = 0
    pinclicks_rank: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class KeywordCandidate:
    term: str
    frequency: int
    weighted_score: float
    engagement_score: float
    title_hits: int = 0
    description_hits: int = 0
    tag_hits: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class BrainOutput:
    primary_keyword: str
    image_generation_prompt: str
    pin_text_overlay: str
    pin_title: str
    pin_description: str
    cluster_label: str
    supporting_terms: list[str] = field(default_factory=list)
    seasonal_angle: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class CsvRow:
    title: str
    description: str
    link: str
    image_url: str
    pinterest_board: str
    publish_date: str
    thumbnail: str = ""
    keywords: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "Title": self.title,
            "Media URL": self.image_url,
            "Pinterest board": self.pinterest_board,
            "Thumbnail": self.thumbnail,
            "Description": self.description,
            "Link": self.link,
            "Publish date": self.publish_date,
            "Keywords": self.keywords,
        }


@dataclass(slots=True)
class RunManifestEntry:
    run_id: str
    blog_suffix: str
    seed_keyword: str
    status: str
    event_time: str
    primary_keyword: str = ""
    idempotency_key: str = ""
    public_permalink: str = ""
    requires_wp_publish_before: str = ""
    failure_stage: str = ""
    source_stage: str = ""
    source_file: str = ""
    keyword_rank_trends: int = 0
    keyword_rank_pinclicks: int = 0
    details: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        run_id: str,
        blog_suffix: str,
        seed_keyword: str,
        status: str,
        primary_keyword: str = "",
        idempotency_key: str = "",
        public_permalink: str = "",
        requires_wp_publish_before: str = "",
        failure_stage: str = "",
        source_stage: str = "",
        source_file: str = "",
        keyword_rank_trends: int = 0,
        keyword_rank_pinclicks: int = 0,
        details: dict[str, Any] | None = None,
    ) -> "RunManifestEntry":
        return cls(
            run_id=run_id,
            blog_suffix=blog_suffix,
            seed_keyword=seed_keyword,
            status=status,
            event_time=datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            primary_keyword=primary_keyword,
            idempotency_key=idempotency_key,
            public_permalink=public_permalink,
            requires_wp_publish_before=requires_wp_publish_before,
            failure_stage=failure_stage,
            source_stage=source_stage,
            source_file=source_file,
            keyword_rank_trends=keyword_rank_trends,
            keyword_rank_pinclicks=keyword_rank_pinclicks,
            details=details or {},
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
