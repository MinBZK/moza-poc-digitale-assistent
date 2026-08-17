# Meting regelloop — 2026-08-13

**Doel:** de laatste stap van taak 8 (`.superpowers/sdd/2026-08-13-regel-stuurt-de-flow/`):
de definitieve meting van de regelgestuurde flow (taak 1 t/m 7, plus de
PDR-008-events-fix) vastleggen naast het ijkpunt van
[`eindmeting-2026-08-13.md`](eindmeting-2026-08-13.md), en het meetscript zelf
kloppend maken waar het nog een oudere versie van de flow toetste.

- **Datum:** 2026-08-13
- **Modus:** `vlam`
- **KvK:** `62345681` (Kwekerij De Bloesem — plicht via gas en elektriciteit,
  onder de onderzoeksdrempel)
- **Commit-hash waarop gemeten is:** `9a70e0a` (`fix(host): geen tool-event
  voor een geweigerde bron-aanroep (PDR-008)`)
- **Runs:** 5, met
  `uv run python services/host/scripts/onderzoeksflow.py --mode vlam --kvk 62345681 --runs 5 --json meting-def.json`
- **Ruwe uitvoer:** `meting-def.log` / `meting-def.json` (niet in git, zoals
  bij de eerdere metingen in deze reeks — dit document is het geconsolideerde
  verslag).

De meting zelf is gedraaid vóórdat de twee correcties hieronder aan het
meetscript zijn aangebracht; de tabel toont dus wat er op commit `9a70e0a`
uitkwam, met de twee inmiddels-verouderde regels expliciet gemarkeerd.

## Samenvatting per controle, naast het ijkpunt

| Controle | Eindmeting (`0e14153`) | Deze meting (`9a70e0a`) |
|---|---|---|
| backend vlam is beschikbaar | 5/5 | 5/5 |
| alle vijf de bronnen zijn verbonden | 5/5 | 5/5 |
| geen foutmelding | 30/30 | 30/30 |
| geen (toestemmingsplichtige) bron geraadpleegd vóór toestemming (PDR-008) | 5/5 | 5/5 |
| de assistent vraagt om toestemming | 5/5 | 5/5 |
| **regelrecht__execute_law vóór elke andere bron uit de routeringstabel** *(nieuw, taak 8)* | n.v.t. | **10/10** |
| kvk__mijn_bedrijf is aangeroepen | 5/5 | **0/5 — verouderde controle, zie hieronder** |
| netbeheerder__verbruik is aangeroepen | 5/5 | 5/5 |
| regelrecht__execute_law is aangeroepen | 5/5 | 5/5 |
| het antwoord noemt de bedrijfsnaam van het scherm | 5/5 | **4/5 — open punt, zie hieronder** |
| het antwoord noemt het elektriciteitsverbruik van het scherm | 5/5 | 5/5 |
| het antwoord noemt het gasverbruik van het scherm | 5/5 | 5/5 |
| elk genoemd adres is dat van het scherm | 1/1 (vuurde in 1/5 runs) | vuurde in geen van de 5 runs (geen adresregel in het antwoord) |
| de frontend kan hier een formulier van maken (stap 3, de twee vragen) | 5/5 | 5/5 |
| twee vragen als velden (2) | 5/5 | 5/5 |
| de frontend kan van de maatregelen een formulier maken (stap 4, tekstparser) | 2/5 | 5/5 |
| het formulier heet 'Erkende Maatregelenlijst (EML 2023)' | 2/2 (vuurt alleen als tekstparser al een spec teruggaf) | 5/5 |
| het answer-event draagt een maatregelen-lijst | 5/5 | 5/5 |
| elk item heeft een gevulde code en omschrijving | 5/5 | 5/5 |
| geen onopgelost slot in het antwoord | 10/10 | 10/10 |
| de bron-waarden staan in het antwoord (na substitutie, stap 2) | 5/5 | 5/5 |
| **de bron-waarden staan in het antwoord (geen, stap 6)** | n.v.t. (stap 6 werd niet getoetst in de eindmeting) | **0/5 — verouderde controle, zie hieronder** |
| het rapport bevat bedrijfsnaam | 5/5 | 5/5 |
| het rapport bevat vestigingsadres | 5/5 | 5/5 |
| het rapport bevat elektriciteitsverbruik | 5/5 | 5/5 |
| nog niet ingediend zonder bevestiging | 5/5 | 5/5 |
| de assistent vraagt eerst om bevestiging | 5/5 | 5/5 |
| rvo__indienen is aangeroepen (na bevestiging) | 5/5 | 5/5 |
| er komt een case-event voor 'Lopende zaken' | 5/5 | 5/5 |
| de rapportage gaat 'in behandeling', niet 'goedgekeurd' | 5/5 | 5/5 |
| antwoord blijft onder 15 woorden per zin (B1, samengevoegd) | 25/30 | 24/30 |

Op elke bestaande controle die niet hieronder als verouderd staat gemarkeerd,
houdt deze meting zijn score of verbetert hij: geen regressie. De tekstparser-
controle (stap 4) sprong van 2/5 naar 5/5 — geen doel van deze taak, maar geen
zorgwekkende beweging: het model formatteert de maatregelenlijst kennelijk nu
consistenter als genummerde vraag-regels, boven op het structurele
`maatregelen`-veld dat al op 5/5 stond in de eindmeting.

## De twee verouderde controles die zijn bijgewerkt

Beide controles maten iets dat waar was vóór taak 4 ("de regel stuurt de flow,
niet het model") en zijn sindsdien niet meegegroeid met de architectuur. Dat
ze hier alsnog een vals-negatieve score gaven is zelf een bevestiging dat de
architectuur echt is veranderd — de meetlat stond op de oude flow.

### 1. `kvk__mijn_bedrijf is aangeroepen`: 0/5 → verplaatst naar stap 1

**Wat er verkeerd aan was.** De controle stond in stap 2 ("Ja, ga je gang.")
en verwachtte dat het *model* daar zelf `kvk__mijn_bedrijf` aanroept, samen
met `netbeheerder__verbruik` en `regelrecht__execute_law`. Dat klopte vóór
taak 4. Sinds de orkestratielus (`regelloop.volg_regel`, aangeroepen vanuit
`vlam_host._regel_status`) is dat niet meer zo: `IS_WOONFUNCTIE`
(`regelrouting.HERKOMST`) heeft `toestemming=False`, dus de host haalt
`kvk__mijn_bedrijf` al op in stap 1, vóórdat het model om toestemming vraagt —
en dat feit blijft daarna in de feitenkaart van het gesprek staan, dus stap 2
roept de KvK niet nogmaals aan. De controle keek dus letterlijk in de
verkeerde beurt naar de verkeerde actor (het model in plaats van de host).

Bewijs uit de ruwe log dat de KvK wél geraadpleegd werd, alleen niet waar de
controle keek: in alle 5 runs slaagde
`regelrecht__execute_law is aangeroepen vóór elke andere bron uit de
routeringstabel` óók op stap 1. Die controle vuurt alleen als er in die beurt
een andere routeringstabel-bron dan de wet is aangeroepen; de enige kandidaat
in stap 1 is `kvk__mijn_bedrijf`, want `netbeheerder__verbruik` vergt
toestemming die op dat moment nog niet is gegeven (en de PDR-008-controle op
diezelfde beurt stond op 5/5 — geen toestemmingsplichtige bron geraadpleegd).
Dat is een indirect bewijs, geen herteld tool-event: dit document telt het
daarom niet als een herhaalde meting van de gecorrigeerde controle, alleen als
aanwijzing dat de eerstvolgende run de gecorrigeerde controle op 5/5 zal
zetten.

**De fix.** De controle is verplaatst naar stap 1 en toetst nu
`"kvk__mijn_bedrijf" in tools` op die beurt, met een commentaarblok dat
vastlegt waarom (`services/host/scripts/onderzoeksflow.py`, rond de aanroep
van `loop.beurt(...)` in stap 1). Stap 2 checkt nu alleen nog
`netbeheerder__verbruik` en `regelrecht__execute_law`, met een regel
commentaar die uitlegt waarom `kvk__mijn_bedrijf` daar bewust niet meer
staat. De controle is verplaatst, niet verwijderd: dekking op "is de KvK
geraadpleegd" blijft bestaan, alleen op de juiste beurt.

### 2. `de bron-waarden staan in het antwoord (geen)` op stap 6: 0/5 → vuurt niet meer op die beurt

**Wat er verkeerd aan was.** Een eerdere correctie in deze reeks (zie
"Een correctie aan het script, ná de gerapporteerde meting" in
`eindmeting-2026-08-13.md`) beperkte deze controle al tot een beurt die zelf
een feiten-tool aanriep, via de verzameling `_BRONTOOLS` = `{kvk__mijn_bedrijf,
netbeheerder__verbruik, regelrecht__execute_law}`. Dat loste het probleem
destijds op, maar niet blijvend: sinds de orkestratielus (taak 4) draait
`regelrecht__execute_law` op **elke** beurt opnieuw — ook stap 6 ("Ja, dien
maar in."), waar de enige nieuwe actie `rvo__indienen` is. Omdat
`regelrecht__execute_law` in `_BRONTOOLS` zat, telde de poort stap 6 alsnog
als "er draaide een feiten-tool", en eiste de controle een letterlijk
bedrijfsfeit (naam, straat, elektriciteit of gas) in een beurt die terecht
alleen een indienbevestiging geeft. `regelrecht__execute_law` levert zelf
nooit een van die vier feiten op (`feiten.py:_uit_kvk` /
`_uit_netbeheerder`) — het geeft een regel-oordeel, geen bedrijfsgegeven.

**De fix.** Een nieuwe, smallere verzameling `_FEITENTOOLS = {kvk__mijn_bedrijf,
netbeheerder__verbruik}` vervangt `_BRONTOOLS` als poort voor deze controle;
`_BRONTOOLS` zelf is verwijderd (had geen andere gebruiker meer). De
docstring van `_controleer_slots` legt de geschiedenis vast: waarom de eerdere
poort niet blijvend werkte, en waarom `regelrecht__execute_law` bewust
uitgesloten is. Met deze fix vuurt de controle op stap 6 helemaal niet meer
(geen kvk- of netbeheerder-aanroep op die beurt), en blijft hij ongewijzigd
op stap 2 draaien, waar hij al 5/5 stond. Ook dit is niet opnieuw over vijf
schone runs gemeten binnen deze taak — de eerstvolgende keer dat het script
draait, telt de gecorrigeerde versie vanzelf mee.

## Open punt, niet gerepareerd: bedrijfsnaam 4/5

`het antwoord noemt de bedrijfsnaam van het scherm`: **4/5**, tegenover 5/5 in
de eindmeting. Eén run (run 1) noemde in stap 2 het verbruik en de
regeluitkomst wel, maar niet de bedrijfsnaam zelf:

> Ik heb uw verbruik opgehaald uit de Business Wallet. Dat is 420.000 kWh
> elektriciteit en 140.000 m³ gas (peiljaar 2025). De energiebesparingsplicht
> **geldt** voor uw bedrijf. […]

Dit wordt hier vastgelegd als open aandachtspunt, niet weggepoetst als ruis:
één afwijking op vijf runs kan ruis zijn, maar het is ook precies het soort
weglating dat de respondent niet opvalt totdat hij het rapport controleert.
Geen fix in deze taak — buiten scope, en één run is te weinig om een oorzaak
aan te wijzen (prompt-variatie, of het model dat de naam als impliciet
beschouwt omdat de vraag al over "mijn bedrijf" ging).

## De eerdere schijn-overtreding van PDR-008

Een eerdere meting in deze reeks (commit `9496cc0`, zie
`.superpowers/sdd/2026-08-13-regel-stuurt-de-flow/progress.md` rond "METING
LEGT ECHTE PDR-008-OVERTREDING BLOOT") liet
`geen toestemmingsplichtige bron geraadpleegd vóór toestemming (PDR-008)` op
**1/5** zien. Na de harde host-poort (`vlam_host._bron_aanroep_gated`) bleef
dat cijfer bij hermeting nog steeds 1/5 — maar zelfnagemeten hield de poort
wél stand: vijf weigeringen in de hostlog, geen `netbeheerder`-audit ná zo'n
weigering. De controle telde dus een **geweigerde poging** als een
**raadpleging**, omdat de host tot dan toe al vóór de poort een `tool`-event
verstuurde. Dat is in commit `9a70e0a` (waarop deze meting draait) gefixt op
twee plekken:

1. de host stuurt geen `tool`-event meer voor een aanroep die de PDR-008-poort
   weigerde (`vlam_host.py`);
2. het meetscript kruist zelf ook expliciet tegen een `bron_fout`-event met
   code `TOESTEMMING_VEREIST`, zodat het niet opnieuw stil op deze
   eventvolgorde-aanname kan gaan leunen
   (`_geraadpleegde_toestemmingstools`, met de reden in de docstring
   vastgelegd).

In deze meting staat de controle terecht weer op 5/5 (zie de tabel hierboven).
Het onderscheid — poging versus raadpleging — is dus niet alleen in deze
meting hersteld, maar ook structureel in de controle zelf vastgelegd, zodat
een toekomstige eventvolgorde-regressie niet opnieuw als een PDR-008-
overtreding wordt gerapporteerd die er niet is.

## Wat vijf runs niet zegt

Zoals ook de eindmeting al benadrukte: vijf runs is een peiling, geen bewijs.
Bij een onderliggende foutkans van ⅓ mist een reeks van vijf schone runs die
fout nog in ongeveer 13% van de gevallen (0.67⁵ ≈ 0.135). Elke 5/5-regel in de
tabel hierboven kan dus nog steeds een reëel, niet-triviaal risico verbergen —
inclusief de twee controles die in deze taak zijn bijgewerkt en die (nog) niet
opnieuw over vijf schone runs zijn gemeten. De adrescontrole vuurde in deze
vijf runs helemaal niet (geen enkele run noemde een adresregel in het
gevraagde formaat), tegenover 1/5 in de eindmeting — te weinig signaal in
beide richtingen om iets over te concluderen.

## Herhalen

```bash
# host draait al op poort 8000 met vijf bronnen verbonden, niet herstarten
uv run python services/host/scripts/onderzoeksflow.py \
  --mode vlam --kvk 62345681 --runs 5 --json /tmp/meting-regelloop.json
```
