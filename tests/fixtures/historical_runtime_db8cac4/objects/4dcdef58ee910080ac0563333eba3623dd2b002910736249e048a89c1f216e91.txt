from pathlib import Path

import pytest

from mechanical_cad.model import load_document

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def plate():
    return load_document(ROOT / "examples" / "drilled_plate.mcad.json")
