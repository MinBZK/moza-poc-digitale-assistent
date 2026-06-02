# Voorbereiding: gebruik van KvK-gegevens van ondernemers

Versie: 0.1

> **Status: voorbereidend (PoC-niveau).** Dit document beschrijft wat geregeld
> moet worden vóór de overgang van de KvK **Test-API** naar **echte** KvK-gegevens
> van ondernemers (richting alpha, beta, productie). Het is geen afgeronde DPIA
> en geen juridisch advies; het is een startpunt voor die trajecten.

Onderdeel van de [voorbereidende documenten](README.md). Zie ook de systeembrede
[`iama.md`](iama.md) (grondrechten) en [`ai-verordening.md`](ai-verordening.md)
(AI-classificatie). De PoC gebruikt nu de KvK Test API met een vast demo-bedrijf
(Test BV Donald, KvK 68750110); zie [`../architecture.md`](../architecture.md).

## Kernpunt: KvK-data is deels persoonsgegevens

Gegevens van **eenmanszaken, vof's, maatschappen en functionarissen**
(zoals bestuurders) zijn persoonsgegevens: naam, woonadres, geboortedatum en
-plaats, en gegevens die herleidbaar zijn via KvK-nummer, handelsnaam of
bezoekadres. Gegevens van **rechtspersonen** (bv, nv, stichting) zelf zijn dat
niet. Zodra echte gegevens worden verwerkt geldt dus de AVG — met de bijzondere
regels die voor het Handelsregister gelden (zo geldt er bijvoorbeeld geen recht
op vergetelheid).

## Werkstromen vóór ingebruikname

### 1. Toegang tot de productie-API

De Test-API moet worden vervangen door productie-toegang. Twee routes:

- **KVK Dataservice / API's voor overheden** (waarschijnlijk passend voor MOZa):
  PKIoverheid-certificaat met **OIN**, WS-Security, een aansluitprocedure
  (PREPROD → productie), en "inputfinanciering" voor overheidsorganisaties.
- **KVK Developer Portal (REST)**: API-key + getekende overeenkomst
  (tekenbevoegd, ingeschreven in het HR; abonnementskosten per key en per
  bevraging).

Beide vereisen akkoord op de **Gebruiksvoorwaarden Verstrekking en gebruik
Handelsregistergegevens**.

### 2. Privacy / AVG → DPIA

- **DPIA verplicht** (overheid + mogelijk grootschalig + AI = hoog-risico­
  verwerking). Privacy by design.
- **Verwerkingsgrondslag** (art. 6 AVG) bepalen en vastleggen (voor de overheid
  doorgaans wettelijke taak / algemeen belang).
- **Doelbinding / hergebruik**: hergebruik van persoonsgegevens uit het HR
  vereist een **apart verzoek bij KVK** en moet verenigbaar zijn met de
  doeleinden van artikel 2 Handelsregisterwet. Laat juridisch bevestigen of het
  tonen van iemands *eigen* gegevens na authenticatie als "inzage" (lichter) of
  "hergebruik" (zwaarder) kwalificeert.
- **Dataminimalisatie**: alleen benodigde velden — de `fields`-parameter op de
  read-tools ondersteunt dit al technisch.
- Verwerkingsregister, bewaartermijnen en betrokkenenrechten beleggen.

### 3. Het "LLM-knelpunt" (belangrijkste)

De host stuurt tool-resultaten (inclusief het KvK-profiel) de **LLM-context in**.
Voor productie is het taalmodel het Rijksbrede **VLAM** (EU/overheid-gehost).
Ook dan worden **persoonsgegevens met een modelleverancier gedeeld** — een aparte
verwerking met eigen grondslag. Te borgen:

- **verwerkersovereenkomst** + **training-opt-out**;
- **dataminimaliseren/pseudonimiseren vóór** het naar het model gaat, of
  persoonsgegevens niet naar het model sturen.

Sluit aan op de sectie "Overheidsbreed Standpunt Generatieve AI" in
[`ai-verordening.md`](ai-verordening.md).

### 4. Authenticatie & autorisatie

Nu hardcoded KvK-nummer; productie haalt het KvK-nummer uit
**sessie-authenticatie** → **eHerkenning** (met machtigingen), zodat een
ondernemer alléén het eigen bedrijf kan opvragen. Borg autorisatie
**server-side**, niet via een tool-parameter die het LLM kan invullen.

### 5. Beveiliging (BIO)

BIO-toets, geheimenbeheer (API-keys/certificaten), TLS, en **logging van toegang
tot persoonsgegevens** (de provenance-metadata is er al; overweeg het Logboek
Dataverwerkingen / NEN 7513). Pentest vóór productie.

### 6. Governance formeel maken

De echte-data-stap triggert formeel: **DPIA**, **IAMA** (zie [`iama.md`](iama.md)),
**doorloop 2 van de AI-verordening beslishulp** en het **Algoritmeregister**-besluit
(zie [`ai-verordening.md`](ai-verordening.md)).

## Toekomst: KvK via een wallet? (optie, nog te besluiten)

KvK-/bedrijfsattesten zouden in de toekomst ook via een **wallet** kunnen komen
(NL Wallet of de Europese Business Wallet) in plaats van een directe API. Dan
deelt de ondernemer geverifieerde attesten zelf en verschuift de grondslag naar
toestemming/selectieve deling. Dat verandert deze DPIA wezenlijk. **Nog niet besloten.**

## Openstaande acties

- [ ] Route kiezen: KVK Dataservice (overheid, PKIoverheid/OIN) vs. Developer
      Portal (API-key), en de bijbehorende overeenkomst tekenen.
- [ ] DPIA uitvoeren en grondslag + doelbinding vastleggen.
- [ ] Apart verzoek bij KVK voor hergebruik van persoonsgegevens (indien van
      toepassing) en inzage-vs-hergebruik juridisch laten bevestigen.
- [ ] Besluit over het LLM-knelpunt (welk model, verwerkersovereenkomst,
      minimalisatie/pseudonimisering).
- [ ] eHerkenning-authenticatie + server-side autorisatie inrichten.
- [ ] BIO-toets en pentest.
- [ ] Wallet-route als optie expliciet wegen en besluiten.

## Bronnen

- [KVK Developer Portal — API's & abonnement](https://developers.kvk.nl/nl/apis)
- [KVK Dataservice overheid aansluiten](https://www.kvk.nl/producten-bestellen/kvk-dataservice-aansluiten-overheid/)
- [Gebruiksvoorwaarden Verstrekking en gebruik Handelsregistergegevens (PDF)](https://developers.kvk.nl/cms/api/uploads/Gebruiksvoorwaarden_Verstrekking_en_Gebruik_Handelsregistergegevens.pdf)
- [KVK — privacy en het Handelsregister](https://www.kvk.nl/over-kvk/veelgestelde-vragen-over-privacy-en-het-handelsregister/)
- [Autoriteit Persoonsgegevens — DPIA](https://autoriteitpersoonsgegevens.nl/themas/basis-avg/praktisch-avg/data-protection-impact-assessment-dpia)
