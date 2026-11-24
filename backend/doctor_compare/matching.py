import re
import unicodedata
from collections import Counter

from .models import Candidate, Comparison, Doctor

SPECIALTY_ALIASES = {
    "лор": "оториноларинголог",
    "отоларинголог": "оториноларинголог",
    "окулист": "офтальмолог",
    "невропатолог": "невролог",
}


def words(value: str) -> tuple[str, ...]:
    value = unicodedata.normalize("NFKC", value).casefold().replace("ё", "е")
    return tuple(re.findall(r"[^\W_]+", value))


def specialty_key(value: str | None) -> str:
    parts = words(value or "")
    if parts[:1] == ("врач",):
        parts = parts[1:]
    key = " ".join(parts)
    return SPECIALTY_ALIASES.get(key, key)


def full_name(parts: tuple[str, ...]) -> bool:
    return len(parts) >= 3 and all(len(part) > 1 for part in parts)


def one_edit(left: str, right: str) -> bool:
    if len(left) > len(right):
        left, right = right, left
    if len(right) - len(left) > 1:
        return False
    for i, (a, b) in enumerate(zip(left, right)):
        if a != b:
            if len(left) < len(right):
                return left[i:] == right[i + 1:]
            return left[i + 1:] == right[i + 1:] or (
                left[i:i + 2] == right[i:i + 2][::-1] and left[i + 2:] == right[i + 2:]
            )
    return len(right) - len(left) == 1


def compatible_initials(left: list[str], right: list[str]) -> bool:
    if Counter(part[0] for part in left) != Counter(part[0] for part in right):
        return False
    # Each unmatched full part needs an unused initial on the opposite side.
    return (
        Counter(part[0] for part in left if len(part) > 1)
        <= Counter(part for part in right if len(part) == 1)
        and Counter(part[0] for part in right if len(part) > 1)
        <= Counter(part for part in left if len(part) == 1)
    )


def name_evidence(
    left: tuple[str, ...], right: tuple[str, ...], required: Counter[str],
) -> str | None:
    if left == right and len(left) >= 2:
        if all(len(part) == 1 for part in left):
            return None
        return "ФИО совпадает" if full_name(left) else "Совпадает неполное ФИО"

    left_counts, right_counts = Counter(left), Counter(right)
    if left_counts == right_counts:
        if len(left) >= 2 and any(len(part) > 1 for part in left):
            return "Части ФИО записаны в другом порядке"
        return None

    shared = left_counts & right_counts
    left_only = list((left_counts - shared).elements())
    right_only = list((right_counts - shared).elements())
    has_required_names = bool(required and required <= shared)
    if has_required_names and (not left_only or not right_only):
        return "В одном источнике пропущена часть ФИО"

    if shared and any(len(part) > 1 for part in shared) and compatible_initials(left_only, right_only):
        return "Часть ФИО записана инициалами"

    if len(left_only) == len(right_only) == 1 and full_name(left) and full_name(right):
        a, b = left_only[0], right_only[0]
        if min(len(a), len(b)) >= 4 and one_edit(a, b):
            return "В одной части ФИО возможна опечатка"

    if has_required_names and left_only and right_only:
        return "Совпадают фамилия и имя, остальные части ФИО различаются"
    return None


def compare(medical: list[Doctor], catalog: list[Doctor]) -> list[Comparison]:
    catalog_keys = [(item, words(item.name), specialty_key(item.specialty)) for item in catalog]
    candidates: dict[str, list[Candidate]] = {}
    for doctor in medical:
        name = words(doctor.name)
        first = words(doctor.first_name or "")
        last = words(doctor.last_name or "")
        required = Counter(first + last) if first and last and all(
            len(part) > 1 for part in first + last
        ) else Counter()
        specialty = specialty_key(doctor.specialty)
        items = candidates[doctor.id] = []
        for other, other_name, other_specialty in catalog_keys:
            same_specialty = bool(specialty and specialty == other_specialty)
            if full_name(name) and name == other_name and same_specialty:
                items.append(Candidate(doctor=other))
                continue

            evidence = name_evidence(name, other_name, required)
            if not evidence:
                continue
            same_full_name = full_name(name) and sorted(name) == sorted(other_name)
            if not (same_specialty or same_full_name):
                continue
            if not specialty or not other_specialty:
                evidence += ", специальность указана не в обоих источниках"
            elif not same_specialty:
                evidence += ", специальности различаются"
            items.append(Candidate(doctor=other, reason=evidence))

    claims = Counter(
        candidate.doctor.id for items in candidates.values() for candidate in items
    )
    # Даже точная пара требует проверки, когда у одной из записей есть другой кандидат.
    rows = []
    for doctor in medical:
        items = candidates[doctor.id]
        if len(items) == 1 and items[0].reason is None and claims[items[0].doctor.id] == 1:
            rows.append(Comparison(
                id=f"medical:{doctor.id}", status="matched", medical=doctor, catalog=items,
            ))
            continue

        items.sort(key=lambda candidate: candidate.reason is not None)
        for candidate in items:
            reason = candidate.reason
            if reason is None:
                reason = "ФИО и специальность совпадают"
                if len(items) > 1:
                    reason += ". Есть другие подходящие карточки каталога"
            if claims[candidate.doctor.id] > 1:
                reason += ". Карточка подходит нескольким записям Medical API"
            candidate.reason = reason
        rows.append(Comparison(
            id=f"medical:{doctor.id}", status="possible" if items else "medical_only",
            medical=doctor, catalog=items,
        ))

    for doctor in catalog:
        if doctor.id not in claims:
            rows.append(Comparison(
                id=f"catalog:{doctor.id}", status="catalog_only",
                catalog=[Candidate(doctor=doctor)],
            ))
    return rows
