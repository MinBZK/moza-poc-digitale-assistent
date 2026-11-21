"""Bouwstraat van de rekenkern (PDR-017): pinnen en ophalen met blobhash-toets.

Draait op een tijdelijk git-corpus, zonder netwerk en zonder Rust: de WASM-stap
zelf zit in `bundel()` en wordt hier niet aangeroepen.
"""

import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest

BOUW_PAD = Path(__file__).resolve().parents[2] / "rekenkern" / "bouw.py"
spec = importlib.util.spec_from_file_location("rekenkern_bouw", BOUW_PAD)
bouw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bouw)

ENGINE = "a" * 40


def _git(map_: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(map_), "-c", "user.name=t", "-c", "user.email=t@t", *args],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


@pytest.fixture
def corpus(tmp_path: Path) -> Path:
    """Een corpus met twee wetversies, een status-bestand en een scenario."""
    c = tmp_path / "corpus"
    for pad, inhoud in {
        "regulation/nl/wet/a/2026-07-01.yaml": "$id: a\nvalid_from: '2026-07-01'\n",
        "regulation/nl/wet/a/2025-01-01.yaml": "$id: a\nvalid_from: '2025-01-01'\n",
        "regulation/nl/wet/a/status.yaml": "status: harvested\n",
        "regulation/nl/wet/a/scenarios/x.yaml": "geen: wet\n",
        "docs/leesmij.md": "niet meenemen\n",
    }.items():
        (c / pad).parent.mkdir(parents=True, exist_ok=True)
        (c / pad).write_text(inhoud)
    _git(c.parent, "init", "-q", str(c))
    _git(c, "add", "-A")
    _git(c, "commit", "-qm", "corpus")
    return c


@pytest.fixture
def bronnen(tmp_path: Path, monkeypatch) -> Path:
    """Een eigen bronnen.json en Cargo.toml, zodat de echte pin niet verandert."""
    b = tmp_path / "bronnen.json"
    b.write_text(json.dumps({
        "engine": {"repo": "MinBZK/regelrecht", "revisie": ""},
        "corpus": {"repo": "x/y", "url": "file:///niet", "revisie": "", "bestanden": {}},
        "contract": "1.0.0",
    }))
    cargo = tmp_path / "Cargo.toml"
    cargo.write_text(f'[package]\nversion = "0.0.1"\n[dependencies]\nregelrecht-engine = {{ git = "x", rev = "{ENGINE}" }}\n')
    monkeypatch.setattr(bouw, "BRONNEN", b)
    monkeypatch.setattr(bouw, "CARGO", cargo)
    return b


def test_blobhash_is_die_van_git(corpus):
    pad = corpus / "regulation/nl/wet/a/2026-07-01.yaml"
    assert bouw.blobhash(pad.read_bytes()) == _git(corpus, "hash-object", str(pad))


@pytest.mark.parametrize(
    ("pad", "verwacht"),
    [
        ("regulation/nl/wet/a/2026-07-01.yaml", True),
        ("regulation/nl/wet/a/status.yaml", False),
        ("regulation/nl/wet/a/scenarios/x.yaml", False),
        ("docs/regulation/a.yaml", False),
        ("regulation/nl/wet/a/2026-07-01.yml", False),
    ],
)
def test_alleen_wetversies(pad, verwacht):
    assert bouw.is_wetversie(pad) is verwacht


def test_pin_legt_revisie_engine_en_alleen_wetversies_vast(corpus, bronnen):
    b = bouw.pin(corpus, None)
    assert b["engine"]["revisie"] == ENGINE
    assert b["corpus"]["revisie"] == _git(corpus, "rev-parse", "HEAD")
    assert sorted(b["corpus"]["bestanden"]) == [
        "regulation/nl/wet/a/2025-01-01.yaml",
        "regulation/nl/wet/a/2026-07-01.yaml",
    ]
    assert json.loads(bronnen.read_text()) == b


def test_haal_wetten_op_de_gepinde_revisie_ook_als_de_checkout_verder_is(corpus, bronnen):
    b = bouw.pin(corpus, None)
    (corpus / "regulation/nl/wet/a/2026-07-01.yaml").write_text("$id: a\nvalid_from: '2026-07-01'\nnieuw: 1\n")
    _git(corpus, "commit", "-qam", "verder")
    wetten = bouw.haal_wetten(corpus, b)
    assert "nieuw" not in wetten["regulation/nl/wet/a/2026-07-01.yaml"]
    assert len(wetten) == 2


def test_afwijkende_blobhash_stopt_de_bouw(corpus, bronnen):
    b = bouw.pin(corpus, None)
    b["corpus"]["bestanden"]["regulation/nl/wet/a/2025-01-01.yaml"] = "0" * 40
    with pytest.raises(bouw.BouwFout, match="blobhash wijkt af"):
        bouw.haal_wetten(corpus, b)


def test_onbekende_revisie_stopt_de_bouw(corpus, bronnen):
    b = bouw.pin(corpus, None)
    b["corpus"]["revisie"] = "f" * 40
    with pytest.raises(bouw.BouwFout, match="staat niet in"):
        bouw.haal_wetten(corpus, b)


def test_corpus_zonder_wetversies_wordt_niet_gepind(tmp_path, bronnen):
    leeg = tmp_path / "leeg"
    (leeg / "regulation").mkdir(parents=True)
    (leeg / "regulation" / "status.yaml").write_text("x: 1\n")
    _git(tmp_path, "init", "-q", str(leeg))
    _git(leeg, "add", "-A")
    _git(leeg, "commit", "-qm", "leeg")
    with pytest.raises(bouw.BouwFout, match="Geen wetversies"):
        bouw.pin(leeg, None)


def test_bundel_weigert_als_engine_pin_en_cargo_verschillen(corpus, bronnen, tmp_path):
    bouw.pin(corpus, None)
    b = json.loads(bronnen.read_text())
    b["engine"]["revisie"] = "b" * 40
    bronnen.write_text(json.dumps(b))
    with pytest.raises(bouw.BouwFout, match="engine-revisie"):
        bouw.bundel(corpus, tmp_path / "dist", wasm=False)


def test_bundel_zonder_wasm_schrijft_wetten_manifest_en_zip(corpus, bronnen, tmp_path, monkeypatch):
    web = tmp_path / "web"
    web.mkdir()
    for naam in ("worker.js", "rekenkern-node.mjs"):
        (web / naam).write_text("// test\n")
    schema = tmp_path / "schema"
    schema.mkdir()
    (schema / "verzoek.schema.json").write_text("{}")
    monkeypatch.setattr(bouw, "WEB", web)
    monkeypatch.setattr(bouw, "SCHEMA", schema)
    bouw.pin(corpus, None)
    doel = bouw.bundel(corpus, tmp_path / "dist", wasm=False)
    manifest = json.loads((doel / "manifest.json").read_text())
    assert manifest["corpus"]["wetversies"] == 2
    assert manifest["engine"]["revisie"] == ENGINE
    assert set(manifest["bestanden"]) >= {"wetten.json", "worker.js", "schema/verzoek.schema.json"}
    wetten = json.loads((doel / "wetten.json").read_text())["wetten"]
    assert manifest["bestanden"]["wetten.json"] == bouw.sha256((doel / "wetten.json").read_bytes())
    assert len(wetten) == 2
    assert (tmp_path / "dist" / f"{doel.name}.zip").exists()
    shutil.rmtree(doel)
