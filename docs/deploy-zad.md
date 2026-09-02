# Deployen naar ZAD

Praktische notities voor het deployen en debuggen van de backend op ZAD.

> **Twee soorten kennis in dit document.** Wat onder "Deze deployment" staat is
> voor dit project geverifieerd. Wat onder "Platformgedrag" staat komt uit een
> zusterproject op hetzelfde platform (FBS Berichtenbox); de mechaniek is
> dezelfde, maar de details zijn hier niet stuk voor stuk nagemeten. Kom je er
> iets tegen dat afwijkt, corrigeer het dan hier.

## Deze deployment

Gedefinieerd in [`.github/workflows/production.yml`](../.github/workflows/production.yml):

| Veld | Waarde |
|---|---|
| Project-id | `pm-5sj` (hetzelfde project als de frontend) |
| Deployment | `poc` |
| Component | `dabackend` |
| Action | `RijksICTGilde/zad-actions/deploy@v4` |
| Secret | `ZAD_API_KEY` (enige; er staan bewust géén LLM-sleutels op) |

De backend is **internal-only**: niet "Publiceer op het web". De frontend-pod
zit in dezelfde namespace en bereikt de backend intern. Omdat er geen publieke
route is, kan de externe readiness-poll van de action er niet bij —
vandaar `wait-for-ready: "false"`. ZAD's eigen readiness-probe (`GET /health`)
staat los daarvan in de component-config.

**Component-config (staat niet in deze repo):**

- `TEST_KVK_NUMMERS=85234567,62345681,56789012,61234570` — de gesloten testgroep
  (PDR-009). Deze lijst moet elke persona dekken die `MinBZK/moza-poc` op
  `actief` zet; ontbreekt er één, dan ziet de deelnemer zijn bedrijf op het
  scherm en antwoordt de assistent "log eerst in". Wijzigt de lijst, dan ook
  `services/host/.env.example` en `services/host/tests/conftest.py` bijwerken —
  die drie lopen niet automatisch gelijk.
- `ALLOWED_ORIGINS` is **niet gezet**, en dat is bewust. Leeg betekent geen
  enkele cross-origin toegang; de frontend praat via een same-origin reverse
  proxy, dus CORS komt er niet aan te pas. Zet hier niets in "voor de zekerheid" —
  dat opent iets wat nu dicht is.
- Geen `ANTHROPIC_API_KEY` / `VLAM_API_KEY`: gebruikers leveren hun eigen sleutel
  via de UI (PDR-010).
- **Geen `MCP_SERVER_NETBEHEERDER`.** De EU Business Wallet (netbeheerder-mock)
  staat standaard **aan**: zonder de variabele start de host de server op het
  standaardpad. `MCP_SERVER_NETBEHEERDER=uit` was een tijdelijke instelling
  voor het gebruikersonderzoek van augustus (de respondent gaf zijn verbruik
  zelf op) en hoort op geen enkel component meer te staan. Staat hij er wel,
  dan waarschuwt de host bij het opstarten (`Bron 'netbeheerder' ... staat
  bewust uit`) en toont `GET /health` hem onder `bronnen_uit`. Controleer dat
  na elke uitrol: `bronnen_uit` hoort `[]` te zijn.

### Valkuil: kale hostnamen in de nginx-proxy

Een 502 vanaf de frontend kwam voort uit de nginx-resolver die de kale hostnaam
`dabackend` niet oploste. Zet `BACKEND_ORIGIN` op de FQDN:

```
http://dabackend.<namespace>.svc.cluster.local:8000
```

## Onderzoeksomgeving

Een tweede link, los van `poc`, voor de sessies van het gebruikersonderzoek.
Gedefinieerd in [`.github/workflows/onderzoek.yml`](../.github/workflows/onderzoek.yml)
(backend) en `onderzoek.yml` in `MinBZK/moza-poc` (frontend). Beide alleen via
`workflow_dispatch` met een `ref`-input: een uitrol tijdens een sessie wist de
sessiestate van de respondent, dus uitrollen is een besluit, geen bijvangst.

| Veld | Waarde |
|---|---|
| Deployment | `gebruikersonderzoek` |
| Componenten | `dabackend-onderzoek` (backend, internal-only) en `proef-onderzoek` (frontend) |
| Link | `https://proef-onderzoek.gebruikersonderzoek-2026-03-moza.rijksapp.dev` |

Waarom eigen componenten: env staat op ZAD **per component, projectbreed**. Een
variabele op `dabackend` geldt dus in élke deployment waar dat component draait
(`poc`, alle previews). De onderzoeksomgeving wijkt op twee punten af, en die
afwijking hoort niet op `poc` te belanden:

- `dabackend-onderzoek` draagt tijdens de sessies een `ANTHROPIC_API_KEY`, zodat
  respondenten geen sleutel hoeven in te vullen. Dat is een bewuste, tijdelijke
  afwijking van PDR-010, beperkt tot deze niet-gepubliceerde link. **Na het
  onderzoek gaat de sleutel er weer af.** Verder dezelfde env als `dabackend`
  (`TEST_KVK_NUMMERS`; `ALLOWED_ORIGINS` leeg; geen `MCP_SERVER_NETBEHEERDER`,
  want de Business Wallet staat standaard aan; tijdens de sessies van augustus
  stond hij hier bewust uit).
- `proef-onderzoek` heeft `BACKEND_ORIGIN` op
  `http://dabackend-onderzoek.<namespace van gebruikersonderzoek>.svc.cluster.local:8000`
  (FQDN, zie de valkuil hierboven).

De frontend staat default op mode `claude`; zonder sleutel in de UI gebruikt de
host de server-env-sleutel. Meer is er niet nodig.

**Inrichten (eenmalig, in de ZAD-UI):** de twee componenten aanmaken in project
`pm-5sj` met bovenstaande env en dezelfde poorten/resources als `dabackend` en
`proef`; `dabackend-onderzoek` niet publiceren. Daarna in beide repo's de
workflow "Onderzoek deploy" starten met de gewenste `ref`.

## Platformgedrag

ZAD draait op **Argo CD GitOps**: de bron van waarheid is Git, niet de cluster en
niet de Operations-Manager-API. De Argo-Applications hebben `selfHeal: true` en
`prune: true`, dus een directe `kubectl`-wijziging of een live aanpassing aan een
draaiende deployment wordt teruggedraaid naar wat in Git staat. Schalen of
reactiveren gaat via OM — dat commit naar de Git-repo die Argo volgt.

Drie lagen, alle drie `RijksICTGilde`-repo's (deels privé):

| Repo / pad | Wat |
|---|---|
| `rig-cluster-projects` → `projects/<project-id>.yaml` | OM-projectspec: componenten, resources, aliassen, versleutelde env. |
| `argo-applications` → `odcn-production/<project-id>/` | Eén Argo-Application per deployment; toont `repoURL`/`path` en de `syncPolicy`. |
| `rig-cluster-application-test` → `odcn-production/<project-id>/<deployment>/` | **De gerenderde manifests die Argo daadwerkelijk synct.** Hier staat de échte image-tag én `replicas`. |

Die laatste is de grond-waarheid bij elk pull- of schaalprobleem.

### Debug-valkuilen

- **"Uitgeschakeld: image ontbreekt" in de UI, plus "No resources found in
  namespace" in de logs** betekent `replicas: 0` in het gerenderde
  `*-deployment.yaml`. Er draait niets: het is een schaalprobleem, geen
  image-probleem.
- **De ImagePullBackOff onder "Technische details" kan een bevroren, verouderd
  event zijn** terwijl het gesyncte manifest allang een geldige tag heeft.
  Controleer eerst de tag en `replicas` in het gerenderde manifest voordat je de
  UI-tekst gelooft.
- **`:refresh`, "herverwerken" in de UI en `PUT .../image` reactiveren een
  uitgeschakeld component niet** — ze verhogen `replicas` niet. Een deployment op
  0 zit in een deadlock: geen pod → geen verse pull → de controller
  herverifieert de image nooit. De werkende fix is de deployment **herscheppen**:
  `DELETE` gevolgd door `:upsert-deployment`. Upsert-na-delete is een create, dus
  die start enabled. Env overleeft, want die staat in de projectspec.
- **`DELETE` is destructief** bij projecten met een `postgresql-database`-service:
  Argo `prune` + `database_cleanup` gooit de data weg. Dit project heeft geen
  databaseservice, maar controleer dat vóór je het doet.
