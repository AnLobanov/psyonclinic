import { useEffect, useState } from "react";

import { fetchReport } from "./api";
import type { Comparison, Doctor, Report, Status } from "./types";

const STATUS_LABELS: Record<Status, string> = {
  matched: "Совпало",
  possible: "Возможно совпадение",
  medical_only: "Только в Medical API (в выборке)",
  catalog_only: "Только в Doctor Catalog (в выборке)",
};

const statuses = Object.keys(STATUS_LABELS) as Status[];
const collator = new Intl.Collator("ru");

function searchText(value: string): string {
  return value.normalize("NFKC").toLocaleLowerCase("ru").replaceAll("ё", "е")
    .replace(/[^\p{L}\p{N}]+/gu, " ").trim();
}

function displayDoctor(row: Comparison): Doctor {
  return row.medical ?? row.catalog[0].doctor;
}

function filterRows(rows: Comparison[], status: Status | "", query: string): Comparison[] {
  const terms = searchText(query).split(" ").filter(Boolean);
  return rows.filter((row) => {
    if (status && row.status !== status) return false;
    const doctors = [row.medical, ...row.catalog.map((item) => item.doctor)];
    return doctors.some((doctor) => {
      if (!doctor) return false;
      const text = searchText([doctor.name, doctor.specialty].filter(Boolean).join(" "));
      return terms.every((term) => text.includes(term));
    });
  }).sort((a, b) => collator.compare(displayDoctor(a).name, displayDoctor(b).name));
}

function StatusLabel({ status }: { status: Status }) {
  return <span className={`status ${status}`}>{STATUS_LABELS[status]}</span>;
}

const fields = [
  ["name", "ФИО"],
  ["specialty", "Специальность"],
  ["experience", "Стаж"],
  ["clinic", "Клиника"],
  ["price", "Публичная цена"],
] as const;

type Field = (typeof fields)[number][0];

function valueFor(doctor: Doctor | null, field: Field): string | null {
  const value = doctor?.[field];
  if (value == null || value === "") return null;
  return field === "experience" ? `${value} (лет)` : String(value).trim().replace(/\s+/g, " ");
}

function ComparisonDetails({ row }: { row: Comparison }) {
  const [candidateId, setCandidateId] = useState("");
  const candidate = row.catalog.find((item) => item.doctor.id === candidateId) ?? row.catalog[0];
  const catalog = candidate?.doctor ?? null;

  return (
    <section className="details" aria-labelledby="doctor-name">
      <h2 id="doctor-name">{displayDoctor(row).name}</h2>
      <StatusLabel status={row.status} />
      {row.catalog.length > 1 && (
        <label className="candidate">
          Кандидат из каталога
          <select value={catalog?.id} onChange={(event) => setCandidateId(event.target.value)}>
            {row.catalog.map(({ doctor }, index) => (
              <option key={doctor.id} value={doctor.id}>
                {index + 1}. {doctor.name} — {doctor.specialty ?? "без специальности"}
                {doctor.clinic ? ` (${doctor.clinic})` : ""}
              </option>
            ))}
          </select>
        </label>
      )}
      {candidate?.reason && <p className="reason">{candidate.reason}.</p>}
      <div className="table-wrap">
        <table aria-label="Данные из двух источников">
          <thead>
            <tr><th scope="col">Поле</th><th scope="col">Medical API</th><th scope="col">Doctor Catalog</th></tr>
          </thead>
          <tbody>
            {fields.map(([field, label]) => {
              const medicalValue = valueFor(row.medical, field);
              const catalogValue = valueFor(catalog, field);
              const differs = row.medical && catalog && field !== "clinic" && field !== "price"
                && medicalValue !== catalogValue;
              return (
                <tr key={field} className={differs ? "different" : undefined}>
                  <th scope="row">
                    {label}
                    {differs && <small>Различается</small>}
                  </th>
                  <td>{row.medical ? medicalValue ?? "—" : "Нет записи"}</td>
                  <td>{catalog ? catalogValue ?? "—" : "Нет записи"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function App() {
  const [report, setReport] = useState<Report | null>(null);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<Status | "">("");
  const [selectedId, setSelectedId] = useState("");
  const [refreshes, setRefreshes] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    fetchReport(refreshes > 0, controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) setReport(data);
      })
      .catch((failure: Error) => {
        if (!controller.signal.aborted) setError(failure.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [refreshes]);

  function refresh() {
    setError("");
    setLoading(true);
    setRefreshes((count) => count + 1);
  }

  const rows = filterRows(report?.rows ?? [], status, query);
  const selected = rows.find((row) => row.id === selectedId) ?? rows[0];

  return (
    <main>
      <header>
        <h1>Сверка врачей</h1>
        <button type="button" onClick={refresh} disabled={loading}>Обновить</button>
      </header>
      {report && (
        <p className="sources">
          Medical API: {report.medical_count} из {report.medical_total} записей
          {" · "}Doctor Catalog: {report.catalog_count} записей, страниц: {report.catalog_pages}
        </p>
      )}
      {loading && (
        <p role="status" className="notice">
          {report ? "Обновляем данные источников…" : "Загружаем данные из двух источников…"}
        </p>
      )}
      {error && (
        <p role="alert" className="notice error">
          {error}{report && " На странице результаты предыдущей загрузки."}
        </p>
      )}
      {report && (
        <>
          <div className="filters">
            <label>
              Поиск
              <input
                type="search" value={query} placeholder="ФИО или специальность"
                onChange={(event) => setQuery(event.target.value)}
              />
            </label>
            <label>
              Статус
              <select value={status} onChange={(event) => setStatus(event.target.value as Status | "")}>
                <option value="">Все статусы</option>
                {statuses.map((option) => (
                  <option key={option} value={option}>{STATUS_LABELS[option]}</option>
                ))}
              </select>
            </label>
          </div>
          {selected ? (
            <div className="layout">
              <section aria-label="Список врачей">
                <p className="count" role="status">Результаты: {rows.length} из {report.rows.length}</p>
                <ul className="list">
                  {rows.map((row) => {
                    const doctor = displayDoctor(row);
                    return (
                      <li key={row.id}>
                        <button
                          type="button" aria-pressed={row.id === selected.id}
                          onClick={() => setSelectedId(row.id)}
                        >
                          <strong>{doctor.name}</strong>
                          {doctor.specialty && <span className="specialty">{doctor.specialty}</span>}
                          <StatusLabel status={row.status} />
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </section>
              <ComparisonDetails key={selected.id} row={selected} />
            </div>
          ) : (
            <p role="status" className="notice">
              {report.rows.length ? "По выбранным условиям ничего не найдено." : "В источниках нет записей."}
            </p>
          )}
        </>
      )}
    </main>
  );
}
