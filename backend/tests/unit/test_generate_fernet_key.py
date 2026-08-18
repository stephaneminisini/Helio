import subprocess
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

# The script lives at the repo root, which the api image does not carry - its
# build context is backend/. Skipping keeps `make test` green inside the
# container, while CI checks out the whole repo and runs these for real.
SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "generate-fernet-key.sh"

pytestmark = pytest.mark.skipif(
    not SCRIPT.exists(), reason=f"{SCRIPT} is outside the api image build context"
)


def run_script() -> str:
    result = subprocess.run(
        [str(SCRIPT)], capture_output=True, text=True, check=True, timeout=30
    )
    return result.stdout.strip()


def test_prints_a_key_fernet_accepts():
    key = run_script()
    assert len(key) == 44
    Fernet(key.encode())


def test_key_is_url_safe_base64():
    key = run_script()
    assert "+" not in key
    assert "/" not in key


def test_each_run_prints_a_different_key():
    assert run_script() != run_script()
