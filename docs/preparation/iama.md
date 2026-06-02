# IAMA — startnotitie voor de Digitale Assistent

Versie: 0.1

**Impact Assessment Mensenrechten en Algoritmes (IAMA), toegepast op het
AI-systeem dat met deze PoC wordt opgeleverd.**

> **Status: voorbereidend (PoC-niveau).** Dit document is géén afgeronde IAMA.
> De IAMA is bedoeld als gestructureerd groepsgesprek met een multidisciplinair
> team (beleid, juridisch, techniek, uitvoering, ethiek). Dit bestand legt de
> bekende feiten en de kernvragen vast als startpunt voor dat gesprek. Een
> formele IAMA, inclusief grondrechtentoets en bestuurlijke vaststelling, is
> vereist vóór inzet in een pilot of productie.

Dit document gaat over het **product** (de Digitale Assistent die op runtime een
LLM aanroept), niet over de inzet van AI als ontwikkelgereedschap — dat staat in
[`ai-verantwoording.md`](../ai-verantwoording.md). Voor de classificatie onder de
EU AI-verordening en het Algoritmeregister, zie [`ai-verordening.md`](ai-verordening.md).

Het IAMA-instrument zelf staat beschreven in het
[Algoritmekader van BZK](https://minbzk.github.io/Algoritmekader/voldoen-aan-wetten-en-regels/hulpmiddelen/IAMA/).

## Deel 1 — Waarom?

**Doel.** De Digitale Assistent helpt ondernemers bij vragen over
overheidsdienstverlening: regelgeving, subsidies en bedrijfsregistratie. De
assistent ontsluit overheidsbronnen (KvK, KOOP, RegelRecht, RVO) als tools voor
een taalmodel en stelt zo antwoorden samen in begrijpelijke taal.

**Publieke waarden.** Toegankelijkheid van overheidsinformatie, begrijpelijkheid
(taalniveau B1), tijdsbesparing voor ondernemers, en juistheid/betrouwbaarheid
van informatie. Tegenover deze waarden staan risico's op onjuiste of
onvolledige informatie en op schijnzekerheid.

**Wettelijke grondslag.** De assistent neemt zelf geen besluiten met
rechtsgevolg. Hij ontsluit openbare bronnen en ondersteunt de gebruiker.
De enige muterende actie (`rvo__indienen`) wordt uitgevoerd namens en met
expliciete bevestiging van de ondernemer. Welke grondslag geldt voor het
verwerken van sessie-/bedrijfsgegevens in een productieversie, moet bij
uitwerking worden bepaald (zie de privacy-/DPIA-vraag hieronder).

**Betrokken partijen.** Opdrachtgever/uitvoerder: Ministerie van BZK (MOZa).
Gebruikers: ondernemers. Bronhouders: KvK, KOOP (wetten.overheid.nl), RVO en de
RegelRecht-/machine-law-uitvoering. Modelleverancier voor productie: het
Rijksbrede VLAM/Mistral-model; Claude (Anthropic) wordt alleen in de
PoC/ontwikkeling gebruikt.

## Deel 2 — Wat?

**Type algoritme.** Een generatief taalmodel (LLM) met tool-use (agentic loop).
Het is een *zelflerend model van een externe leverancier* dat in deze toepassing
niet wordt getraind of bijgesteld; het wordt aangestuurd via een systeemprompt
en krijgt toegang tot een vaste set tools. Zie [`architecture.md`](../architecture.md).

**Input.** De gebruikersvraag, de gespreksgeschiedenis binnen een sessie, en de
data die de tools teruggeven (o.a. KvK-basisprofiel van het eigen bedrijf,
wetteksten, beslislogica-uitkomsten). In de PoC: uitsluitend fictieve/testdata
(demo: Test BV Donald, KvK 68750110).

**Output.** Een tekstantwoord in natuurlijke taal, met bronverwijzingen, en in
één geval een mutatie (rapportage indienen bij RVO) na bevestiging.

**Persoonsgegevens.** In de PoC worden geen persoonsgegevens verwerkt. In
productie kunnen bedrijfs- en mogelijk persoonsgegevens (bv. van eenmanszaken,
of de ingelogde gebruiker) in beeld komen. Een **DPIA** is dan vereist
(zie [`ai-verantwoording.md`](../ai-verantwoording.md), §4b en de scope-grens).
Dataminimalisatie is technisch ondersteund via de `fields`-parameter op
read-tools.

**Transparantie (technisch).** Code en architectuur zijn openbaar (EUPL-1.2).
Ontwerpkeuzes staan in de PDR's ([`decisions/`](../decisions/)). Tools geven
provenance-metadata terug bij elk resultaat.

## Deel 3 — Hoe?

**Menselijke regie.** De assistent is adviserend, niet beslissend. De gebruiker
houdt de regie: muterende acties vereisen expliciete bevestiging
(afgedwongen via `ToolAnnotations` `readOnlyHint=False` én de systeemprompt).

**Kwaliteitsborging.** Systeemprompt met guardrails en bronverwijzingsregels;
scenario-/integratietests over de tool-calling-keten; CI met ruff, pytest en
CodeQL. De officiële bron blijft altijd leidend; de assistent verwijst daarnaar.

**Foutgedrag.** Bij onbereikbare bronnen geeft de assistent dat eerlijk aan en
verwijst naar het directe kanaal (zie scenario 5 in [`architecture.md`](../architecture.md)),
in plaats van te gokken.

**Evaluatie en communicatie.** Voor productie nog te beleggen: monitoring van
antwoordkwaliteit, een terugkoppel-/klachtenkanaal, en een evaluatiecyclus.

## Grondrechtentoets (te beleggen)

De grondrechtentoets is het hart van de IAMA en hoort in het multidisciplinaire
gesprek thuis. Voorlopige aandachtspunten:

| Grondrecht / waarde | Relevantie | Voorlopige inschatting |
|---|---|---|
| Non-discriminatie / gelijke behandeling | LLM-antwoorden kunnen onbedoeld bias bevatten | Beperkt: geen profilering of besluitvorming; wel toetsen of antwoorden voor alle groepen even bruikbaar/juist zijn |
| Behoorlijk bestuur / rechtszekerheid | Risico op onjuiste of schijnzekere informatie | Mitigatie: bronverwijzing, disclaimers, "officiële bron is leidend" |
| Bescherming persoonsgegevens (art. 8 Handvest) | In productie mogelijk persoonsgegevens | DPIA vereist; in PoC niet van toepassing |
| Toegang tot informatie / non-uitsluiting | Taalniveau, digitale toegankelijkheid (WCAG) | Positief mits toegankelijk ontworpen; alternatief kanaal blijft nodig |

Per geraakt grondrecht moet de formele IAMA de stappen **inbreuk → doel →
noodzaak → evenredigheid → subsidiariteit** doorlopen en een afweging vastleggen.

## Openstaande acties

- [ ] Formele IAMA-sessie beleggen met een multidisciplinair team.
- [ ] DPIA uitvoeren zodra (mogelijk) persoonsgegevens worden verwerkt.
- [ ] Grondrechtentoets vastleggen en bestuurlijk laten vaststellen.
- [ ] Uitkomsten terugkoppelen naar [`ai-verordening.md`](ai-verordening.md)
      (risicoclassificatie) en het Algoritmeregister-besluit.
