# Changelog

Alle noemenswaardige wijzigingen aan dit project worden gedocumenteerd in dit
bestand. Het formaat is gebaseerd op
[Keep a Changelog](https://keepachangelog.com/nl/1.1.0/).

Dit project heeft nog geen releases. De secties hieronder zijn mijlpalen op
`main`, genoemd naar de datum van de laatste wijziging in de vorm `YYYY.M.D`
(bijvoorbeeld `2026.8.25`). Elke sectie verwijst onderaan naar de commit op
`main` die bij die stand hoort.

Per mijlpaal staan eerst de wijzigingen die een ondernemer of een afnemer van
de dienst merkt. Meer technische wijzigingen (zoals dependency-updates, CI en
build) staan kort onder "Onder de motorkap".

## [Unreleased]

## [2026.11.26]

### Gewijzigd

* De uitleg in gewone taal krijgt de berekening tot aan de invoer mee, met de
  grenzen uit de wet erbij (zoals een termijn of een drempelbedrag), zolang
  die in het verzoek aan het taalmodel past
  ([#80](https://github.com/MinBZK/moza-poc-digitale-assistent/pull/80)).
* Via VLAM verschilt de uitleg van dezelfde berekening minder van keer tot
  keer. Het taalmodel krijgt daarvoor een lage temperature mee, in te stellen
  met `UITLEG_VLAM_TEMPERATURE`.
* De Digitale assistent rekent niet. Een portaal of andere afnemer rekent in
  de browser met de regelrecht-engine, en stuurt een berekening alleen naar
  `/uitleg` als de ondernemer om een uitleg vraagt
  ([PDR-017](docs/decisions/PDR-017-de-digitale-assistent-rekent-niet.md),
  [#82](https://github.com/MinBZK/moza-poc-digitale-assistent/pull/82)).

### Opgelost

* De controle op de uitleg keurt een percentage dat goed is overgenomen niet
  langer af. Bedragen en percentages staan in de berekening nu in dezelfde vorm
  als in de uitkomst.
* Bij een grote berekening vallen geen onderdelen meer weg uit wat het
  taalmodel te zien krijgt. Paste een niveau dieper niet, dan verdwenen de
  laatste onderdelen in hun geheel.

### Onder de motorkap

* Het image draait weer op Python 3.14. Met Python 3.15 bouwde het image niet,
  waardoor er sinds 19 november geen nieuwe versie werd uitgerold
  ([#84](https://github.com/MinBZK/moza-poc-digitale-assistent/pull/84)).
* Een technische opstelling van "Waarom deze uitkomst?" beschrijft de twee
  lagen van de uitleg, vier beperkingen en mogelijke verbeteringen
  ([#81](https://github.com/MinBZK/moza-poc-digitale-assistent/pull/81)).
* Dependency-updates voor de GitHub Actions.

## [2026.10.25]

### Toegevoegd

* Uitleg in gewone taal: `POST /uitleg` zet de berekening van de
  regelrecht-engine om in een korte tekst en controleert daarna of de bedragen,
  de percentages en het wetsartikel in die tekst uit de berekening komen. Een
  tekst die de controle niet haalt, komt terug met die uitslag erbij
  ([PDR-016](docs/decisions/PDR-016-uitleg-in-gewone-taal-uit-de-beslisgraaf.md),
  [#77](https://github.com/MinBZK/moza-poc-digitale-assistent/pull/77)).
* Dezelfde uitleg is beschikbaar als losse MCP-server en als
  commandoregelprogramma (`uitleg-cli`).

### Gewijzigd

* VLAM loopt via de VLAM-API van ZAD, met Kimi-K3 als standaardmodel.

## [2026.9.3]

### Gewijzigd

* Bronnen staan standaard aan. De ondernemer zet een bron uit met een woord in
  het gesprek. Een handeling die akkoord vraagt, kan de assistent pas uitvoeren
  nadat de ondernemer dat akkoord heeft gegeven
  ([PDR-015](docs/decisions/PDR-015-bronnen-standaard-aan-en-tools-na-akkoord.md),
  [#75](https://github.com/MinBZK/moza-poc-digitale-assistent/pull/75)).

## [2026.8.25]

Deze mijlpaal bevat het werk voor het gebruikersonderzoek van augustus 2026.

### Toegevoegd

* De assistent werkt met de bedrijfsgegevens van de ingelogde ondernemer. Het
  systeem bepaalt zelf om welk bedrijf het gaat; het taalmodel en de tekst van
  het gesprek kunnen dat niet veranderen. Zonder geldige sessie wordt er geen
  bron en geen taalmodel aangeroepen
  ([PDR-009](docs/decisions/PDR-009-sessie-identiteit-host-side.md),
  [#38](https://github.com/MinBZK/moza-poc-digitale-assistent/pull/38)).
* Foutmeldingen zeggen wat er gebeurde en wat de ondernemer kan doen. Een
  vraag buiten het taakgebied krijgt een afwijzing met een verwijzing
  ([PDR-011](docs/decisions/PDR-011-foutmeldingen-catalogus.md),
  [#45](https://github.com/MinBZK/moza-poc-digitale-assistent/pull/45)).
* De regel stuurt het gesprek. Het systeem haalt eerst op wat het zelf kan
  ophalen en stopt waar toestemming of een opgave van de ondernemer nodig is.
  Elk gegeven draagt zijn herkomst: uit welke bron het komt en of het is
  waargenomen of alleen doorgegeven
  ([#53](https://github.com/MinBZK/moza-poc-digitale-assistent/pull/53)).
* De ondernemer ziet eerst het oordeel en de herkomst van de gegevens, en
  daarna pas het formulier voor de vervolgstap
  ([#54](https://github.com/MinBZK/moza-poc-digitale-assistent/pull/54)).
* De ondernemer kan zijn verbruik zelf opgeven in een invulveld
  ([#56](https://github.com/MinBZK/moza-poc-digitale-assistent/pull/56)).
* De ondernemer geeft per bron toestemming, ook voor het Handelsregister.
* Een ingediende zaak draagt de onderbouwing waarop die rust
  ([#55](https://github.com/MinBZK/moza-poc-digitale-assistent/pull/55)).
* Een bron is in de configuratie uit te zetten. De assistent noemt een bron
  die bewust uit staat niet
  ([#57](https://github.com/MinBZK/moza-poc-digitale-assistent/pull/57)).
* De belangrijkste vervolgstap staat vetgedrukt op een eigen regel
  ([#59](https://github.com/MinBZK/moza-poc-digitale-assistent/pull/59)).

### Gewijzigd

* Na het indienen van een rapportage staat de zaak op "In behandeling". De
  assistent meldt geen goedkeuring
  ([#31](https://github.com/MinBZK/moza-poc-digitale-assistent/pull/31)).
* De voorbeelden in de instructie aan het taalmodel zijn zelf op B1-niveau
  geschreven, met een meting van zinslengte en leesbaarheid in de tests
  ([#48](https://github.com/MinBZK/moza-poc-digitale-assistent/pull/48)).
* De rapportagedeadline in de RVO-mock is 1 december 2026
  ([#63](https://github.com/MinBZK/moza-poc-digitale-assistent/pull/63)).

### Beveiliging

* Een sleutel voor het taalmodel leeft precies één verzoek. Bij twee
  gelijktijdige verzoeken kon de sleutel van de ene gebruiker het verzoek van
  de andere bedienen. Een sleutel wordt verder op vorm gecontroleerd, gaat geen
  subproces in en wordt uit logregels verwijderd
  ([PDR-010](docs/decisions/PDR-010-sleutel-van-de-gebruiker.md),
  [#44](https://github.com/MinBZK/moza-poc-digitale-assistent/pull/44)).

### Opgelost

* Een opgave in Nederlandse notatie, zoals `250.000`, wordt gelezen als
  tweehonderdvijftigduizend. De opgave werd als 250 gelezen, waardoor de plicht
  onterecht verviel.
* Een negatief verbruik, zoals de tikfout `-5000`, telt niet als opgave. Het
  veld blijft open
  ([#60](https://github.com/MinBZK/moza-poc-digitale-assistent/pull/60)).
* Een antwoord dat langer dan een minuut duurt, komt aan. Tijdens het wachten
  blijft de status zichtbaar, en bij een druk taalmodel volgt een nieuwe poging
  ([PDR-013](docs/decisions/PDR-013-timeoutgrenzen-op-basis-van-meting.md),
  [#61](https://github.com/MinBZK/moza-poc-digitale-assistent/pull/61)).
* De assistent gebruikt geen woorden als "host", "backend" of "tool" in een
  antwoord
  ([#62](https://github.com/MinBZK/moza-poc-digitale-assistent/pull/62)).
* Wat als formulier op het scherm staat, staat niet ook als tekst in het
  antwoord
  ([#67](https://github.com/MinBZK/moza-poc-digitale-assistent/pull/67),
  [#68](https://github.com/MinBZK/moza-poc-digitale-assistent/pull/68)).
* Een bron die hangt of een onleesbaar antwoord geeft, laat het gesprek niet
  meer vastlopen. Vóór het indienen zoekt de assistent niet meer in RVO naar
  iets dat er niet is
  ([#66](https://github.com/MinBZK/moza-poc-digitale-assistent/pull/66)).
* De bedrijfsgegevens van Kwekerij De Bloesem in de KvK-mock komen overeen met
  wat het portaal toont: voltijd en deeltijd apart, en de website
  ([#47](https://github.com/MinBZK/moza-poc-digitale-assistent/pull/47)).

### Onder de motorkap

* Een eigen omgeving voor het gebruikersonderzoek, die op verzoek wordt
  uitgerold
  ([#64](https://github.com/MinBZK/moza-poc-digitale-assistent/pull/64)).
* Een script loopt de onderzoeksflow af tegen een draaiende host
  ([#52](https://github.com/MinBZK/moza-poc-digitale-assistent/pull/52)).
* Dependency-updates voor de GitHub Actions.

## [2026.6.18]

### Toegevoegd

* Eerste versie van de Digitale assistent in deze repository: een host die een
  gesprek voert tussen een taalmodel en overheidsbronnen (KvK, KOOP,
  RegelRecht, RVO en een netbeheerder-mock), via MCP of via
  commandoregelprogramma's.
* Demo voor de informatieplicht energiebesparing: de assistent attendeert de
  ondernemer, raadpleegt gegevens bij de bron na toestemming en laat een
  machine-uitvoerbare regel bepalen welke maatregelen gelden. Met een generieke
  RegelRecht-tool en de Business Wallet
  ([#29](https://github.com/MinBZK/moza-poc-digitale-assistent/pull/29)).
* De uitkomst van de beslishulp AI-verordening staat bij de voorbereidende
  documenten
  ([#7](https://github.com/MinBZK/moza-poc-digitale-assistent/pull/7)).

### Opgelost

* De flow voor het indienen van een rapportage is hersteld
  ([#30](https://github.com/MinBZK/moza-poc-digitale-assistent/pull/30)).

### Onder de motorkap

* De backend is uit te rollen op ZAD als intern component
  ([#6](https://github.com/MinBZK/moza-poc-digitale-assistent/pull/6)).
* Reviews lopen via `CODEOWNERS`; de CI draait ruff en de tests
  ([#8](https://github.com/MinBZK/moza-poc-digitale-assistent/pull/8)).
* Strengere standaardinstellingen voor beveiliging, waaronder CORS.
* Dependency-updates voor het image en de GitHub Actions.

[Unreleased]: https://github.com/MinBZK/moza-poc-digitale-assistent/compare/8c9167c...main
[2026.11.26]: https://github.com/MinBZK/moza-poc-digitale-assistent/compare/fe7281a...8c9167c
[2026.10.25]: https://github.com/MinBZK/moza-poc-digitale-assistent/compare/92fb9b8...fe7281a
[2026.9.3]: https://github.com/MinBZK/moza-poc-digitale-assistent/compare/365d46b...92fb9b8
[2026.8.25]: https://github.com/MinBZK/moza-poc-digitale-assistent/compare/b56f80e...365d46b
[2026.6.18]: https://github.com/MinBZK/moza-poc-digitale-assistent/commits/b56f80e
