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

### Valkuil: kale hostnamen in de nginx-proxy

Een 502 vanaf de frontend kwam voort uit de nginx-resolver die de kale hostnaam
`dabackend` niet oploste. Zet `BACKEND_ORIGIN` op de FQDN:

```
http://dabackend.<namespace>.svc.cluster.local:8000
```

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
