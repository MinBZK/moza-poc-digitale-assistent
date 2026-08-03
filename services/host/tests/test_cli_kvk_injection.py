"""CLI-transport bedient het sessie-KvK, niet de env-default (MVP-01/PDR-009).

De `kvk-cli`-tools lezen het KvK-nummer uit de env-var KVK_SESSIE_NUMMER; die
default is 68750110. De host moet het sessie-KvK per subprocess meegeven, anders
ziet elke gebruiker in CLI-modus hetzelfde demo-bedrijf.
"""

import cli_executor

MOCK_KVK = "85234567"


async def test_kvk_cli_krijgt_sessie_kvk_via_env(monkeypatch):
    captured = {}

    async def _fake_run_cli(cmd, env=None):
        captured["cmd"] = cmd
        captured["env"] = env
        return "{}"

    monkeypatch.setattr(cli_executor, "_run_cli", _fake_run_cli)

    await cli_executor.execute_cli_tool("kvk__mijn_bedrijf", {"kvk_nummer": MOCK_KVK})

    assert captured["env"] is not None
    assert captured["env"].get("KVK_SESSIE_NUMMER") == MOCK_KVK


def test_loggable_cmd_laat_kvk_argv_weg():
    # Het KvK-nummer staat als positional argv in de regelrecht/rvo-CLI en mag
    # niet in de logs: _loggable_cmd logt alleen scriptnaam + subcommando's/flags.
    readable = cli_executor._loggable_cmd(
        ["/pad/regelrecht-cli", "check", MOCK_KVK, "--provenance"]
    )
    assert MOCK_KVK not in readable
    assert "regelrecht-cli" in readable
    assert "check" in readable
