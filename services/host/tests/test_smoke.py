"""Smoke-tests: controleren dat de host-modules importeerbaar zijn.

Aanvullende pytest-tests volgen in vervolg-PRs. De handmatige scripts in
`services/host/scripts/` (check_vlam_toolcalling*.py, run_scenarios.py)
zijn integratie-checks die echte LLM-credentials vereisen en draaien
buiten pytest.
"""

import os


def test_config_importeerbaar():
    # Voorkom dat een lokaal .env de test beïnvloedt.
    os.environ.setdefault("ANTHROPIC_API_KEY", "")
    os.environ.setdefault("VLAM_API_KEY", "")

    import config  # noqa: F401


def test_vlam_host_importeerbaar():
    os.environ.setdefault("ANTHROPIC_API_KEY", "")
    os.environ.setdefault("VLAM_API_KEY", "")

    from vlam_host import VLAMHost

    host = VLAMHost()
    status = host.get_status()
    assert status["backends"]["claude"] is False
    assert status["backends"]["vlam"] is False
