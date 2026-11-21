# Rekenkern

De regels voor "iemand aannemen met afstand tot de arbeidsmarkt", uitgerekend
in de browser van de ondernemer. Feiten en uitkomsten gaan niet naar een server.

- Contract: [`docs/rekenkern/contract.md`](../../docs/rekenkern/contract.md)
- Besluiten: [PDR-017](../../docs/decisions/PDR-017-bron-en-pinning-van-de-rekenkern.md) (bron en pinning),
  [PDR-018](../../docs/decisions/PDR-018-clientcontract-rekenkern.md) (clientcontract),
  [PDR-019](../../docs/decisions/PDR-019-reken-dit-uit-in-het-gesprek.md) (in het gesprek; voorgesteld)

## Opbouw

| Pad | Wat |
|---|---|
| `src/kern.rs` | Wetten laden, allowlist, `bereken`, `orienteer`, foutcodes |
| `src/graaf.rs` | Trace van de engine naar de minimale beslisgraaf, met markeringen |
| `src/wetboek.rs` | Opzoeken in de wet-YAML: actie, letterlijke drempels, omschrijving, eenheid, url |
| `src/uitleg.rs` | Tekst uit de graaf zonder taalmodel (`kort`, `motivering`, `volledig`, `voorbehouden`) |
| `src/aannemen.rs` | De oriëntatie: vraag 1, feiten per antwoord, welke uitkomsten, wat het scherm toont, balans |
| `src/wasm.rs` | De browserfuncties (JSON in, JSON uit) |
| `src/bin/rekenkern.rs` | CLI: `wetten`, `bereken`, `orienteer` |
| `casus/iemand-aannemen/` | Neutrale basisfeiten en leesbare namen |
| `schema/` | JSON Schema's van het contract |
| `web/` | `worker.js` en `rekenkern-node.mjs` voor de bundel |
| `bronnen.json` | Pin: engine-commit, corpusrevisie, blobhash per wetversie |
| `bouw.py` | `pin` en `bundel` |
| `tests/` | Referentieset, bedragen, schema's (Rust); de bundel in Node |

## Bouwen

Vereist: Rust met target `wasm32-unknown-unknown`, `wasm-bindgen-cli` in de
versie uit `Cargo.toml` (`0.2.114`), en een checkout van
`MinBZK/regelrecht-corpus-FCV` op de gepinde revisie.

```bash
# bundel in dist/rekenkern-<versie>/ en dist/rekenkern-<versie>.zip
uv run python services/rekenkern/bouw.py bundel --corpus ../regelrecht-corpus-FCV

# nieuwe pin na een wijziging in het corpus
uv run python services/rekenkern/bouw.py pin --corpus ../regelrecht-corpus-FCV
```

Een toolchain die een eigen `RUSTFLAGS` of `CARGO_BUILD_TARGET` zet (zoals
musl met rust-lld): `bouw.py` haalt die weg voor de WASM-stap.

## Testen

```bash
cd services/rekenkern
cargo run --release --bin rekenkern -- wetten <corpus>/regulation /tmp/wetten.json
REKENKERN_WETTEN=/tmp/wetten.json cargo test --release         # Rust: port, referentieset, bedragen, schema's
node --test tests/bundel.test.mjs                               # de gebouwde bundel, zoals een afnemer hem laadt
uv run pytest services/host/tests/test_rekenkern_bouw.py        # pinnen en ophalen (vanuit de repo-root)
```

Zonder `REKENKERN_WETTEN` draaien alleen de tests die geen wetten nodig hebben.

Bij een nieuwe pin laat `tests/referentie.rs` zien wat er ten opzichte van de
oude portaalbundel verandert. Wat ontbreekt, noemt:

```bash
REKENKERN_WETTEN=/tmp/wetten.json cargo test --release --test referentie -- --ignored --nocapture
```

`tests/fixtures/referentieset.json` is eenmalig gemaakt met
`tests/maak-referentieset.mjs` vanuit moza-portaal (de oude bundel, corpus
`42054d7d`). Maak hem niet opnieuw met de nieuwe kern: dan toetst hij niets meer.

## Publiceren

De bundel is een release-asset. Na `bouw.py bundel`:

```bash
gh release create rekenkern-v<versie> dist/rekenkern-<versie>.zip --title "Rekenkern <versie>" \
  --notes "Engine <commit>, corpus regelrecht-corpus-FCV <revisie>; zie manifest.json"
```
