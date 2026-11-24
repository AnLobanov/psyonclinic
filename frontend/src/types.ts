export type Status = "matched" | "possible" | "medical_only" | "catalog_only";

export interface Doctor {
  id: string;
  name: string;
  specialty: string | null;
  experience: number | null;
  clinic: string | null;
  price: string | null;
}

export interface Candidate {
  doctor: Doctor;
  reason: string | null;
}

export interface Comparison {
  id: string;
  status: Status;
  medical: Doctor | null;
  catalog: Candidate[];
}

export interface Report {
  medical_count: number;
  medical_total: number;
  catalog_count: number;
  catalog_pages: number;
  rows: Comparison[];
}
