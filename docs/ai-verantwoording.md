# Verantwoording inzet van Claude Code bij de ontwikkeling van de Digitale-Assistent-PoC

**Verantwoording i.h.k.v. het Overheidsbreed Standpunt Generatieve AI, getoetst aan het stappenplan uit de bijbehorende handreiking.**

Dit document verantwoordt het gebruik van **Claude Code (Anthropic)** als
ontwikkelgereedschap bij het bouwen van deze Proof of Concept (PoC). Voor een
beknopte samenvatting, zie [`DISCLAIMER.md`](../DISCLAIMER.md).

## Scope van dit document

Dit document gaat **uitsluitend** over de inzet van generatieve AI als
ontwikkelgereedschap (Claude Code) tijdens het bouwen van de PoC.

Het gaat **niet** over het AI-systeem dat met deze PoC wordt opgeleverd
(de Digitale Assistent zelf, die op runtime een LLM aanroept om
gebruikersvragen te beantwoorden). Daarvoor komt aparte verantwoording en
documentatie, op basis van:

- **IAMA** (Impact Assessment Mensenrechten en Algoritmen): brede mensenrechten-
  en kwaliteitsassessment voor algoritmische toepassingen door de overheid.
  Zie de startnotitie [`iama.md`](preparation/iama.md).
- **AI-verordening beslishulp**: bepaling van risicocategorie en bijbehorende
  verplichtingen onder de EU AI Act voor het AI-systeem. Zie de voorlopige
  classificatie in [`ai-verordening.md`](preparation/ai-verordening.md).
- **Overheidsbreed Standpunt Generatieve AI** en bijbehorende handreiking,
  toegepast op het gebruik in het product (niet enkel in de ontwikkeling).
  Zie de sectie "Overheidsbreed Standpunt" in [`ai-verordening.md`](preparation/ai-verordening.md).

Deze documenten bestaan nu als **voorbereidende PoC-startnotities**; ze worden
verder uitgewerkt en formeel vastgesteld zodra het AI-systeem richting pilot of
productie gaat.

## Beschrijving van de PoC en de rol van AI

Deze repository is een PoC voor een Digitale Assistent binnen MijnOverheid
Zakelijk (MOZa). Zie de [`README.md`](../README.md) voor de actuele opzet en
onderdelen.

**Rol van AI in de ontwikkeling.** De code is grotendeels gegenereerd met de
AI-assistant Claude Code (Anthropic). AI is ingezet voor codegeneratie en voor
ondersteuning bij refactoring en review. Architectuur- en ontwerpbeslissingen
worden vastgelegd in product decision records (PDR) (zie
[`docs/decisions/`](decisions/)).

**Menselijke review.** De review richt zich op de onderdelen die het gedrag en
de kwaliteit van de PoC bepalen: het ontwerp (de PDR's) wordt inhoudelijk
beoordeeld, en alle niet-testcode wordt door ontwikkelaars gereviewd voordat
die in de hoofdbranch wordt opgenomen. Testcode wordt niet regel voor regel
gereviewd; de werking wordt in plaats daarvan functioneel beproefd.
De mens blijft eindverantwoordelijk; de AI is een hulpmiddel.

Deze afbakening is een bewust onderdeel van de beproeving: we onderzoeken
hoeveel en hoe nauwkeurig menselijke review nodig én haalbaar is. De aanname
die we daarbij toetsen, is dat de AI met voldoende review-stappen code van
voldoende kwaliteit oplevert.

**Gegevens.** Tijdens de ontwikkeling worden geen persoonsgegevens met de
AI-assistant gedeeld. Er wordt uitsluitend gewerkt met openbare, fictieve en/of test-gegevens.

**Scope-grens.** Deze verantwoording betreft uitsluitend de ontwikkeling van
de PoC met behulp van een AI-assistant. Eventueel gebruik van de PoC in een
pilot of productie valt **buiten de scope** en vereist aanvullende toetsing,
waaronder een beoordeling tegen de BIO (Baseline Informatiebeveiliging
Overheid) en een DPIA (Data Protection Impact Assessment).

## Verantwoording per stappenplan

Hieronder volgen we het globale stappenplan uit hoofdstuk 4 van de
[Overheidsbrede handreiking verantwoorde inzet van generatieve AI](https://open.overheid.nl/documenten/9c273b71-cebb-4e11-b06f-fa20f7b4b90e/file),
toegepast op het gebruik van Claude Code in de ontwikkeling.

### 1) Doel en toepassingsgebied

*Doel (AI-aspect):* onderzoeken of we verantwoord met behulp van een
AI-assistant software kunnen bouwen, en of de resultaten aantoonbaar in lijn
te brengen zijn met de standaarden, kaders en richtlijnen van de Nederlandse
overheid (o.a. NL API Design Rules, relevante Logius-standaarden, MCP-standaard
voor Generieke Interactieservices), mede met behulp van de
[overheidsskills](https://github.com/developer-overheid-nl/skills-marketplace).

*Toepassingsgebied:* de ontwikkeling van deze experimentele PoC. Niet in
scope: gebruik in pilot of productie, en (zoals in "Scope van dit document"
uitgelegd) het AI-systeem dat met deze PoC wordt opgeleverd.

### 2) Zorg voor de juiste mensen en vaardigheden

De betrokken ontwikkelaars zijn niet op voorhand expert van alle betrokken
standaarden. Een onderdeel van de PoC is juist om praktisch kennis van die
standaarden op te bouwen door iets te bouwen, en om mede met behulp van de
[overheidsskills](https://github.com/developer-overheid-nl/skills-marketplace) te
borgen dat het resultaat eraan voldoet. AI wordt ingezet als gereedschap onder
menselijke regie.

Om de juiste expertise te betrekken streven we ernaar zo veel mogelijk
betrokken partijen, waaronder beheerders en experts van de relevante
standaarden, te laten meekijken met de PoC.

### 3) Creëer een (generatieve) AI-governance structuur

Het werk gebeurt in opdracht van het Ministerie van Binnenlandse Zaken en
Koninkrijksrelaties (BZK). Als beleidsmatige leidraad gelden het
[Overheidsbreed standpunt voor de inzet van generatieve AI](https://open.overheid.nl/documenten/bc03ce31-0cf1-4946-9c94-e934a62ebe73/file)
en de bijbehorende
[handreiking](https://open.overheid.nl/documenten/9c273b71-cebb-4e11-b06f-fa20f7b4b90e/file).

Concrete governance-maatregelen:

- Met AI gegenereerde bijdragen zijn herkenbaar gemarkeerd via de commit-trailer
  `Co-Authored-By`.
- Niet-testcode wordt menselijk gereviewd via de pull-request-workflow vóór
  merge; de werking van het geheel wordt functioneel beproefd (zie "Menselijke
  review" hierboven).
- Voor maximale transparantie is de repository openbaar en onder een open
  licentie ([EUPL-1.2](../LICENSE)); reageren kan via GitHub-issues.

### 4) Risicoanalyse

De gangbare assessment-instrumenten gaan er doorgaans van uit dat een
organisatie zelf een AI-systeem bouwt of structureel inzet. Dat is in het kader
van *deze verantwoording* niet het geval: we gebruiken een AI-assistant als
gereedschap, we bouwen zelf geen AI-systeem in dit document, nemen niets in
productie en delen geen persoonsgegevens met de AI-assistant. Dit beperkt de
gebruikelijke AI-risico's (zoals bias en ethische risico's). De volgende
aandachtspunten blijven relevant.

#### a. Voldoen aan de EU AI-verordening

Wij maken geen AI-model en bouwen in deze verantwoording geen AI-systeem;
we gebruiken Claude Code als gereedschap. De verplichtingen vallen primair op
de aanbieder. Anthropic is ondertekenaar van de
[General Purpose AI Code of Practice](https://digital-strategy.ec.europa.eu/en/policies/contents-code-gpai)
van de EU. We houden bij welke AI-assistant en modellen we gebruiken en
markeren de met AI gegenereerde output als zodanig.

#### b. AVG en DPIA

Er worden geen persoonsgegevens met de AI-assistant gedeeld; er wordt
uitsluitend met fictieve/testdata gewerkt. Organisaties die deze code later in
een pilot of productie zouden gebruiken, dienen op dat moment zelf te
beoordelen welke AVG-verplichtingen van toepassing zijn, waaronder een
eventuele DPIA.

#### c. BIO en beveiligingseisen

Voor experimentele PoC-code die niet in productie gaat, gelden geen
BIO-verplichtingen. Wel kent het project basismaatregelen: CodeQL-securityscans,
OpenSSF Scorecard en aandacht voor dependencies en secrets in CI. Gebruik in
pilot of productie vereist een volledige toetsing aan de geldende
beveiligingseisen.

#### d. Datadeling met de AI-aanbieder

Het risico op datadeling wordt beperkt doordat geen vertrouwelijke gegevens of
persoonsgegevens met de AI-assistant worden gedeeld, en doordat in de
instellingen van Claude Code is gekozen voor de opt-out voor modeltraining.
De aanschaf van de AI-licenties door onze overheidsorganisatie is in
voorbereiding.

#### e. Risico op "schijnzekerheid"

Het inzetten van AI bij de ontwikkeling van software is geen compliance-
garantie. De officiële brondocumenten (zoals de beschrijvingen van standaarden)
zijn altijd leidend. Het team blijft zelf verantwoordelijk voor het voldoen
aan standaarden en richtlijnen. AI is slechts een hulpmiddel.

#### f. Kwaliteitsrisico: onjuiste of onveilige gegenereerde code

De kwaliteit wordt op meerdere niveaus geborgd: menselijke review van de
niet-testcode (zie "Menselijke review" hierboven), een teststrategie met onder
meer scenario-tests over de gehele tool-calling-keten, en geautomatiseerde
CI-controles (ruff, pytest, CodeQL).

#### g. Auteursrecht op brondocumenten als input

Per gebruikte standaard of bron wordt gecontroleerd of deze als input voor
een AI-assistant gebruikt mag worden. Brondocumentatie wordt vermeld, met
bijbehorende licentie-informatie waar nodig.

#### h. Uitlegbaarheid / gevaar op "black box"

De gegenereerde code en de architectuur zijn openbaar en in voor mensen
leesbare vorm gepubliceerd. Ontwerpbeslissingen worden vastgelegd in product
decision records (PDR's, zie [`docs/decisions/`](decisions/)).

#### i. AI-geletterdheid van betrokken medewerkers

Kennis over de inzet van AI-assistants wordt binnen het team gedeeld; deze
verantwoording wordt openbaar gepubliceerd.

### 5) Generatieve AI inkopen of bouwen

#### a. Vendor lock-in

Op dit moment wordt voor de ontwikkeling uitsluitend Claude Code gebruikt.
Dat is een expliciet aandachtspunt voor een eventueel vervolg. De opgeleverde
software zelf is leverancier-onafhankelijk (Python/FastAPI) en kent geen
ontwikkel-tijd-afhankelijkheid van een AI-aanbieder; een andere AI-assistant
kan in een vervolg worden ingezet.

#### b. Keuze voor de AI-assistant

In deze PoC is gekozen voor Claude Code (Anthropic), een aanbieder die de EU
General Purpose AI Code of Practice heeft ondertekend.
