"""Sessie-isolatie en deny-by-default na review-bevindingen (MVP-01/PDR-009).

Dekt:
- conversatie-buckets gepartitioneerd op identiteit (KvK), niet alleen op het
  client-gekozen session_id (anders leest een geldig token andermans historie);
- `execute_law` deny-by-default: een LLM-KvK in `parameters.KVK_NUMMER` wordt
  altijd verwijderd, en alleen de informatieplicht-regel krijgt de sessie-KvK;
- robuustheid bij een niet-dict `parameters`;
- clear_session wist ook de CLI-buckets.
"""

import vlam_host

SESSIE_A = "85234567"
SESSIE_B = "68750110"
_INFORMATIEPLICHT = "omgevingswet/energiebesparing/informatieplicht"
_MAATREGELEN = "omgevingswet/energiebesparing/maatregelen"


def test_conv_key_partitioneert_op_kvk():
    # Zelfde session_id + mode maar ander KvK => aparte bucket (geen kruislek).
    a = vlam_host.VLAMHost._conv_key(SESSIE_A, "sid-1", "vlam")
    b = vlam_host.VLAMHost._conv_key(SESSIE_B, "sid-1", "vlam")
    assert a != b


def test_conv_key_zelfde_identiteit_zelfde_bucket():
    a = vlam_host.VLAMHost._conv_key(SESSIE_A, "sid-1", "vlam")
    a2 = vlam_host.VLAMHost._conv_key(SESSIE_A, "sid-1", "vlam")
    assert a == a2


def test_clear_session_wist_alle_modi_inclusief_cli():
    host = vlam_host.VLAMHost()
    for mode in ("vlam", "claude", "cli:vlam", "cli:claude"):
        host.conversations[host._conv_key(SESSIE_A, "sid-1", mode)] = [{"x": 1}]
    # Een andere sessie mag blijven staan.
    keep = host._conv_key(SESSIE_A, "sid-2", "vlam")
    host.conversations[keep] = [{"y": 2}]

    host.clear_session("sid-1")

    assert keep in host.conversations
    assert all("sid-1" not in k for k in host.conversations)


def test_execute_law_strip_llm_kvk_voor_andere_wet():
    # Deny-by-default: bij een niet-informatieplicht-wet wordt een door het LLM
    # meegegeven KVK_NUMMER verwijderd en NIET vervangen door de sessie-waarde.
    out = vlam_host._inject_session_kvk(
        "regelrecht__execute_law",
        {"law": "een/andere/wet", "parameters": {"KVK_NUMMER": "99999999"}},
        SESSIE_A,
    )
    assert "KVK_NUMMER" not in out["parameters"]


def test_execute_law_maatregelen_strip_gesmokkelde_kvk():
    out = vlam_host._inject_session_kvk(
        "regelrecht__execute_law",
        {"law": _MAATREGELEN, "parameters": {"HEEFT_KOELINSTALLATIE": True, "KVK_NUMMER": "99999999"}},
        SESSIE_A,
    )
    assert "KVK_NUMMER" not in out["parameters"]
    assert out["parameters"]["HEEFT_KOELINSTALLATIE"] is True


def test_execute_law_informatieplicht_zet_sessie_kvk():
    out = vlam_host._inject_session_kvk(
        "regelrecht__execute_law",
        {"law": _INFORMATIEPLICHT, "parameters": {"KVK_NUMMER": "99999999"}},
        SESSIE_A,
    )
    assert out["parameters"]["KVK_NUMMER"] == SESSIE_A


def test_execute_law_niet_dict_parameters_geeft_geen_error():
    # Mag niet crashen als het LLM parameters als string stuurt.
    out = vlam_host._inject_session_kvk(
        "regelrecht__execute_law",
        {"law": _INFORMATIEPLICHT, "parameters": "kapot"},
        SESSIE_A,
    )
    assert out["parameters"]["KVK_NUMMER"] == SESSIE_A
