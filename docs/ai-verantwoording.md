# Verantwoording inzet van generatieve AI in de Digitale-Assistent-PoC

**Verantwoording i.h.k.v. het Overheidsbreed Standpunt Generatieve AI, getoetst aan het stappenplan uit de bijbehorende handreiking**

Dit document verantwoordt het gebruik van generatieve AI bij het bouwen van deze
Proof of Concept (PoC). Voor een beknopte samenvatting, zie
[`DISCLAIMER.md`](../DISCLAIMER.md).

## Beschrijving van de PoC en de rol van AI

Deze repository is een PoC voor een Digitale Assistent binnen MijnOverheid
Zakelijk (MOZa). De assistent helpt ondernemers bij vragen over
overheidsdienstverlening door bronnen (KvK, KOOP, RegelRecht, RVO) via het
Model Context Protocol (MCP) te ontsluiten aan een LLM. Zie de
[`README.md`](../README.md) voor de actuele opzet en onderdelen.

**Rol van AI.** De code is grotendeels gegenereerd met de AI-assistant
Claude Code (Anthropic). AI is ingezet voor codegeneratie en voor ondersteuning
bij refactoring en review. Daarnaast is AI hier zelf onderdeel van het *product*:
de assistent gebruikt op runtime een LLM (Claude of een via VLAM beschikbaar
gesteld model) om gebruikersvragen te beantwoorden. Architectuur- en
ontwerpbeslissingen worden vastgelegd in product decision records
(zie [`MinBZK/moza-poc/services/decisions/`](https://github.com/MinBZK/moza-poc/tree/main/services/decisions)).

**Menselijke review.** De review richt zich op de onderdelen die het gedrag en
de kwaliteit van de PoC bepalen: het ontwerp (de PDR's) wordt inhoudelijk
beoordeeld, en alle niet-testcode wordt door ontwikkelaars gereviewd voordat die
in de hoofdbranch wordt opgenomen. Testcode wordt niet regel voor regel
gereviewd; de werking wordt in plaats daarvan functioneel beproefd (met test-
scenario's en een demo-applicatie). Dit gebeurt via de pull-request-workflow met
code-eigenaarschap (`CODEOWNERS`) en een CI-pijplijn met onder andere
CodeQL-securityscanning en OpenSSF Scorecard. De mens blijft eindverantwoordelijk;
de AI is een hulpmiddel.

Deze afbakening is een bewust onderdeel van de beproeving: we onderzoeken hoeveel
en hoe nauwkeurig menselijke review nodig én haalbaar is. De aanname die we
daarbij toetsen, is dat de AI met voldoende review-stappen code van voldoende
kwaliteit oplevert.

**Gegevens.** De PoC verwerkt geen persoonsgegevens. Er wordt uitsluitend
gewerkt met fictieve en testgegevens (waaronder een vaste test-ondernemer voor
de KvK-bevragingen).

**Scope-grens.** Deze verantwoording betreft uitsluitend de PoC. Eventueel
gebruik in een pilot of productie valt **buiten de huidige scope** en vereist
aanvullende toetsing, waaronder een beoordeling tegen de BIO (Baseline
Informatiebeveiliging Overheid) en een DPIA (Data Protection Impact Assessment).

## Verantwoording per stappenplan

Hieronder volgen we het globale stappenplan uit hoofdstuk 4 van de
[Overheidsbrede handreiking verantwoorde inzet van generatieve AI](https://open.overheid.nl/documenten/9c273b71-cebb-4e11-b06f-fa20f7b4b90e/file).

### 1) Doel en toepassingsgebied

De PoC heeft een breder doel dan alleen AI: we experimenteren onder meer met
het ontsluiten van overheidsbronnen via MCP, de gebruikerservaring en de
samenwerking met betrokken partijen. Dit document beperkt zich tot het
AI-aspect daarvan.

*Doel (AI-aspect):* onderzoeken of we verantwoord met behulp van generatieve AI
software kunnen bouwen *én* generatieve AI als runtime-component verantwoord
kunnen inzetten in een digitale dienst, en of de resultaten aantoonbaar in lijn
te brengen zijn met de standaarden, kaders en richtlijnen van de Nederlandse
overheid (o.a. MCP-standaard voor Generieke Interactieservices, NL API Design
Rules, relevante Logius-standaarden), mede met behulp van de
[overheidsskills](https://github.com/developer-overheid-nl/skills-marketplace).

*Toepassingsgebied:* de ontwikkeling van deze experimentele PoC. Niet in scope:
gebruik in pilot of productie.

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
organisatie zelf een AI-systeem bouwt of structureel inzet. De situatie hier is
gemengd: we gebruiken een AI-assistant als gereedschap tijdens ontwikkeling, en
de PoC gebruikt op runtime een LLM van een externe aanbieder. We nemen niets in
productie en verwerken geen persoonsgegevens. Dit beperkt de gebruikelijke
AI-risico's (zoals bias en ethische risico's). De volgende aandachtspunten
blijven relevant.

#### a. Voldoen aan de EU AI-verordening

Wij maken geen AI-systeem maar gebruiken bestaande AI-modellen: als
ontwikkelgereedschap (Claude Code) en als runtime-component (Claude API of een
via VLAM beschikbaar gesteld model). De verplichtingen vallen primair op de
aanbieder. Anthropic is ondertekenaar van de
[General Purpose AI Code of Practice](https://digital-strategy.ec.europa.eu/en/policies/contents-code-gpai)
van de EU. We houden bij welke AI-assistant en modellen we gebruiken en
markeren de met AI gegenereerde output als zodanig.

#### b. AVG en DPIA

De PoC verwerkt geen persoonsgegevens; er wordt uitsluitend met fictieve/
testdata gewerkt. Organisaties die deze code later in een pilot of productie
zouden gebruiken, dienen op dat moment zelf te beoordelen welke AVG-
verplichtingen van toepassing zijn, waaronder een eventuele DPIA: met name
omdat een digitale assistent in een productiecontext potentieel
persoonsgegevens van eindgebruikers verwerkt.

#### c. BIO en beveiligingseisen

Voor experimentele PoC-code die niet in productie gaat, gelden geen
BIO-verplichtingen. Wel kent het project basismaatregelen: CodeQL-securityscans,
OpenSSF Scorecard en aandacht voor dependencies en secrets in CI. Gebruik in
pilot of productie vereist een volledige toetsing aan de geldende
beveiligingseisen.

#### d. Datadeling met de AI-aanbieder

Het risico op datadeling wordt beperkt doordat geen vertrouwelijke gegevens of
persoonsgegevens worden gebruikt, en doordat in de instellingen van de
AI-assistant is gekozen voor de opt-out voor modeltraining. De aanschaf van
de AI-licenties door onze overheidsorganisatie is in voorbereiding. Voor de
runtime-LLM-aanroepen vanuit de PoC geldt hetzelfde: er worden uitsluitend
test-/demo-gegevens uitgewisseld.

#### e. Risico op "schijnzekerheid"

Het inzetten van AI bij de ontwikkeling van software is geen compliance-
garantie. De officiële brondocumenten (zoals de beschrijvingen van standaarden)
zijn altijd leidend. Het team blijft zelf verantwoordelijk voor het voldoen aan
standaarden en richtlijnen. AI is slechts een hulpmiddel.

Voor de assistent zelf geldt aanvullend: een antwoord van het LLM mag niet
zonder bronvermelding worden gepresenteerd. De PoC gebruikt provenance-metadata
op MCP-resources (conform de MCP-standaard §4.1) om aan eindgebruikers
herleidbaar te maken op welke overheidsbron een antwoord stoelt.

#### f. Kwaliteitsrisico: onjuiste of onveilige gegenereerde code

De kwaliteit wordt op meerdere niveaus geborgd: menselijke review van de
niet-testcode (zie "Menselijke review" hierboven), een teststrategie met onder
meer scenario-tests over de gehele tool-calling-keten, en geautomatiseerde
CI-controles (ruff, pytest, CodeQL).

#### g. Auteursrecht op brondocumenten als input

Per gebruikte standaard of bron wordt gecontroleerd of deze als input voor een
AI-assistant gebruikt mag worden. Brondocumentatie wordt vermeld, met
bijbehorende licentie-informatie waar nodig.

#### h. Uitlegbaarheid / gevaar op "black box"

De gegenereerde code en de architectuur zijn openbaar en in voor mensen
leesbare vorm gepubliceerd. Ontwerpbeslissingen worden vastgelegd in product
decision records (PDR's). De assistent zelf onderbouwt antwoorden met
verwijzingen naar de geraadpleegde bron via MCP-provenance.

#### i. AI-geletterdheid van betrokken medewerkers

Kennis over de inzet van AI-assistants wordt binnen het team gedeeld; deze
verantwoording wordt openbaar gepubliceerd.

### 5) Generatieve AI inkopen of bouwen

#### a. Vendor lock-in

Voor de ontwikkeling wordt op dit moment uitsluitend Claude Code gebruikt. Dat
is een expliciet aandachtspunt voor een eventueel vervolg. De opgeleverde
software zelf ondersteunt op runtime meerdere LLM-aanbieders: zowel Claude
(Anthropic) als modellen via de VLAM (UbiOps/Mistral) zijn out-of-the-box
ondersteund. Het is mogelijk om in een vervolg een andere LLM-aanbieder of een
andere AI-assistant in te zetten.

#### b. Keuze voor de AI-assistant

In deze PoC is gekozen voor Claude Code (Anthropic), een aanbieder die de EU
General Purpose AI Code of Practice heeft ondertekend.
