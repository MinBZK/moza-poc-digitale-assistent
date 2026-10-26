# PDR-017: De DA is de bron van de rekenkern in de browser, gepind op engine en corpus

| Veld | Waarde |
|---|---|
| Status | Voorgesteld |
| Datum | 2026-10-26 |
| Beslisser(s) | Projectteam Digitale assistent 2.0 |
| Gerelateerd | [PDR-016](PDR-016-uitleg-in-gewone-taal-uit-de-beslisgraaf.md) (uitleg uit de beslisgraaf), [PDR-018](PDR-018-clientcontract-rekenkern.md) (clientcontract) |

## Context

De oriëntatie "iemand aannemen" in moza-portaal rekent in de browser met een
WASM-kern. Die kern kwam uit `regelrecht-uitleg` (privérepo, persoonlijk
account), met een eigen uitleglaag (presentaties, sjablonen, afleidingen). In
het portaal zat daarbovenop een laag met de vertaling van vier antwoorden naar
feiten, de keuze welke uitkomsten te rekenen, en de vertaling naar het scherm
(`_uitkomsten.ts`).

Drie problemen:

- De DA-repo is publiek en de kern niet. CI kan de kern niet bouwen, en de
  herkomst van wat het portaal laadt is niet na te gaan.
- De rekenlaag zat in het portaal. Een tweede afnemer moest hem kopiëren.
- Het corpus van Financieel CV staat sinds 21 oktober in een eigen repo
  (`MinBZK/regelrecht-corpus-FCV`) en is op 25 oktober gereviewd. De oude
  bundel rekende nog op `regelrecht-corpus` `42054d7d`.

De uitleglaag moet bovendien de vorm krijgen van de Graph-conditie uit het
paper (zie regelrecht.rijks.app/research/citizen-explanation), als nieuwe
functionaliteit van de DA.

## Beslissing

1. **De rekenkern is een crate in de DA**: `services/rekenkern/` (Rust,
   `da-rekenkern`). Hij bouwt naar WASM voor de browser en native voor tests
   en een CLI. Er zit geen code van regelrecht-uitleg in: de beslisgraaf,
   de uitleg en de oriëntatie zijn nieuw en eigen aan de DA.
2. **De engine is een git-dependency op een commit** van `MinBZK/regelrecht`
   (`rev` in `Cargo.toml`, nu `abfce035`, main van 26 oktober 2026). Er wordt
   geen crate gevendord en regelrecht wordt niet gewijzigd. De engine bevat
   geen wetkennis.
3. **Het corpus wordt opgehaald, niet gekopieerd.** `bronnen.json` pint de
   corpusrepo, de revisie en de git-blobhash van elke wetversie (nu
   `regelrecht-corpus-FCV` `b030cb1`, 37 wetversies). `bouw.py bundel` haalt
   elk bestand op de gepinde revisie uit een checkout of clone en stopt bij
   een afwijkende hash. Wet-YAML komt nooit in deze repo.
4. **De oriëntatielaag verhuist uit het portaal naar de kern**
   (`src/aannemen.rs`, basisfeiten in `casus/iemand-aannemen/`). De
   vertaling is overgenomen en getoetst op de referentieset (zie
   Consequenties). Twee feiten zijn aangepast aan het gereviewde corpus;
   `tests/fixtures/verwachte-verschillen.json` noemt ze, met reden.
5. **De bundel is een release-asset**: `bouw.py bundel` maakt
   `dist/rekenkern-<versie>/` en een zip. De gebruiker publiceert hem als
   GitHub-release; het portaal haalt hem op en toetst hem aan het manifest.
   Er komt geen binaire bundel in git.

## Alternatieven overwogen

- **De uitleglaag van regelrecht-uitleg als dependency.** Afgewezen: privé,
  dus niet te bouwen in de publieke DA. En de uitleg moet een nieuwe vorm
  krijgen (getypeerde graaf), niet de presentaties en sjablonen van toen.
- **regelrecht-uitleg vendoren.** Afgewezen: daarmee wordt privécode
  gepubliceerd, en de DA erft een laag die hij niet wil.
- **De graaf in JavaScript naast de engine-WASM.** Overwogen. Gekozen is Rust
  in dezelfde WASM: één artefact, de graaf werkt op de typen van de engine,
  en native tests draaien dezelfde code als de browser.
- **De bundel als map in de repo.** Afgewezen: ongeveer 10 MB per versie in de
  git-historie (2,3 MB WASM, 7,8 MB wetten; de zip is 1,9 MB). **Als npm-pakket**: vraagt een scope en publicatierechten,
  zonder winst boven een release met manifest.
- **Pinnen op `regelrecht-corpus` `42054d7d`, zoals de oude bundel.**
  Afgewezen: het FCV-corpus is de bron sinds de verhuizing. De referentietest
  laat zien dat de uitkomsten gelijk blijven (zie Consequenties).

## Consequenties

- **Gelijke uitkomsten.** `tests/fixtures/referentieset.json` legt 128
  gevallen vast (elke geldige combinatie van vraag 1, loonwaarde 60 en 100,
  uurloon € 14,99 en € 20,00, 32 uur), met de invoer en de outputs van de oude
  portaalbundel. De kern geeft op het FCV-corpus dezelfde outputs en dezelfde
  schermuitkomsten (`tests/referentie.rs`, `tests/bundel.test.mjs`). Er waren
  twee aanpassingen nodig aan de feiten: de datum
  `datum_laatst_persoon_7_lid_1_a_of_7a_lid_2_b` (bij bijstand de dag voor de
  aanvang) in plaats van de vervallen boolean, en
  `ondersteuning_is_in_overwegende_mate_op_individu_gericht` (bij WIA waar).
  Zonder die twee was loonkostensubsidie "onbekend" en faalde jobcoaching.
- **Snelheid.** Een volledige oriëntatie (tot vijf aanroepen, met graaf en
  uitleg) duurt in WASM ongeveer 25 ms; de oude kern deed ongeveer een
  seconde per aanroep.
- **Bouwen vraagt** een Rust-toolchain met target `wasm32-unknown-unknown`,
  `wasm-bindgen-cli` in exact de versie uit `Cargo.toml`, en leestoegang tot
  het corpus. Zolang `regelrecht-corpus-FCV` privé is, kan CI niet bouwen; de
  bouw gebeurt lokaal en de release is de overdracht.
- **Een nieuwe pin** (`bouw.py pin --corpus <checkout>`) laat de
  referentietest zien wat er verandert. Verschillen komen met reden in
  `verwachte-verschillen.json`, of de feitenlaag past zich aan. De test
  `verken_ontbrekende_gegevens` noemt de gegevens die het nieuwe corpus vraagt.
- **Indeling van de oriëntatielaag.** De notitie "Wat de oriëntatie bovenop
  RegelRecht doet" (regelrecht-corpus-FCV, `docs/`, 26 oktober 2026) deelt de
  laag in. In de kern betekent dat:
  - de koppeling van vraag 1 (Wfsv 38b), de UWV-uitsluiting (Pwet 7 lid 3
    onder c) en het voorbehoud bij het loonkostenvoordeel zijn wetkennis. Ze
    staan tijdelijk in `aannemen.rs`, totdat het corpus ze uitdrukt;
  - de markeringen van het corpus komen al mee in de graaf, zodat een afnemer
    het voorbehoud uit het corpus kan tonen;
  - het vraagmodel (feiten per antwoord, welke uitkomsten) blijft in de DA,
    en de schatting van de loonkosten blijft herkenbaar een schatting
    (`OPSLAG`).
