"""High-level PII scanner that wraps Presidio with Aegis Japanese recognizers."""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
from typing import Any

from presidio_analyzer import AnalyzerEngine, RecognizerResult
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_analyzer.recognizer_registry import RecognizerRegistry
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

from . import register_japanese_recognizers


logger = logging.getLogger("aegis.pii")


class Action(str, Enum):
    PASS = "pass"
    TAG_ONLY = "tag_only"
    MASK = "mask"
    REPLACE = "replace"
    HASH = "hash"
    BLOCK = "block"


@dataclass
class EntityPolicy:
    action: Action = Action.REPLACE
    keep_chars: int = 0  # mask 時に末尾に残す文字数
    placeholder: str | None = None  # replace時の文字列。Noneなら <ENTITY_TYPE>


@dataclass
class TenantPolicy:
    entities: dict[str, EntityPolicy] = field(default_factory=dict)
    fail_open: bool = False  # スキャナ障害時に通すか
    min_score: float = 0.4   # この閾値未満は無視

    def policy_for(self, entity_type: str) -> EntityPolicy:
        return self.entities.get(entity_type, EntityPolicy(action=Action.REPLACE))


@dataclass
class ScanResult:
    original_text: str
    masked_text: str
    entities: list[RecognizerResult]
    blocked: bool
    actions_applied: dict[str, int]  # 種別 → 件数


# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _build_analyzer() -> AnalyzerEngine:
    """Build the Presidio analyzer with Japanese + global recognizers."""
    nlp_config = {
        "nlp_engine_name": "spacy",
        "models": [
            {"lang_code": "ja", "model_name": "ja_core_news_md"},
            {"lang_code": "en", "model_name": "en_core_web_sm"},
        ],
    }
    nlp_engine = NlpEngineProvider(nlp_configuration=nlp_config).create_engine()

    registry = RecognizerRegistry()
    registry.load_predefined_recognizers(languages=["en"])  # global PII
    register_japanese_recognizers(registry)

    return AnalyzerEngine(
        nlp_engine=nlp_engine,
        registry=registry,
        supported_languages=["ja", "en"],
    )


@lru_cache(maxsize=1)
def _build_anonymizer() -> AnonymizerEngine:
    return AnonymizerEngine()


def _hash_value(value: str) -> str:
    """Deterministic HMAC-SHA256 of value (truncated to 12 hex chars)."""
    key = os.environ.get("AEGIS_PII_HMAC_KEY", "aegis-default-do-not-use").encode()
    digest = hmac.new(key, value.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"<HASH:{digest[:12]}>"


def _mask_keep_suffix(value: str, keep: int) -> str:
    if keep >= len(value):
        return value
    return "*" * (len(value) - keep) + value[-keep:]


def _operator_for(entity_type: str, policy: EntityPolicy) -> OperatorConfig:
    if policy.action == Action.MASK:
        return OperatorConfig(
            "mask",
            {
                "type": "mask",
                "masking_char": "*",
                "chars_to_mask": 100,
                "from_end": False,
            },
        )
    if policy.action == Action.HASH:
        return OperatorConfig("custom", {"lambda": _hash_value})
    # REPLACE (default) / TAG_ONLY / BLOCK / PASS は別途処理
    placeholder = policy.placeholder or f"<{entity_type}>"
    return OperatorConfig("replace", {"new_value": placeholder})


class PIIScanner:
    """Synchronous scanner with per-tenant policies."""

    def __init__(self, default_policy: TenantPolicy) -> None:
        self._default = default_policy
        self._analyzer = _build_analyzer()
        self._anonymizer = _build_anonymizer()

    def scan(
        self,
        text: str,
        *,
        tenant_policy: TenantPolicy | None = None,
        language: str = "ja",
    ) -> ScanResult:
        policy = tenant_policy or self._default

        try:
            findings = self._analyzer.analyze(
                text=text,
                language=language,
                score_threshold=policy.min_score,
            )
        except Exception as exc:  # noqa: BLE001 - we want full coverage
            logger.exception("PII analyzer failed: %s", exc)
            if policy.fail_open:
                return ScanResult(
                    original_text=text,
                    masked_text=text,
                    entities=[],
                    blocked=False,
                    actions_applied={},
                )
            return ScanResult(
                original_text=text,
                masked_text="",
                entities=[],
                blocked=True,
                actions_applied={"_scanner_error": 1},
            )

        # block 判定
        actions: dict[str, int] = {}
        for f in findings:
            p = policy.policy_for(f.entity_type)
            actions[f.entity_type] = actions.get(f.entity_type, 0) + 1
            if p.action == Action.BLOCK:
                return ScanResult(
                    original_text=text,
                    masked_text="",
                    entities=findings,
                    blocked=True,
                    actions_applied=actions,
                )

        # mask / replace / hash / tag_only / pass
        operators: dict[str, OperatorConfig] = {}
        active_findings: list[RecognizerResult] = []
        for f in findings:
            p = policy.policy_for(f.entity_type)
            if p.action in (Action.PASS, Action.TAG_ONLY):
                continue
            operators[f.entity_type] = _operator_for(f.entity_type, p)
            active_findings.append(f)

        if not active_findings:
            return ScanResult(
                original_text=text,
                masked_text=text,
                entities=findings,
                blocked=False,
                actions_applied=actions,
            )

        anonymized = self._anonymizer.anonymize(
            text=text,
            analyzer_results=active_findings,
            operators=operators,
        )
        return ScanResult(
            original_text=text,
            masked_text=anonymized.text,
            entities=findings,
            blocked=False,
            actions_applied=actions,
        )
