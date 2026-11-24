from typing import Literal

from pydantic import BaseModel, Field

Status = Literal["matched", "possible", "medical_only", "catalog_only"]


class Doctor(BaseModel):
    id: str
    name: str
    specialty: str | None = None
    experience: int | None = None
    clinic: str | None = None
    price: str | None = None
    first_name: str | None = Field(default=None, exclude=True)
    last_name: str | None = Field(default=None, exclude=True)


class Candidate(BaseModel):
    doctor: Doctor
    reason: str | None = None


class Comparison(BaseModel):
    id: str
    status: Status
    medical: Doctor | None = None
    catalog: list[Candidate]


class Report(BaseModel):
    medical_count: int
    medical_total: int
    catalog_count: int
    catalog_pages: int
    rows: list[Comparison]


class ErrorResponse(BaseModel):
    detail: str
