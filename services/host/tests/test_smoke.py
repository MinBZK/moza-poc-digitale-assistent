"""Smoke-tests: controleren dat de host-modules importeerbaar zijn.

Aanvullende pytest-tests volgen in vervolg-PRs. De handmatige scripts in
`services/host/scripts/` (check_vlam_toolcalling*.py, run_scenarios.py)
zijn integratie-checks die echte LLM-credentials vereisen en draaien
buiten pytest.
"""

import os


def _force_no_keys():
    os.environ["ANTHROPIC_API_KEY"] = ""
    os.environ["VLAM_API_KEY"] = ""


def test_config_importeerbaar():
    _force_no_keys()
    import config  # noqa: F401


def test_vlam_host_importeerbaar():
    _force_no_keys()
    from vlam_host import VLAMHost

    host = VLAMHost()
    status = host.get_status()
    assert status["backends"]["claude"] is False
    assert status["backends"]["vlam"] is False
