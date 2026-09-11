from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from quinovo.language.models import QuinovoModel

RuleKind = Literal[
    "forecast_fact",
    "fact_link_fact",
    "prefix_link",
    "property_fact",
    "join_links",
    "age_fact",
]

ConfidenceSource = Literal["forecast"]


class ForecastWhen(QuinovoModel):
    metric: str
    point_gte: float


class AgeWhen(QuinovoModel):
    """A timestamp property older than N days. ISO 8601 strings only."""

    property: str
    older_than_days: float


class FactWhen(QuinovoModel):
    predicate: str
    equals: str


class PropertyWhen(QuinovoModel):
    api_name: str
    equals: str


class ThenFact(QuinovoModel):
    predicate: str
    value: str


class ThenLink(QuinovoModel):
    link_type: str
    to_type: str
    to_id: str


class InferenceRule(QuinovoModel):
    api_name: str
    kind: RuleKind
    description: str = ""
    source_type: str
    confidence: float | None = None
    confidence_from: ConfidenceSource | None = None
    when_forecast: ForecastWhen | None = None
    when_fact: FactWhen | None = None
    when_property: PropertyWhen | None = None
    when_age: AgeWhen | None = None
    when_link: str | None = None
    when_links: list[str] = Field(default_factory=list)
    when_pk_prefix: str | None = None
    then_fact: ThenFact | None = None
    then_link: ThenLink | None = None

    def resolved_confidence(self) -> float:
        """Static confidence. Forecast-sourced rules resolve at fire time."""
        return self.confidence if self.confidence is not None else 0.9

    @model_validator(mode="after")
    def premises_match_kind(self) -> InferenceRule:
        if self.confidence is not None and self.confidence_from is not None:
            raise ValueError(
                f"{self.api_name}: set confidence or confidence_from, not both"
            )
        match self.kind:
            case "forecast_fact":
                if self.when_forecast is None or self.then_fact is None:
                    raise ValueError(f"{self.api_name}: forecast_fact needs when_forecast and then_fact")
            case "fact_link_fact":
                if self.when_fact is None or self.when_link is None or self.then_fact is None:
                    raise ValueError(
                        f"{self.api_name}: fact_link_fact needs when_fact, when_link, then_fact"
                    )
            case "prefix_link":
                if self.when_pk_prefix is None or self.then_link is None:
                    raise ValueError(f"{self.api_name}: prefix_link needs when_pk_prefix and then_link")
            case "property_fact":
                if self.when_property is None or self.then_fact is None:
                    raise ValueError(
                        f"{self.api_name}: property_fact needs when_property and then_fact"
                    )
            case "join_links":
                if len(self.when_links) < 2 or self.then_fact is None:
                    raise ValueError(
                        f"{self.api_name}: join_links needs when_links (2+) and then_fact"
                    )
            case "age_fact":
                if self.when_age is None or self.then_fact is None:
                    raise ValueError(f"{self.api_name}: age_fact needs when_age and then_fact")
            case _ as unreachable:
                raise TypeError(f"unhandled rule kind: {unreachable}")
        return self


class InferenceRuleset(QuinovoModel):
    rules: list[InferenceRule] = Field(default_factory=list)
