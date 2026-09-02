# Product Decision Records (PDRs)

Beslissingen rond de Digitale Assistent. Lees de PDRs in volgorde — elke nieuwe beslissing bouwt op de vorige voort.

## Geldige beslissingen

| # | Onderwerp | Status |
|---|---|---|
| [PDR-001](PDR-001-dual-llm-backend.md) | Dual LLM-backend (VLAM + Claude) met gedeelde MCP-tools | Geaccepteerd |
| [PDR-005](PDR-005-cli-vs-mcp-transport.md) | CLI vs MCP als transport voor tool-uitvoering | Geaccepteerd |
| [PDR-006](PDR-006-feasibility-conclusie.md) | Feasibility-conclusie MCP en CLI; uitbreiding overheidsstandaard | Geaccepteerd |
| [PDR-007](PDR-007-demo-persona-en-netbeheerder-bron.md) | Demo-persona's, netbeheerder/Business Wallet en EML-maatregelen | Geaccepteerd |
| [PDR-008](PDR-008-generieke-regelrecht-tool-en-wallet.md) | Eén generieke RegelRecht-tool en energiegegevens via de Business Wallet | Geaccepteerd |
| [PDR-009](PDR-009-sessie-identiteit-host-side.md) | Bedrijfsidentiteit server-side bepaald door de host-sessie (MVP-01) | Geaccepteerd |
| [PDR-010](PDR-010-sleutel-van-de-gebruiker.md) | De LLM-sleutel komt van de gebruiker, niet van de server (MVP-02) | Geaccepteerd |
| [PDR-011](PDR-011-foutmeldingen-catalogus.md) | Foutmeldingen uit één catalogus, met wat er misging én wat je kunt doen | Geaccepteerd |
| [PDR-013](PDR-013-timeoutgrenzen-op-basis-van-meting.md) | Time-outgrenzen op basis van meting, met levensteken en herkansingen | Geaccepteerd |
| [PDR-014](PDR-014-chat-geparkeerd-tot-de-vertaling-naar-wet-klopt.md) | Chat geparkeerd tot de vertaling van vraag naar wet en invoer klopt; daarna doortrekken, eventueel in een andere vorm (Digitale assistent 2.0) | **Voorgesteld** |

## Vervangen of ongeldig verklaarde beslissingen

Bewust bewaard voor audit-trail; niet meer van toepassing op de codebase.

| # | Onderwerp | Status | Toelichting |
|---|---|---|---|
| [PDR-002](PDR-002-vlam-timeout-fallback.md) | VLAM timeout en graceful fallback | **Ongeldig** sinds 15 april 2026 | VLAM tool-calling stabiliseerde; fallback-logica is verwijderd uit `vlam_host.py`. De grenzen (30/60 s) zijn op 24 augustus vervangen door [PDR-013](PDR-013-timeoutgrenzen-op-basis-van-meting.md). |
| [PDR-003](PDR-003-vlam-orchestrated-tool-use.md) | VLAM host-gestuurde tool-aanroepen | **Ongeldig** sinds 15 april 2026 | VLAM ondersteunt nu native tool-calling stabiel; orchestratie-modus geschrapt. |
| [PDR-004](PDR-004-cli-profiel-voor-overheidsstandaard.md) | CLI-profiel voor overheidsstandaard | **Vervangen** op 9 mei 2026 | Inhoud verplaatst naar het standaard-voorstel in [`moza-mcp-standaard-poc`](https://github.com/MinBZK/moza-mcp-standaard-poc) (buiten scope van deze repo). |

## Conventies

- **Bestandsnaam**: `PDR-NNN-korte-titel.md` (engelse-streepjes, lowercase). De titel beschrijft de inhoud, niet alleen het type.
- **Frontmatter**: tabel met Status, Datum, Beslisser(s), Gerelateerd. Bij vervanging of ongeldigheid: voeg een waarschuwingsblok bovenaan toe en zet de status op "Ongeldig" of "Vervangen".
- **Audit-trail**: ongeldig verklaarde of vervangen PDRs blijven staan. Verwijder ze niet — ze documenteren waarom we vandaag staan waar we staan.
- **Test-materiaal** hoort niet hier; testvragen voor handmatige verificatie staan in [`../test-vragen.md`](../test-vragen.md).

## Schrijftips voor een nieuwe PDR

- Begin met **Context** (waarom moest dit besloten worden), dan **Beslissing**, dan **Alternatieven overwogen**, dan **Consequenties**.
- Wees concreet in alternatieven. "We hebben dit overwogen, en hier is waarom we het niet kozen" is waardevoller dan een afgevinkte lijst.
- Verwijs naar code, prompts en validatiekader-dimensies waar van toepassing.
- Een PDR is geen tutorial. Houd het kort genoeg om in tien minuten te lezen; verwijs voor diepe technische details naar de code of een rapport in `docs/`.
