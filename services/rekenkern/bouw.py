"""Bouwstraat van de rekenkern: pinnen, ophalen, toetsen, bundelen.

De bundel is wat een afnemer (het portaal) in de browser laadt: de WASM-kern,
de wetversies van het gepinde corpus, een worker en een manifest met een hash
per bestand. Wet-YAML komt nooit in deze repo; hij wordt bij het bouwen uit het
corpus gehaald en tegen de blobhash in `bronnen.json` getoetst.

    uv run python services/rekenkern/bouw.py pin --corpus <checkout> [--revisie <sha>]
    uv run python services/rekenkern/bouw.py bundel [--corpus <checkout>] [--uit dist]

Zonder `--corpus` haalt `bundel` het corpus op via `corpus.url` in
`bronnen.json` (een git-clone in `services/rekenkern/.bron/`, buiten git), of
gebruikt de checkout uit de omgevingsvariabele `CORPUS_FCV_ROOT`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

HIER = Path(__file__).resolve().parent
BRONNEN = HIER / "bronnen.json"
CARGO = HIER / "Cargo.toml"
WEB = HIER / "web"
SCHEMA = HIER / "schema"


class BouwFout(Exception):
    """Een fout die de bouw stopt; de tekst zegt wat er mis is en wat te doen."""


def git(map_: Path, *args: str) -> bytes:
    r = subprocess.run(["git", "-C", str(map_), *args], capture_output=True)
    if r.returncode != 0:
        raise BouwFout(f"git {' '.join(args)} in {map_}: {r.stderr.decode().strip()}")
    return r.stdout


def blobhash(inhoud: bytes) -> str:
    """De git-blobhash van een bestand, zoals `git hash-object` hem geeft."""
    return hashlib.sha1(b"blob %d\0" % len(inhoud) + inhoud).hexdigest()


def sha256(inhoud: bytes) -> str:
    return hashlib.sha256(inhoud).hexdigest()


def is_wetversie(pad: str) -> bool:
    """Een wetversie: `regulation/**/<datum>.yaml`, geen status of scenario."""
    return (
        pad.startswith("regulation/")
        and pad.endswith(".yaml")
        and not pad.endswith("/status.yaml")
        and "/scenarios/" not in pad
    )


def lees_bronnen() -> dict:
    return json.loads(BRONNEN.read_text())


def engine_revisie_in_cargo() -> str:
    m = re.search(r'regelrecht-engine = \{[^}]*rev = "([0-9a-f]{40})"', CARGO.read_text())
    if not m:
        raise BouwFout("Cargo.toml pint regelrecht-engine niet op een volledige commit (rev).")
    return m.group(1)


def pin(corpus: Path, revisie: str | None) -> dict:
    """Legt de corpus-revisie en de blobhash van elke wetversie vast in bronnen.json."""
    rev = git(corpus, "rev-parse", revisie or "HEAD").decode().strip()
    regels = git(corpus, "ls-tree", "-r", rev, "regulation").decode().splitlines()
    bestanden = {}
    for regel in regels:
        meta, pad = regel.split("\t", 1)
        if is_wetversie(pad):
            bestanden[pad] = meta.split()[2]
    if not bestanden:
        raise BouwFout(f"Geen wetversies onder regulation/ op {rev}.")
    bronnen = lees_bronnen()
    bronnen["engine"]["revisie"] = engine_revisie_in_cargo()
    bronnen["corpus"]["revisie"] = rev
    bronnen["corpus"]["bestanden"] = dict(sorted(bestanden.items()))
    BRONNEN.write_text(json.dumps(bronnen, ensure_ascii=False, indent=2) + "\n")
    return bronnen


def corpus_map(opgegeven: Path | None, bronnen: dict) -> Path:
    if opgegeven:
        return opgegeven
    if os.environ.get("CORPUS_FCV_ROOT"):
        return Path(os.environ["CORPUS_FCV_ROOT"])
    cache = HIER / ".bron" / "corpus"
    if not cache.exists():
        cache.parent.mkdir(parents=True, exist_ok=True)
        r = subprocess.run(["git", "clone", "--quiet", bronnen["corpus"]["url"], str(cache)])
        if r.returncode != 0:
            raise BouwFout(
                f"Kon {bronnen['corpus']['url']} niet clonen. Geef een checkout mee met "
                "--corpus of CORPUS_FCV_ROOT."
            )
    return cache


def haal_wetten(corpus: Path, bronnen: dict) -> dict[str, str]:
    """Haalt elke gepinde wetversie op de gepinde revisie en toetst de blobhash."""
    rev = bronnen["corpus"]["revisie"]
    try:
        git(corpus, "cat-file", "-e", f"{rev}^{{commit}}")
    except BouwFout as e:
        raise BouwFout(
            f"Revisie {rev} staat niet in {corpus}. Haal hem op (git fetch) of pin opnieuw."
        ) from e
    wetten = {}
    for pad, verwacht in bronnen["corpus"]["bestanden"].items():
        inhoud = git(corpus, "show", f"{rev}:{pad}")
        if blobhash(inhoud) != verwacht:
            raise BouwFout(f"{pad}: blobhash wijkt af van de pin ({verwacht}).")
        wetten[pad] = inhoud.decode("utf-8")
    return wetten


def bouw_wasm(doel: Path) -> None:
    """Bouwt de kern naar wasm32 en maakt er met wasm-bindgen een ES-module van."""
    cargo_versie = re.search(r'wasm-bindgen = \{ version = "=([0-9.]+)"', CARGO.read_text())
    cli = subprocess.run(["wasm-bindgen", "--version"], capture_output=True, text=True)
    if cli.returncode != 0 or not cargo_versie or cargo_versie.group(1) not in cli.stdout:
        raise BouwFout(
            "wasm-bindgen ontbreekt of heeft niet de versie uit Cargo.toml "
            f"({cargo_versie.group(1) if cargo_versie else '?'}): "
            "cargo install wasm-bindgen-cli --version <versie>."
        )
    omgeving = {k: v for k, v in os.environ.items() if k not in ("RUSTFLAGS", "CARGO_BUILD_TARGET")}
    stappen = [
        ["cargo", "build", "--release", "--lib", "--features", "wasm", "--target", "wasm32-unknown-unknown"],
        [
            "wasm-bindgen", "--target", "web", "--out-dir", str(doel),
            str(HIER / "target/wasm32-unknown-unknown/release/da_rekenkern.wasm"),
        ],
    ]
    for stap in stappen:
        if subprocess.run(stap, cwd=HIER, env=omgeving).returncode != 0:
            raise BouwFout(f"Mislukt: {' '.join(stap)}")


def crate_versie() -> str:
    m = re.search(r'^version = "([^"]+)"', CARGO.read_text(), re.M)
    if not m:
        raise BouwFout("Geen versie in Cargo.toml.")
    return m.group(1)


def bundel(corpus: Path | None, uit: Path, wasm: bool = True) -> Path:
    bronnen = lees_bronnen()
    if bronnen["engine"]["revisie"] != engine_revisie_in_cargo():
        raise BouwFout("De engine-revisie in bronnen.json en Cargo.toml verschilt; draai pin opnieuw.")
    wetten = haal_wetten(corpus_map(corpus, bronnen), bronnen)
    versie = crate_versie()
    doel = uit / f"rekenkern-{versie}"
    if doel.exists():
        shutil.rmtree(doel)
    (doel / "pkg").mkdir(parents=True)
    if wasm:
        bouw_wasm(doel / "pkg")
    (doel / "wetten.json").write_text(json.dumps({"wetten": wetten}, ensure_ascii=False))
    for bron in (WEB / "worker.js", WEB / "rekenkern-node.mjs"):
        shutil.copy(bron, doel / bron.name)
    shutil.copytree(SCHEMA, doel / "schema")
    bestanden = {
        str(p.relative_to(doel)): sha256(p.read_bytes())
        for p in sorted(doel.rglob("*"))
        if p.is_file() and p.suffix != ".ts"
    }
    manifest = {
        "naam": "da-rekenkern",
        "versie": versie,
        "engine": {"repo": bronnen["engine"]["repo"], "revisie": bronnen["engine"]["revisie"]},
        "corpus": {
            "repo": bronnen["corpus"]["repo"],
            "revisie": bronnen["corpus"]["revisie"],
            "wetversies": len(wetten),
        },
        "contract": bronnen["contract"],
        "bestanden": bestanden,
    }
    (doel / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    zip_pad = uit / f"rekenkern-{versie}.zip"
    with zipfile.ZipFile(zip_pad, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(doel.rglob("*")):
            if p.is_file():
                z.write(p, Path(doel.name) / p.relative_to(doel))
    return doel


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="commando", required=True)
    p_pin = sub.add_parser("pin", help="corpus-revisie en blobhashes vastleggen in bronnen.json")
    p_pin.add_argument("--corpus", type=Path, required=True)
    p_pin.add_argument("--revisie")
    p_bundel = sub.add_parser("bundel", help="de browserbundel bouwen")
    p_bundel.add_argument("--corpus", type=Path)
    p_bundel.add_argument("--uit", type=Path, default=HIER.parents[1] / "dist")
    a = p.parse_args(argv)
    try:
        if a.commando == "pin":
            b = pin(a.corpus, a.revisie)
            print(f"gepind: corpus {b['corpus']['revisie'][:12]}, {len(b['corpus']['bestanden'])} wetversies")
        else:
            doel = bundel(a.corpus, a.uit)
            print(f"bundel: {doel}")
    except BouwFout as e:
        print(f"bouw gestopt: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
