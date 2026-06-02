# AI-verordening en Algoritmeregister — beoordeling Digitale Assistent

Versie: 0.1

**Voorlopige classificatie van het AI-systeem onder de EU AI-verordening
(AI Act) en beoordeling van registratie in het Algoritmeregister.**

> **Status: voorlopig (PoC-niveau).** Dit document geeft een onderbouwde
> voorlopige classificatie op basis van de huidige PoC. Het is geen formeel
> vastgestelde conformiteitsbeoordeling. Definitieve classificatie en de
> bijbehorende verplichtingen moeten worden bevestigd vóór inzet in een pilot
> of productie, en opnieuw worden beoordeeld als de functionaliteit uitbreidt.

Dit document gaat over het **product** (de runtime-assistent), niet over AI als
ontwikkelgereedschap — dat staat in [`ai-verantwoording.md`](../ai-verantwoording.md).
Zie ook de [`iama.md`](iama.md) startnotitie.

Bronnen: [Beslishulp AI-verordening (Algoritmekader)](https://minbzk.github.io/Algoritmekader/ai-verordening/),
[AI-verordening (EU AI Act)](https://artificialintelligenceact.eu/),
[Algoritmeregister](https://algoritmes.overheid.nl/),
[Algoritmekader BZK](https://minbzk.github.io/Algoritmekader/).

## Wat is het systeem?

Een generatieve-AI-chatbot die ondernemers informeert over
overheidsdienstverlening. Het systeem gebruikt een taalmodel met toegang tot
vier read-/één write-tool. Voor productie is dat het Rijksbrede VLAM/Mistral-model;
Claude (Anthropic) wordt alleen in de PoC/ontwikkeling gebruikt. Het neemt zelf geen besluiten met
rechtsgevolg; de enige muterende actie gebeurt na expliciete bevestiging van de
gebruiker. Zie [`architecture.md`](../architecture.md).

## Rollen onder de AI-verordening

- **Aanbieder/gebruiksverantwoordelijke (deployer/provider):** BZK, als het
  systeem onder eigen naam in gebruik wordt genomen. De meeste verplichtingen
  bij inzet liggen hier.
- **Aanbieder van het AI-model voor algemene doeleinden (GPAI):** voor productie
  de aanbieder van het Rijksbrede VLAM/Mistral-model; in de PoC/ontwikkeling
  Claude (Anthropic). Zij dragen de modelverplichtingen (o.a. technische
  documentatie, auteursrechtbeleid).

## Risicoclassificatie (beslislogica AI Act)

We doorlopen de [Beslishulp AI-verordening](https://minbzk.github.io/Algoritmekader/ai-verordening/)
van het Algoritmekader **twee keer**, omdat de classificatie afhangt van hoe het
systeem wordt ingezet:

1. **Huidige status** — de PoC zoals die nu bestaat: niet in gebruik, geen echte
   eindgebruikers, uitsluitend fictieve/testdata, geen besluitvorming.
2. **Toekomstige status** — de beoogde inzet in een pilot of productie, met
   echte ondernemers als gebruikers en mogelijk uitgebreide functionaliteit.

Het onderscheid is belangrijk: een verplichting zoals de transparantieplicht
(art. 50) wordt pas operationeel zodra natuurlijke personen daadwerkelijk met het
systeem communiceren, en de hoog-risico-toets kan anders uitvallen als de
functionaliteit uitbreidt.

### Doorloop 1 — huidige status (PoC)

| Categorie | Van toepassing? | Onderbouwing |
|---|---|---|
| **Verboden praktijk** (art. 5) | Nee | Geen verboden toepassing. |
| **Hoog risico** (art. 6 + bijlage III) | Nee | Geen inzet, geen echte gebruikers, geen besluitvorming; geen verwerking van persoonsgegevens. |
| **Beperkt risico / transparantieplicht** (art. 50) | Niet operationeel | De plicht bijt pas bij interactie met natuurlijke personen; in een gesloten test met testdata is dat nog niet het geval. |
| **Minimaal risico** | Ja (feitelijk) | De PoC valt nu feitelijk in de restcategorie. |

**Voorlopige conclusie (huidig):** geen acute verplichtingen onder de
AI-verordening. Wel verstandig om transparantie (kenbaarheid AI) en
bronverwijzing nu al in te bouwen, zodat doorloop 2 soepel verloopt.

### Doorloop 2 — toekomstige status (beoogde inzet)

| Categorie | Van toepassing? | Onderbouwing |
|---|---|---|
| **Verboden praktijk** (art. 5) | Nee | Geen social scoring, manipulatie, biometrische categorisatie of andere verboden toepassing. |
| **Hoog risico** (art. 6 + bijlage III) | **Waarschijnlijk niet — te bevestigen** | Bijlage III(5) ziet o.a. op systemen die de toegang van *natuurlijke personen* tot essentiële (publieke) voorzieningen beoordelen of erover beslissen. De assistent *informeert* over regelingen/verplichtingen voor *ondernemingen* en *beslist niet*: RegelRecht licht toe of een verplichting van toepassing is, de mens behoudt de regie, en indienen vereist bevestiging. Dit moet formeel tegen bijlage III worden afgezet, omdat de uitkomst kan kantelen als het systeem bindende of besluitvormende functies krijgt. |
| **Beperkt risico / transparantieplicht** (art. 50) | **Ja** | Het systeem is een chatbot die met natuurlijke personen communiceert en genereert tekst. De gebruiker moet duidelijk en tijdig weten dat hij met een AI-systeem communiceert. |
| **Minimaal risico** | Restcategorie | Overige aspecten vallen hieronder; vrijwillige naleving van gedragscodes wordt aangemoedigd. |

**Voorlopige conclusie (toekomstig):** het systeem valt naar verwachting onder de
**transparantieverplichtingen voor beperkt risico (art. 50)**, niet onder
hoog risico — onder voorbehoud van formele toetsing tegen bijlage III en mits
de functionaliteit niet uitbreidt naar besluitvorming over personen. Deze
doorloop moet opnieuw worden gemaakt bij elke wezenlijke functie-uitbreiding.

## Verplichtingen die hieruit volgen

Bij de categorie beperkt risico (art. 50), als minimaal te borgen:

- **Kenbaarheid AI.** De interface maakt expliciet dat de gebruiker met een
  AI-assistent communiceert (niet met een ambtenaar).
- **Markering van AI-output** waar passend; bronverwijzing bij feitelijke claims.
- **Disclaimer** dat antwoorden niet bindend zijn en de officiële bron leidend is
  (sluit aan op [`DISCLAIMER.md`](../../DISCLAIMER.md)).
- **AI-geletterdheid** (art. 4): betrokken medewerkers moeten voldoende kennis
  hebben van de werking en beperkingen.

Zou de formele toets alsnog op hoog risico uitkomen, dan gelden de zwaardere
verplichtingen uit hoofdstuk III (o.a. risicomanagementsysteem, datakwaliteit,
logging, menselijk toezicht, conformiteitsbeoordeling, CE-markering en
registratie in de EU-databank).

## Algoritmeregister

Voor de Nederlandse overheid geldt het beleid om algoritmen te publiceren in het
[Algoritmeregister](https://algoritmes.overheid.nl/). Registratie is in elk geval
verplicht voor hoog-risico- en impactvolle algoritmen; daarbuiten geldt
"publiceren, tenzij".

- **PoC-fase:** registratie is nu niet aan de orde — het systeem is niet in
  gebruik en verwerkt geen echte gegevens.
- **Bij inzet (pilot/productie):** beoordeel registratie. Gezien de
  publieksgerichte inzet en de transparantie-ambitie van MOZa ligt **vrijwillige
  registratie in de rede**, ook als het systeem niet als hoog risico kwalificeert.
  De openbare architectuur, PDR's en deze documenten leveren al een groot deel
  van de benodigde registerinformatie.

## Overheidsbreed Standpunt Generatieve AI (toegepast op het product)

Naast de toetsing van het ontwikkelgereedschap in [`ai-verantwoording.md`](../ai-verantwoording.md)
moet het [Overheidsbreed standpunt generatieve AI](https://open.overheid.nl/documenten/bc03ce31-0cf1-4946-9c94-e934a62ebe73/file)
ook op het *product* worden toegepast zodra het richting pilot/productie gaat.
Aandachtspunten:

- Een passende rechtsgrond en (waar nodig) toestemming voor het gebruik van een
  generatief model in een overheidsdienst.
- Afspraken met de modelleverancier over datagebruik en training-opt-out, ook
  voor runtime-invoer van gebruikers.
- Menselijke controle, monitoring en een terugkoppelkanaal.
- Beoordeling tegen BIO (beveiliging) en AVG/DPIA (privacy).
