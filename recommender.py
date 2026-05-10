from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


CATALOG_PATH = Path(__file__).with_name("shl_product_catalog.json")
MAX_RECOMMENDATIONS = 10


TYPE_CODES = {
    "Knowledge & Skills": "K",
    "Personality & Behavior": "P",
    "Ability & Aptitude": "A",
    "Competencies": "C",
    "Simulations": "S",
    "Assessment Exercises": "E",
    "Development & 360": "D",
    "Biodata & Situational Judgment": "B",
}


STOPWORDS = {
    "a",
    "about",
    "actually",
    "add",
    "also",
    "an",
    "and",
    "are",
    "around",
    "assessment",
    "assessments",
    "candidate",
    "candidates",
    "can",
    "developer",
    "development",
    "description",
    "for",
    "here",
    "from",
    "give",
    "hire",
    "hiring",
    "i",
    "in",
    "is",
    "it",
    "job",
    "level",
    "me",
    "need",
    "of",
    "please",
    "role",
    "skills",
    "test",
    "tests",
    "text",
    "the",
    "to",
    "want",
    "we",
    "with",
    "who",
    "work",
    "works",
    "years",
}


OUT_OF_SCOPE_TERMS = {
    "salary",
    "compensation",
    "legal",
    "law",
    "lawsuit",
    "contract",
    "interview questions",
    "resume template",
}

PROMPT_INJECTION_TERMS = {
    "ignore previous",
    "ignore your",
    "prompt",
    "system instruction",
}


ALIASES = {
    "gsa": "Global Skills Assessment",
    "global skills": "Global Skills Assessment",
    "opq": "Occupational Personality Questionnaire OPQ32r",
    "opq32": "Occupational Personality Questionnaire OPQ32r",
    "opq32r": "Occupational Personality Questionnaire OPQ32r",
    "mq": "Motivation Questionnaire MQM5",
}


@dataclass(frozen=True)
class CatalogItem:
    name: str
    url: str
    description: str
    keys: tuple[str, ...]
    job_levels: tuple[str, ...]
    duration: str
    remote: str
    adaptive: str
    search_text: str

    @property
    def test_type(self) -> str:
        for key in self.keys:
            if key in TYPE_CODES:
                return TYPE_CODES[key]
        return "O"


def load_catalog() -> list[CatalogItem]:
    raw_items = json.loads(CATALOG_PATH.read_text(encoding="utf-8"), strict=False)
    catalog: list[CatalogItem] = []

    for item in raw_items:
        if item.get("status") != "ok":
            continue
        name = clean_text(item.get("name", ""))
        url = item.get("link", "")
        description = clean_text(item.get("description", ""))
        keys = tuple(item.get("keys") or [])
        job_levels = tuple(item.get("job_levels") or [])
        duration = clean_text(item.get("duration", ""))
        remote = clean_text(item.get("remote", ""))
        adaptive = clean_text(item.get("adaptive", ""))
        search_text = " ".join(
            [
                name,
                description,
                " ".join(keys),
                " ".join(job_levels),
                duration,
                remote,
                adaptive,
            ]
        ).lower()

        if name and url:
            catalog.append(
                CatalogItem(
                    name=name,
                    url=url,
                    description=description,
                    keys=keys,
                    job_levels=job_levels,
                    duration=duration,
                    remote=remote,
                    adaptive=adaptive,
                    search_text=search_text,
                )
            )

    return catalog


def chat(messages: list[dict[str, str]]) -> dict[str, Any]:
    latest_user = latest_user_message(messages)
    conversation = " ".join(message["content"] for message in messages if message["role"] == "user").lower()

    if is_out_of_scope(latest_user):
        return {
            "reply": "I can only help with selecting and comparing SHL assessments from the catalog.",
            "recommendations": [],
            "end_of_conversation": False,
        }

    comparison = detect_comparison(latest_user)
    if comparison:
        return compare_assessments(comparison)

    if is_vague(conversation):
        return {
            "reply": "I can help with that. What role are you hiring for, and which skills or traits should the assessment measure?",
            "recommendations": [],
            "end_of_conversation": False,
        }

    recommendations = recommend(conversation)
    if not recommendations:
        return {
            "reply": "I could not find a strong match in the SHL catalog. Please share the role title and the main skills you want to assess.",
            "recommendations": [],
            "end_of_conversation": False,
        }

    role_hint = extract_role_hint(conversation)
    reply = f"Got it. Here are {len(recommendations)} SHL assessments"
    reply += f" that fit {role_hint}." if role_hint else " that best match your requirements."

    return {
        "reply": reply,
        "recommendations": [to_recommendation(item) for item in recommendations],
        "end_of_conversation": False,
    }


def recommend(text: str) -> list[CatalogItem]:
    tokens = meaningful_tokens(text)
    desired_types = desired_catalog_types(text)
    seniority_terms = desired_seniority_terms(text)

    scored: list[tuple[int, CatalogItem]] = []
    for item in CATALOG:
        score = 0

        for token in tokens:
            if contains_token(item.name.lower(), token):
                score += 10
            elif contains_token(item.search_text, token):
                score += 3

        for catalog_type in desired_types:
            if catalog_type in item.keys:
                score += 18

        for seniority in seniority_terms:
            if seniority in " ".join(item.job_levels).lower():
                score += 5

        if text_mentions_personality(text) and "Personality & Behavior" in item.keys:
            score += 25

        score += product_quality_adjustment(item, text)

        if score > 0:
            scored.append((score, item))

    scored.sort(key=lambda pair: (pair[0], exact_name_bonus(pair[1], text)), reverse=True)
    return diversify_by_type(scored, desired_types)


def compare_assessments(names: list[str]) -> dict[str, Any]:
    matches = [find_catalog_item(name) for name in names]
    found = [item for item in matches if item]

    if len(found) < 2:
        return {
            "reply": "I can compare SHL assessments when I can identify at least two catalog items. Please use the catalog assessment names.",
            "recommendations": [],
            "end_of_conversation": False,
        }

    left, right = found[:2]
    reply = (
        f"{left.name} is categorized as {', '.join(left.keys) or 'uncategorized'} and the catalog describes it as: "
        f"{shorten(left.description)} "
        f"{right.name} is categorized as {', '.join(right.keys) or 'uncategorized'} and the catalog describes it as: "
        f"{shorten(right.description)}"
    )

    return {
        "reply": reply,
        "recommendations": [to_recommendation(left), to_recommendation(right)],
        "end_of_conversation": False,
    }


def detect_comparison(text: str) -> list[str] | None:
    lowered = text.lower()
    if not any(word in lowered for word in ("compare", "difference", "different", "versus", " vs ")):
        return None

    candidates_with_position: list[tuple[int, str]] = []
    for alias, canonical in ALIASES.items():
        match = re.search(rf"\b{re.escape(alias)}\b", lowered)
        if match:
            candidates_with_position.append((match.start(), canonical))

    for item in CATALOG:
        name = item.name.lower()
        position = lowered.find(name)
        if position >= 0:
            candidates_with_position.append((position, item.name))

    if len(candidates_with_position) >= 2:
        candidates = [name for _, name in sorted(candidates_with_position, key=lambda pair: pair[0])]
        return unique_preserving_order(candidates)[:2]

    between_match = re.search(
        r"(?:between|compare|difference between)\s+(.+?)\s+(?:and|vs|versus)\s+(.+?)[?.]?$",
        text,
        flags=re.IGNORECASE,
    )
    if between_match:
        return [between_match.group(1).strip(), between_match.group(2).strip()]

    chunks = re.split(r"\b(?:and|vs|versus|,)\b", text, flags=re.IGNORECASE)
    cleaned = [
        re.sub(r"(?i)\b(what|is|the|difference|compare|different|between)\b", "", chunk).strip(" ?.")
        for chunk in chunks
    ]
    return [chunk for chunk in cleaned if len(chunk) >= 2][:2]


def find_catalog_item(name: str) -> CatalogItem | None:
    normalized = name.lower().strip()
    if normalized in ALIASES:
        normalized = ALIASES[normalized].lower()

    if normalized in CATALOG_BY_NAME:
        return CATALOG_BY_NAME[normalized]

    for item in CATALOG:
        item_name = item.name.lower()
        if normalized and (normalized in item_name or item_name in normalized):
            return item
    return None


def is_vague(text: str) -> bool:
    tokens = meaningful_tokens(text)
    strong_tokens = [token for token in tokens if len(token) > 2]
    return len(strong_tokens) < 2 and not desired_catalog_types(text)


def is_out_of_scope(text: str) -> bool:
    lowered = text.lower()
    if any(term in lowered for term in PROMPT_INJECTION_TERMS):
        return True
    return any(term in lowered for term in OUT_OF_SCOPE_TERMS) and "assessment" not in lowered


def desired_catalog_types(text: str) -> set[str]:
    lowered = text.lower()
    desired: set[str] = set()
    if any(term in lowered for term in ("java", "python", "sql", "excel", "coding", "programming", "developer", "technical")):
        desired.add("Knowledge & Skills")
    if text_mentions_personality(lowered):
        desired.add("Personality & Behavior")
    if any(term in lowered for term in ("cognitive", "ability", "aptitude", "reasoning", "numerical", "verbal")):
        desired.add("Ability & Aptitude")
    if any(term in lowered for term in ("competency", "competencies", "leadership", "stakeholder", "communication", "manager")):
        desired.add("Competencies")
    if any(term in lowered for term in ("simulation", "situational", "judgment", "sjt")):
        desired.add("Biodata & Situational Judgment")
    return desired


def desired_seniority_terms(text: str) -> set[str]:
    terms: set[str] = set()
    if any(term in text for term in ("entry", "junior", "graduate", "fresher")):
        terms.update({"entry-level", "graduate"})
    if any(term in text for term in ("mid", "4 years", "3 years", "5 years")):
        terms.add("mid-professional")
    if any(term in text for term in ("senior", "lead", "manager")):
        terms.update({"manager", "professional individual contributor"})
    return terms


def text_mentions_personality(text: str) -> bool:
    return any(term in text for term in ("personality", "behavior", "behaviour", "opq", "culture", "traits"))


def meaningful_tokens(text: str) -> list[str]:
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9+#.]*", text.lower())
    return [word for word in words if word not in STOPWORDS and len(word) >= 2]


def exact_name_bonus(item: CatalogItem, text: str) -> int:
    return 1 if item.name.lower() in text else 0


def latest_user_message(messages: list[dict[str, str]]) -> str:
    for message in reversed(messages):
        if message["role"] == "user":
            return message["content"]
    return ""


def extract_role_hint(text: str) -> str:
    match = re.search(r"(?:hiring|hire|for)\s+(?:a|an)?\s*([a-z0-9+#. -]{3,80})", text, re.IGNORECASE)
    if not match:
        return ""
    role = match.group(1).strip(" .")
    role = re.split(r"\b(?:who|with|that|to|needs?|requiring|having)\b", role, flags=re.IGNORECASE)[0].strip()
    role = re.sub(r"\b(assessment|assessments|test|tests)\b", "", role, flags=re.IGNORECASE).strip()
    return role


def clean_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def shorten(text: str, limit: int = 260) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3].rsplit(" ", 1)[0] + "..."


def to_recommendation(item: CatalogItem) -> dict[str, str]:
    return {"name": item.name, "url": item.url, "test_type": item.test_type}


def contains_token(text: str, token: str) -> bool:
    return re.search(rf"(?<![a-z0-9+#.]){re.escape(token)}(?![a-z0-9+#.])", text) is not None


def product_quality_adjustment(item: CatalogItem, text: str) -> int:
    name = item.name.lower()
    adjustment = 0

    if "report" in name or "guide" in name or "profiler cards" in name:
        adjustment -= 12
    if "solution" in name:
        adjustment -= 20
    if "questionnaire" in name or "assessment" in name:
        adjustment += 8
    if "opq" in text and "occupational personality questionnaire" in name:
        adjustment += 30
    if "gsa" in text and name == "global skills assessment":
        adjustment += 30

    return adjustment


def diversify_by_type(scored: list[tuple[int, CatalogItem]], desired_types: set[str]) -> list[CatalogItem]:
    selected: list[CatalogItem] = []
    selected_urls: set[str] = set()

    for catalog_type in desired_types:
        for _, item in scored:
            if item.url not in selected_urls and catalog_type in item.keys:
                selected.append(item)
                selected_urls.add(item.url)
                break

    for _, item in scored:
        if item.url in selected_urls:
            continue
        selected.append(item)
        selected_urls.add(item.url)
        if len(selected) >= MAX_RECOMMENDATIONS:
            break

    return selected[:MAX_RECOMMENDATIONS]


def unique_preserving_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.lower()
        if key not in seen:
            result.append(value)
            seen.add(key)
    return result


CATALOG = load_catalog()
CATALOG_BY_NAME = {item.name.lower(): item for item in CATALOG}
