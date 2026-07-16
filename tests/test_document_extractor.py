import csv
from pathlib import Path

import pytest

from src.document_extractor import (
    extract_case_documents,
    extract_csv,
    extract_document,
    extract_xlsx,
)


@pytest.fixture
def tmp_csv(tmp_path):
    f = tmp_path / "transactions.csv"
    with open(f, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["Date", "Amount", "Merchant"])
        writer.writerow(["2025-01-01", "99.99", "NorthernThread"])
        writer.writerow(["2025-01-02", "49.50", "SkyFarers"])
    return f


@pytest.fixture
def tmp_xlsx(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Transactions"
    ws.append(["Date", "Amount", "Merchant"])
    ws.append(["2025-01-01", 99.99, "NorthernThread"])
    f = tmp_path / "transactions.xlsx"
    wb.save(f)
    return f


def test_csv_extraction_success(tmp_csv):
    result = extract_csv(tmp_csv)
    assert result["status"] == "success"
    assert result["row_count"] == 3
    assert "NorthernThread" in result["full_text"]
    assert "Date | Amount | Merchant" in result["full_text"]


def test_csv_extraction_via_dispatch(tmp_csv):
    result = extract_document(tmp_csv)
    assert result["file_type"] == "csv"
    assert result["status"] == "success"


def test_xlsx_extraction_success(tmp_xlsx):
    result = extract_xlsx(tmp_xlsx)
    assert result["status"] == "success"
    assert "NorthernThread" in result["full_text"]
    assert "Transactions" in result["full_text"]


def test_xlsx_extraction_via_dispatch(tmp_xlsx):
    result = extract_document(tmp_xlsx)
    assert result["file_type"] == "xlsx"
    assert result["status"] == "success"


def test_unknown_extension_flagged(tmp_path):
    f = tmp_path / "data.bin"
    f.write_bytes(b"\x00\x01\x02\x03")
    result = extract_document(f)
    assert result["file_type"] == "unknown"
    assert result["status"] == "needs_review"


def test_missing_file_returns_not_found(tmp_path):
    results = extract_case_documents(["ghost.pdf"], str(tmp_path))
    assert len(results) == 1
    assert results[0]["status"] == "not_found"
    assert results[0]["filename"] == "ghost.pdf"


def test_empty_csv_flagged(tmp_path):
    f = tmp_path / "empty.csv"
    f.write_text("")
    result = extract_csv(f)
    assert result["status"] == "needs_review"
