import inspect
from pathlib import Path
import pytest
from app.providers.kite_provider import KitePortfolioReader

FORBIDDEN_CALLS = [
    "place_order",
    "modify_order",
    "cancel_order",
    "convert_position",
    "place_gtt",
    "modify_gtt",
    "delete_gtt",
]


def test_no_forbidden_broker_order_endpoints_in_repo():
    """Rule 1: Verify that no order placement, modification, cancellation, or GTT-mutating
    endpoints exist anywhere in the application repository.
    """
    repo_root = Path(__file__).resolve().parent.parent.parent
    backend_app_dir = repo_root / "backend" / "app"

    found_violations = []

    for py_file in backend_app_dir.rglob("*.py"):
        # Skip this test file or pycache
        if "tests" in py_file.parts or "__pycache__" in py_file.parts:
            continue

        with open(py_file, "r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                clean_line = line.strip()
                # Skip comments explaining the prohibition
                if clean_line.startswith("#") or clean_line.startswith('"""') or clean_line.startswith("'''"):
                    continue
                for forbidden in FORBIDDEN_CALLS:
                    if f"def {forbidden}" in clean_line or f".{forbidden}(" in clean_line:
                        found_violations.append(f"{py_file.name}:{line_no} -> {clean_line}")

    assert (
        len(found_violations) == 0
    ), f"Rule 1 Violation! Found forbidden broker mutating calls:\n" + "\n".join(found_violations)


def test_kite_portfolio_reader_strictly_read_only():
    """Verify that KitePortfolioReader exposes ONLY read methods."""
    reader = KitePortfolioReader()
    methods = [
        m for m in dir(reader) if not m.startswith("_") and callable(getattr(reader, m))
    ]

    for m in methods:
        for forbidden in FORBIDDEN_CALLS:
            assert forbidden not in m.lower(), f"Forbidden method {m} found in KitePortfolioReader!"

    allowed_methods = {
        "is_configured",
        "is_authenticated",
        "get_login_url",
        "exchange_request_token",
        "profile",
        "funds",
        "holdings",
        "positions",
        "orders",
        "trades",
        "status",
    }
    assert set(methods).issubset(
        allowed_methods
    ), f"Unexpected methods in read-only client: {set(methods) - allowed_methods}"

