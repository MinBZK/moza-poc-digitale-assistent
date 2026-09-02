# Beeldmateriaal PDR-014 — shotlist

Werkbestand, weg zodra alle beelden er staan. De PDR verwijst al naar de
bestandsnamen hieronder; zet een beeld op die naam en de verwijzing werkt.

Uitgangspunt: in de onderbouwing staan **letterlijke logs van het moment dat
het misgaat**, geen schema's. Schema's alleen in Context (fig0, fig1) en bij
de juristensessies (fig7, fig8); haal ze weg als ze afleiden.

Geen browser in de ontwikkelomgeving van Claude. Wat zonder taalmodel
reproduceerbaar was, staat er al (fig3). De rest vraagt een draaiende host met
een sleutel, of de ZAD-logs van de onderzoeksomgeving.

Formaat: PNG, breedte ≥ 1600 px. Geen sleutels, tokens of URL's van de
onderzoeksomgeving in beeld; alleen de fictieve persona's.

| # | Bestand | Status | Waar in de PDR | Wat het laat zien |
|---|---|---|---|---|
| 0 | `fig0-toets-bij-regelrecht.png` | aanwezig (sessieschema) | Context | de toets ligt bij RegelRecht |
| 1 | `fig1-beslismomenten.png` | aanwezig (sessieschema) | Context | B4/B5/B6 = taalmodel |
| 3 | `fig3-log-250000-engine.png` | **aanwezig, gerenderd uit `log3-250000-engine.txt`** (2 sept, echte engine, geen taalmodel) | Onderbouwing A, invoerwaarden | `"250.000"` → 250, `-65000` → plicht vervalt |
| 4 | `fig4-hostlog-maatregelen-eigen-aanroep.png` | **aanwezig, gerenderd uit `log4-hostlog-model-roept-regel-zelf.txt`** (host-log 2 sept) | Onderbouwing A, verkeerde wet/bron/moment | model roept de regel zelf aan; host hergebruikt de uitkomst |
| 5 | `fig5-hostlog-toestemming-vereist.png` | **aanwezig, gerenderd uit `log5-hostlog-toestemming-geweigerd.txt`** (host-log 2 sept) | Onderbouwing A, toestemmingspoort | model roept KvK en wallet aan vóór Delen; poort weigert |
| 6 | `fig6-zadlog-verbruik-als-tekst.png` | MAKEN (ZAD-log 25 aug) | Onderbouwing A, invoerwaarden | respondent typt verbruik als tekst; regelloop wacht op opgave; assistent vraagt opnieuw |
| 7 | `fig7-route-b5.png` | aanwezig (sessieschema) | Onderbouwing B | classificatieroute met B5 |
| 8 | `fig8-sadee-financieel-cv.png` | aanwezig (regelrecht-repo) | Onderbouwing C | zeven regelingen op dezelfde feiten |
| 9 | `fig9-schermschets-vooringevuld.png` | MAKEN (Keynote-export) | Beslissing 2 | concept-aanvraag met bron + ophaaldatum per gegeven |

## fig3 opnieuw maken

```bash
# schrijft log3-250000-engine.txt opnieuw (echte engine, ~1 s) en rendert de PNG
uv run python docs/decisions/assets/pdr-014/maak-log3.py
```

Bestaat het script niet meer: de aanroepen staan in de txt zelf (vier keer
`execute_law` op `omgevingswet/energiebesparing/informatieplicht`, service
RVO, tegen `REGELRECHT_RPC_URL`). Wil je liever een echte terminal-screenshot
dan de gerenderde PNG: `cat` de txt in een terminal en schiet die.

## fig4 en fig5 opnieuw maken

Beide komen uit de host-log van een gewone meting op main (zie
`docs/superpowers/plans/2026-09-02-toets-pdr-014.md`, "Herhalen"). Host
starten met `LOG_LEVEL=INFO`, de onderzoeksflow één keer draaien, en:

```bash
grep -B1 "geweigerd zonder vastgelegde toestemming" /tmp/host.log   # fig5
grep -B1 "Regel al bepaald door de regelloop" /tmp/host.log          # fig4
```

Liever een echte terminal-screenshot dan de gerenderde PNG: `cat` de txt.

## fig6 — ZAD-log van 25 augustus

ZAD-UI → deployment `gebruikersonderzoek` → component `dabackend-onderzoek` →
logs. Tijdvenster: sessie van 25 augustus, 11:00–12:00. Zoek op `opgave`,
`wacht_op`, `verbruik`. Het beeld: de beurt waarin de respondent
"… kWh en … m3" typt, gevolgd door de regelloop die op `opgave` blijft
staan en de assistent die het verbruik opnieuw vraagt. Staat de log niet meer
in ZAD (bewaartermijn), dan lokaal reproduceren op `365d46b` (de ouder van
`af6924d`) met de wallet uit (`MCP_SERVER_NETBEHEERDER=uit`) en het verbruik
als chatbericht sturen in plaats van via het formulier; het meetscript doet
dat niet vanzelf, dus dan via de frontend of met `curl` op `/chat/stream`.

**Redigeren vóór opname:** sleutels en tokens redigeert de host al
(`log_redaction.py`); controleer op de pod-naam, de hostnaam en de URL.

## fig9 — schermschets Vooringevuld

Uit `~/projects/vooringevuld-onepager_RM.key` (Keynote): de slide met de
concept-aanvraag exporteren als PNG. Bestaat er nog geen schets met een
gegevensregel "bron + ophaaldatum", dan is dat de eerste schets om te maken;
de PDR verwijst er nu al naar als werkhypothese.

## Bewust geen beeld

- **"Bloemenlaan 12" in het rapport.** Eén run op 13 augustus, ruwe log niet
  bewaard, niet op commando reproduceerbaar. Blijft een citaat uit
  `NEXT_STEPS.md`.
- **Meting 5/5 → 1/5.** Alleen als tabel zichtbaar
  (`docs/superpowers/plans/meting-regelloop-2026-08-13.md`); de ruwe
  `meting-def.log` staat niet in git.
- **RVO-stappenplan.** De vergelijking is verloren gegaan; geen beeld tenzij
  de analyse opnieuw wordt gemaakt.
