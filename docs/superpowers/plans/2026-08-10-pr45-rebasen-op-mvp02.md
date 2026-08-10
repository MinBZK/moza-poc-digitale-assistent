# PR #45 rebasen op #44 — implementatieplan (W1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** PR #45 (foutmeldingen, PDR-011) staat op main bovenop PR #44 (MVP-02),
zonder dat een van de twee beveiligingsfixes uit #44 stilzwijgend terugkomt.

**Architecture:** Geen herontwerp. Achttien conflicthunks oplossen, waarvan twee
gevaarlijk: daar draait de voor de hand liggende resolutie een fix uit #44 terug.
De tests uit #44 zijn het vangnet dat dat betrapt, dus die moeten eerst op main
staan.

**Tech Stack:** git, Python 3.12, pytest, ruff, uv.

## Global Constraints

- **Volgorde ligt vast:** #44 → main, dán #45 rebasen op main. Andersom levert
  dezelfde conflicten op zonder dat `test_key_isolation.py` en
  `test_subprocess_env.py` je beschermen tijdens het oplossen.
- **`.github/workflows/` is in deze ontwikkelomgeving beschermd.** Wijzigingen
  daar worden teruggedraaid; een rebase struikelt daarom op dependabot-commits
  die die map raken. Draai de echte rebase buiten deze omgeving, of sla die
  commits over.
- Commits zonder `Co-Authored-By`-trailer.
- Gemeten op 2026-08-10 met `git merge --no-commit --no-ff` tussen
  `origin/feat/foutmeldingen-specifiek` en `origin/feat/mvp-02-key-blootstelling`.
  Wijkt het aantal hunks af, dan is een van beide branches sindsdien veranderd —
  controleer dat vóór je dit plan volgt.

## De twee valkuilen

Lees deze eerst. Beide zien eruit als een gewone "kies een kant"-keuze en beide
maken de codebase stilletjes onveiliger als je #45 kiest.

**1. `services/host/cli_executor.py`, de `env=`-parameter.**
#45 schrijft `env=subprocess_env`, #44 schrijft `env=subprocess_env(CLI_ALLOWLIST, env)`.
Kies je #45, dan erven de bash-subprocessen weer de volledige omgeving inclusief
`ANTHROPIC_API_KEY` en `VLAM_API_KEY`. Dat is exact het gat dat #44 dichtte.
**#44 wint.** `test_subprocess_env.py::test_cli_subprocess_krijgt_de_beperkte_env`
betrapt een verkeerde keuze.

**2. `services/host/vlam_host.py`, de body van `chat_stream` (hunk 4, 73 tegen 41 regels).**
#45 gebruikt nog `orig_claude, orig_vlam = self.claude_client, self.vlam_client`
met herstel in een `finally`. #44 verving dat door de contextmanager
`_request_clients`, die de client als argument doorgeeft. Kies je #45, dan is de
gedeelde-state-bug terug: bij twee gelijktijdige gesprekken kan de sleutel van de
één het verzoek van de ander bedienen. #45 weet dit zelf — er staat een comment
"wordt opgelost in PR #44". **#44's structuur wint; #45's inhoud gaat erin.**
`test_key_isolation.py` betrapt een verkeerde keuze.

## De achttien hunks

### Mechanisch — beide kanten behouden (9 hunks)

| Bestand | Wat er botst | Resolutie |
|---|---|---|
| `docs/decisions/README.md` | #45 voegt de PDR-011-regel toe, #44 de PDR-010-regel | Beide regels, PDR-010 boven PDR-011 |
| `pyproject.toml` | `known-first-party`: #45 voegt `errors` toe, #44 `log_redaction` | De vereniging van beide lijsten |
| `services/host/mcp_client.py` | #45 importeert uit `errors`, #44 uit `subprocess_env` | Beide imports |
| `services/host/scripts/run_scenarios.py` | #45 importeert `ALLOW_API_KEY_OVERRIDE`, #44 `vlam_host` + de `sys.path`-fix | Beide. **De `sys.path`-fix uit #44 moet mee**, anders faalt het script op `ModuleNotFoundError: No module named 'config'` — nagemeten op de #45-branch |
| `services/host/tests/conftest.py` | #45 zet `TEST_KVK_NUMMERS`, #44 voegt de redactie-state-fixture toe | Beide |
| `services/host/vlam_host.py` hunk 1, 2 | Importblokken | Beide |
| `services/host/api.py` hunk 1 | Importblokken | Beide |
| `services/host/cli_executor.py` hunk 1 | Importblokken | Beide |

### Inhoudelijk — samenvoegen, niet kiezen (7 hunks)

| Bestand | Wat er botst | Resolutie |
|---|---|---|
| `vlam_host.py` hunk 3 | #45 `if not self.vlam_client`, #44 `if not vlam` | #44's parameter, met #45's foutmelding eromheen |
| `vlam_host.py` hunk 4 | Zie valkuil 2 | #44's `_request_clients`, met #45's dispatch en foutafhandeling erin |
| `vlam_host.py` hunk 5, 8 | #45 introduceert `_bron_aanroep`, #44 wijzigde de logging in dezelfde `try` | #45's `_bron_aanroep` met #44's logdiscipline (exceptietype op ERROR, volledige melding op DEBUG) |
| `vlam_host.py` hunk 6 | `_chat_claude`-signatuur: #44 voegt de verplichte `claude`-parameter toe | #44's signatuur; #45's body |
| `vlam_host.py` hunk 7 | #45 `_lees_tool_argumenten`, #44 `_inject_session_kvk` | Beide: eerst argumenten lezen, dan het sessie-KvK injecteren |
| `api.py` hunk 2 | #45 voegt een `RequestValidationError`-handler toe, #44 `check_origin_boundary` | Beide |
| `api.py` hunk 3 | Beide herschreven de SSE-routes | #44's `_sse_chunks` en `aclosing`, met #45's foutafhandeling en meldingen |

### Vraagt een besluit, geen resolutie (1 hunk)

`services/host/.env.example`, `ALLOW_API_KEY_OVERRIDE`. #45 zet `false` met de
redenering "zet expliciet op false in productie". #44 zet `true` met de
redenering uit PDR-010: de deployment draait zonder serversleutels en elke tester
brengt zijn eigen sleutel mee. Die twee spreken elkaar tegen; dit is geen
opmaakconflict.

De stand die bij het gebruikersonderzoek hoort is `false` mét een serversleutel,
maar alléén in het venster van 25–27 augustus (zie het addendum in het W0-plan).
De repo-default hoort `true` te blijven zolang PDR-010 geldt. **Neem hier `true`
over en beschrijf de onderzoeksuitzondering in het commentaar**, zodat er geen
vierde document ontstaat dat iets anders beweert — deze repo had dat probleem al
met `ALLOWED_ORIGINS`.

---

### Task 1: #44 naar main

**Files:** geen; dit is een merge.

- [ ] **Step 1: Controleer dat #44 groen en gereviewd is**

Run: `gh pr view 44 --json reviewDecision,mergeable,statusCheckRollup`
Expected: gereviewd (ericwout-overheid, 2026-08-06, verwerkt) en mergeable.

- [ ] **Step 2: Merge #44**

Merge via GitHub. Dit is de stap die alles deblokkeert: zonder #44 op main kan
#45 niet rebasen én bestaat `docs/decisions/PDR-010-sleutel-van-de-gebruiker.md`
nergens, waardoor het W0-addendum niet geschreven kan worden.

- [ ] **Step 3: Controleer main**

Run: `git checkout main && git pull && uv run pytest -q && uv run ruff check .`
Expected: alles groen.

---

### Task 2: Rebase #45 en los de achttien hunks op

**Files:** de negen bestanden uit de tabellen hierboven.

- [ ] **Step 1: Start de rebase**

```bash
git checkout feat/foutmeldingen-specifiek
git pull
git rebase main
```

Struikelt de rebase op een dependabot-commit die `.github/workflows/` raakt, dan
zit je in een omgeving die die map beschermt (zie Global Constraints).

- [ ] **Step 2: Los de negen mechanische hunks op**

Volg de eerste tabel. Behoud bij elk van deze hunks beide kanten; er gaat niets
verloren en er valt niets te kiezen.

- [ ] **Step 3: Los de zeven inhoudelijke hunks op**

Volg de tweede tabel. Werk `vlam_host.py` hunk 4 als laatste: die is de grootste
en de andere hunks in dat bestand geven je de namen die je erin nodig hebt.

- [ ] **Step 4: Neem het besluit over `.env.example`**

Zet `ALLOW_API_KEY_OVERRIDE=true` en beschrijf de onderzoeksuitzondering in het
commentaar eromheen, met een verwijzing naar het addendum in PDR-010.

- [ ] **Step 5: Draai de tests die de twee valkuilen bewaken**

```bash
uv run pytest services/host/tests/test_key_isolation.py services/host/tests/test_subprocess_env.py -q
```

Expected: PASS. Falen deze, dan heb je in valkuil 1 of 2 de verkeerde kant
gekozen — ga terug naar de betreffende hunk voordat je verder gaat.

- [ ] **Step 6: Draai alles**

```bash
uv run pytest -q && uv run ruff check . && uv run python services/host/scripts/run_scenarios.py
```

Expected: suite groen, ruff schoon, zeven scenario's geslaagd. Faalt het script
op `ModuleNotFoundError: No module named 'config'`, dan is de `sys.path`-fix uit
#44 bij hunk `run_scenarios.py` weggevallen.

- [ ] **Step 7: Rond de rebase af en push**

```bash
git rebase --continue
git push --force-with-lease
```

`--force-with-lease` en niet `--force`: als er intussen iemand op de branch heeft
gepusht, hoort de push te weigeren in plaats van dat werk te overschrijven.

---

### Task 3: Controleer wat alleen ná de merge te controleren is

**Files:** geen; dit is verificatie.

- [ ] **Step 1: De sleutelmelding met een serversleutel**

Uit het W0-plan: de frontend toont nu "Vul uw API-sleutel in via het
instellingenpaneel" (`digitale-assistent.js:779`). Met `ALLOW_API_KEY_OVERRIDE=false`
en een serversleutel hoort die tekst nooit te verschijnen. #45 herschrijft precies
deze meldingen (`LLM_GEEN_SLEUTEL` versus `LLM_NIET_INGESTELD`), dus dit is pas
nu te controleren.

Run de host met `ALLOW_API_KEY_OVERRIDE=false` en zónder sleutel, en stel één
vraag. Expected: de melding "de assistent is in deze omgeving niet volledig
ingesteld — meld dit bij de beheerder", niet "vul uw sleutel in".

- [ ] **Step 2: De zes openstaande reviewbevindingen opnieuw wegen**

Drie van de tien bevindingen uit de review van 2026-08-10 zijn opgelost
(34afbfa, 306b92a, 07404dd). Van de zes die openstaan zijn er twee de moeite
waard vóór het onderzoek: de brede `except Exception` in `vlam_host.py` (een
hostbug die zich voordoet als modelfout stuurt de observatie tijdens een sessie
de verkeerde kant op) en het wegvallen van de anti-impersonatieregels uit
`kvk.md` als de KvK-bron offline is (de respondent speelt een persona; juist dan
moet de assistent een verkeerde identiteitsaanname tegenspreken).

Bevinding 5 (nul zoekresultaten) is bewust niet opgelost: de melding klopt, en de
onderliggende vraag — mag de assistent zelf breder zoeken — is een PDR-011-keuze
die niet stilzwijgend teruggedraaid hoort te worden.

## Zelfreview van dit plan

**Spec-dekking.** Dit is W1 uit de spec. De uiterste datum van 16 augustus staat
er bewust niet in als stap: die is afgeleid, niet gegeven, en de repo-eigenaar
heeft bevestigd dat de review haalbaar is.

**Wat hier niet in staat.** De inhoud van de zes openstaande reviewbevindingen
staat in de reviewrapportage, niet hier; dit plan verwijst er alleen naar zodat
ze niet uit beeld raken bij de merge.

**Aanname die kan verlopen.** De achttien hunks zijn gemeten op 2026-08-10.
Verandert een van beide branches, dan verandert de kaart. Step 1 van Task 2
merkt dat vanzelf op, maar de tabellen kloppen dan niet meer.
