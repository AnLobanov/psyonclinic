from doctor_compare.matching import compare
from doctor_compare.models import Doctor


def doctor(id, name="Иванов Пётр Сергеевич", specialty="Терапевт", experience=10):
    return Doctor(
        id=id, name=name, specialty=specialty, experience=experience,
    )


def medical_doctor():
    return doctor("1").model_copy(update={"first_name": "Пётр", "last_name": "Иванов"})


def test_normalized_match_preserves_source_values():
    [row] = compare(
        [doctor("1")],
        [doctor("a", "  Иванов Петр Сергеевич", "Врач-терапевт", 12)],
    )
    assert row.status == "matched"
    assert row.medical.experience == 10
    assert row.catalog[0].doctor.experience == 12


def test_typo_and_initials_are_possible():
    for name in ("Иванов Петр Сергевич", "Иванов П. С."):
        [row] = compare([doctor("1")], [doctor("a", name)])
        assert row.status == "possible"
        assert row.catalog[0].reason


def test_specialty_conflict_and_unrelated_doctor():
    rows = compare(
        [doctor("1")],
        [doctor("a", specialty="Хирург"), doctor("b", "Петрова Анна Ильинична")],
    )
    assert {row.status for row in rows} == {"possible", "catalog_only"}


def test_same_surname_given_name_and_specialty_with_different_patronymic_is_possible():
    [row] = compare([medical_doctor()], [doctor("a", "Иванов Пётр Андреевич")])
    assert row.status == "possible"
    assert "остальные части ФИО различаются" in row.catalog[0].reason


def test_reordered_initials_are_possible():
    [row] = compare([doctor("1")], [doctor("a", "П. С. Иванов")])
    assert row.status == "possible"
    assert "инициалами" in row.catalog[0].reason


def test_reordered_two_part_name_is_reported_as_reordered():
    medical = Doctor(
        id="m", name="Иванов Пётр", first_name="Пётр", last_name="Иванов",
        specialty="Терапевт",
    )
    [row] = compare([medical], [doctor("a", "Пётр Иванов")])
    assert row.status == "possible"
    assert "другом порядке" in row.catalog[0].reason


def test_missing_additional_names_with_reordered_compound_surname():
    medical = Doctor(
        id="m", name="де ла Крус Ана Мария Луиса",
        first_name="Ана", last_name="де ла Крус", specialty="Терапевт",
    )
    [row] = compare([medical], [doctor("a", "Ана де ла Крус")])
    assert row.status == "possible"
    assert "пропущена часть ФИО" in row.catalog[0].reason


def test_reordered_full_name_with_different_specialty_is_possible():
    [row] = compare([doctor("1")], [doctor("a", "Пётр Сергеевич Иванов", "Хирург")])
    assert row.status == "possible"
    assert "другом порядке" in row.catalog[0].reason
    assert "специальности различаются" in row.catalog[0].reason


def test_repeated_initials_cannot_reuse_one_name_part():
    rows = compare([doctor("1")], [doctor("a", "П. П. Иванов")])
    assert {row.status for row in rows} == {"medical_only", "catalog_only"}


def test_matching_initials_without_any_full_part_are_not_enough():
    rows = compare([doctor("1", "Д. А.")], [doctor("a", "Д. А.")])
    assert {row.status for row in rows} == {"medical_only", "catalog_only"}


def test_same_incomplete_name_requires_same_specialty():
    rows = compare(
        [doctor("1", "Иванов Пётр")], [doctor("a", "Иванов Пётр", "Хирург")]
    )
    assert {row.status for row in rows} == {"medical_only", "catalog_only"}


def test_same_surname_and_patronymic_are_not_enough():
    rows = compare([medical_doctor()], [doctor("a", "Иванов Максим Сергеевич")])
    assert {row.status for row in rows} == {"medical_only", "catalog_only"}


def test_duplicate_candidates_are_all_visible():
    [row] = compare([doctor("1")], [doctor("a"), doctor("b")])
    assert row.status == "possible"
    assert {item.doctor.id for item in row.catalog} == {"a", "b"}
    assert all(item.reason for item in row.catalog)


def test_exact_card_and_reordered_card_both_require_review():
    medical = [doctor("1", "Иванов Иван Иванович")]
    catalog = [
        doctor("a", "Иванов Иван Иванович"),
        doctor("b", "Иван Иванов Иванович"),
    ]
    for cards in (catalog, catalog[::-1]):
        [row] = compare(medical, cards)
        assert row.status == "possible"
        assert [item.doctor.id for item in row.catalog] == ["a", "b"]
        assert "другом порядке" in row.catalog[1].reason


def test_catalog_card_with_two_medical_candidates_requires_review():
    rows = compare(
        [doctor("1"), doctor("2", "Пётр Иванов Сергеевич")], [doctor("a")]
    )
    assert len(rows) == 2 and all(row.status == "possible" for row in rows)
    assert all(row.catalog[0].doctor.id == "a" for row in rows)
    assert all("нескольким записям" in row.catalog[0].reason for row in rows)


def test_typo_candidate_is_visible_alongside_exact_card():
    [row] = compare([doctor("1")], [doctor("a"), doctor("b", "Иванов Пётр Сергевич")])
    assert row.status == "possible"
    assert [item.doctor.id for item in row.catalog] == ["a", "b"]
    assert "опечатка" in row.catalog[1].reason


def test_alone_on_either_side():
    rows = compare([doctor("1")], [doctor("a", "Петрова Анна Ильинична")])
    assert {row.status for row in rows} == {"medical_only", "catalog_only"}
