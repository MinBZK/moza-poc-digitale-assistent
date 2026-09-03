"""Foutcatalogus: elke faalsituatie krijgt een eigen, actionabele melding.

Waarom een catalogus en niet een `str(e)` per plek: de host faalde overal met
dezelfde zin ("De assistent is op dit moment niet bereikbaar"), of gaf de
exception-tekst door aan het LLM. De gebruiker wist dan niet wat er misging en
al helemaal niet wat hij eraan kon doen.

Elke melding bestaat uit twee delen:
  - `bericht` — wat er gebeurde, in gewone taal, zonder jargon of foutcode;
  - `actie`   — wat de gebruiker nu kan doen.

Het `code`-veld is voor de logs, de UI en de tests; het komt nooit in een zin
terecht. Exception-teksten, paden en URL's gaan naar de log, niet naar de
gebruiker en niet naar het LLM.
"""

import json
import logging
import re
from dataclasses import dataclass, replace

import anthropic
import openai

logger = logging.getLogger("vlam.errors")

# Bovengrens voor tekst uit een bron of uit de vraag die we in een melding
# terugkaatsen. Die melding gaat naar de UI én naar het LLM met de instructie om
# 'm door te geven; zonder grens kan een bron er een lap tekst of een eigen
# "instructie" in kwijt en spreekt de assistent die met gezag uit.
MAX_ECHO_TEKENS = 80


def schoon_echo(waarde: object, maximum: int = MAX_ECHO_TEKENS) -> str:
    """Maak tekst van buiten geschikt om in een melding te herhalen.

    Regeleindes en opmaaktekens eruit (een melding is één zin, geen HTML en geen
    tweede instructie aan het model), en afkappen op een lengte die in een zin
    past. Dit is geen beveiligingsgrens maar wel de grens tussen "een bron meldt
    iets" en "een bron dicteert wat de assistent zegt".
    """
    tekst = re.sub(r"[\s]+", " ", str(waarde)).strip()
    tekst = re.sub(r"[<>{}\[\]]", "", tekst)
    if len(tekst) > maximum:
        tekst = tekst[:maximum].rstrip() + "..."
    return tekst


@dataclass(frozen=True)
class FoutMelding:
    """Eén faalsituatie, klaar om te tonen."""

    code: str
    bericht: str
    actie: str
    bron: str | None = None
    herstelbaar: bool = True
    http_status: int = 502
    # Zichtbaar voor de gebruiker? Een fout die het model zelf kan herstellen
    # (een verkeerd opgebouwde tool-aanroep) hoort niet als storing in de UI:
    # het model corrigeert en gaat door, de gebruiker merkt er niets van.
    zichtbaar: bool = True
    # Wat het model met deze fout moet doen. Standaard: doorvertellen. Bij een
    # eigen fout van het model juist niet.
    llm_instructie: str = ""

    @property
    def tekst(self) -> str:
        """De volledige melding als één string (vult het `message`-veld)."""
        return f"{self.bericht} {self.actie}".strip()


# --- Bronnen -----------------------------------------------------------------

# Hoe we een bron aan de gebruiker noemen, en waar hij terecht kan als de bron
# uitvalt. De sleutel is het server-voorvoegsel uit de tool-key (`koop__zoek...`).
BRON_LABELS: dict[str, str] = {
    "kvk": "het KvK Handelsregister",
    "koop": "de regelgeving-database (KOOP Regelingenbank)",
    "regelrecht": "de regeltoets (RegelRecht)",
    "rvo": "RVO",
    "netbeheerder": "uw Business Wallet (energiegegevens van de netbeheerder)",
}

# Hoe we de twee LLM-backends aan de gebruiker noemen. De host accepteert twee
# losse sleutels (`x-vlam-api-key`, `x-claude-api-key`), dus "vul uw sleutel in"
# zonder te zeggen wélke laat de gebruiker raden welk veld hij moet vullen.
BACKEND_LABELS: dict[str, str] = {"vlam": "VLAM", "claude": "Claude"}

BRON_ALTERNATIEF: dict[str, str] = {
    "kvk": "kvk.nl",
    "koop": "wetten.overheid.nl",
    "regelrecht": "rvo.nl",
    "rvo": "rvo.nl",
    "netbeheerder": "uw energierekening",
}


def scope_uit_tool(tool_key: str | None) -> str:
    """De servernaam vóór `__` in een tool-key (`koop__zoek_regelgeving` -> `koop`).

    Eén afspraak voor de toestemmingspoort, het tool-filter, de regelloop en
    het CLI-transport: zien die niet dezelfde scope, dan toont de een een tool
    die de ander weigert.
    """
    return str(tool_key or "").split("__", 1)[0]


def bron_uit_tool(tool_key: str) -> str | None:
    """Haal de bronnaam uit een tool-key, of None als het geen bekende bron is."""
    bron = scope_uit_tool(tool_key)
    return bron if bron in BRON_LABELS else None


# --- Catalogus ---------------------------------------------------------------

# Invulwaarden die een melding nodig kan hebben. Ontbreekt er één bij het
# opbouwen, dan valt de zin terug op een neutrale formulering in plaats van een
# KeyError: een foutmelding mag nooit zélf de oorzaak van een fout worden.
_STANDAARD_INVULLING: dict[str, str] = {
    "bron_label": "de bron",
    "alternatief": "de website van de betreffende instantie",
    "seconden": "de ingestelde tijd",
    "backend_label": "het AI-model",
    "maximum": "toegestaan",
    "veld": "een verplicht gegeven",
    "zoekterm": "uw zoekopdracht",
}


class _Invulling(dict):
    """Format-mapping die onbekende placeholders neutraal invult."""

    def __missing__(self, sleutel: str) -> str:
        return _STANDAARD_INVULLING.get(sleutel, "")


FOUTEN: dict[str, FoutMelding] = {
    # --- Het AI-model ---
    "LLM_TIMEOUT": FoutMelding(
        code="LLM_TIMEOUT",
        bericht="Het opstellen van het antwoord duurde langer dan {seconden}.",
        actie="Probeer het opnieuw, of stel uw vraag korter en concreter.",
        http_status=504,
    ),
    "LLM_GEEN_SLEUTEL": FoutMelding(
        code="LLM_GEEN_SLEUTEL",
        bericht="De assistent heeft nog geen toegangssleutel voor {backend_label}.",
        actie=(
            "Vul de sleutel voor {backend_label} in bij Instellingen en verstuur "
            "uw vraag opnieuw."
        ),
        herstelbaar=False,
        http_status=503,
    ),
    "LLM_NIET_INGESTELD": FoutMelding(
        code="LLM_NIET_INGESTELD",
        # Zelfde oorzaak als LLM_GEEN_SLEUTEL, ander advies: staat
        # ALLOW_API_KEY_OVERRIDE uit, dan negeert de host een ingevulde sleutel
        # en blijft de gebruiker anders eindeloos hetzelfde proberen.
        bericht="De assistent is in deze omgeving niet volledig ingesteld.",
        actie=(
            "Hier kunt u zelf niets aan doen. Meld dit bij de beheerder van "
            "deze omgeving."
        ),
        herstelbaar=False,
        http_status=503,
    ),
    "LLM_SLEUTEL_ONGELDIG": FoutMelding(
        code="LLM_SLEUTEL_ONGELDIG",
        bericht="De toegangssleutel voor {backend_label} wordt niet geaccepteerd.",
        actie=(
            "Controleer de sleutel voor {backend_label} bij Instellingen en "
            "verstuur uw vraag daarna opnieuw."
        ),
        herstelbaar=False,
        http_status=401,
    ),
    "LLM_TE_DRUK": FoutMelding(
        code="LLM_TE_DRUK",
        bericht="Het AI-model verwerkt op dit moment te veel verzoeken.",
        actie="Probeer het over een minuut opnieuw.",
        http_status=429,
    ),
    "LLM_OVERBELAST": FoutMelding(
        code="LLM_OVERBELAST",
        bericht="Het AI-model is tijdelijk niet beschikbaar.",
        actie="Probeer het over een minuut opnieuw.",
        http_status=503,
    ),
    "LLM_ONBEREIKBAAR": FoutMelding(
        code="LLM_ONBEREIKBAAR",
        # Dit gaat over de verbinding van de assistent naar het AI-model, niet
        # over die van de gebruiker: lag díé eruit, dan had hij deze melding
        # nooit ontvangen. "Controleer uw netwerkverbinding" is hier dus een
        # gegarandeerd zinloze opdracht.
        bericht="De assistent kan het AI-model op dit moment niet bereiken.",
        actie=(
            "Probeer het over een minuut opnieuw. Blijft het misgaan, meld het "
            "dan bij de beheerder van deze omgeving."
        ),
        http_status=503,
    ),
    "LLM_GESPREK_TE_LANG": FoutMelding(
        code="LLM_GESPREK_TE_LANG",
        bericht="Dit gesprek is te lang geworden om in één keer te verwerken.",
        actie=(
            "Begin een nieuw gesprek met de knop 'gesprek wissen', "
            "en stel uw vraag daarna opnieuw."
        ),
        herstelbaar=False,
        http_status=400,
    ),
    "LLM_BUDGET_OP": FoutMelding(
        code="LLM_BUDGET_OP",
        bericht="Het tegoed voor de AI-assistent is op.",
        actie=(
            "Meld dit bij uw begeleider. Uw vraag was in orde; "
            "opnieuw proberen helpt pas als het tegoed is aangevuld."
        ),
        http_status=400,
    ),
    "LLM_VERZOEK_ONGELDIG": FoutMelding(
        code="LLM_VERZOEK_ONGELDIG",
        bericht="Het AI-model kon dit verzoek niet verwerken.",
        actie=(
            "Formuleer uw vraag anders, of begin een nieuw gesprek "
            "met de knop 'gesprek wissen'."
        ),
        http_status=400,
    ),
    "LLM_MODEL_ONBEKEND": FoutMelding(
        code="LLM_MODEL_ONBEKEND",
        bericht="Het ingestelde model voor {backend_label} bestaat niet (meer).",
        actie=(
            "Dit is een instelling van de beheerder. "
            "Meld het bij de beheerder van deze omgeving."
        ),
        herstelbaar=False,
        http_status=503,
    ),
    "LLM_MAX_STAPPEN": FoutMelding(
        code="LLM_MAX_STAPPEN",
        bericht="Uw vraag vroeg meer stappen dan de assistent in één keer kan zetten.",
        actie=(
            "Splits uw vraag op. Bijvoorbeeld eerst 'geldt de energiebesparingsplicht "
            "voor mij?' en daarna 'welke maatregelen gelden er dan?'."
        ),
        http_status=504,
    ),
    "LLM_TOOLCALL_ONGELDIG": FoutMelding(
        code="LLM_TOOLCALL_ONGELDIG",
        # De MCP-SDK valideert de argumenten tegen het tool-schema en meldt een
        # schending terug. Dat is een fout van het model, geen storing: het kan
        # de aanroep corrigeren. Behandelen als bronstoring zou het model de
        # gebruiker een niet-bestaande storing laten melden, én het beroven van
        # de informatie waarmee het zichzelf kan herstellen.
        bericht="De assistent stelde een vraag aan een bron in de verkeerde vorm.",
        actie="Probeer het opnieuw, het liefst met een iets concretere vraag.",
        zichtbaar=False,
        llm_instructie=(
            "Dit is een fout in UW eigen tool-aanroep, geen storing bij de bron. "
            "Meld dit NIET aan de gebruiker. Lees `validatiefout`, corrigeer de "
            "argumenten en roep de tool opnieuw aan."
        ),
        http_status=400,
    ),
    "LLM_TOOLCALL_ONLEESBAAR": FoutMelding(
        code="LLM_TOOLCALL_ONLEESBAAR",
        # Zelfde soort fout als LLM_TOOLCALL_ONGELDIG: het model bouwde de
        # aanroep verkeerd op en corrigeert dat zelf in de volgende ronde. Een
        # storing melden die er niet is, in termen waar een ondernemer niets mee
        # kan, maakt een gesprek dat verder gewoon slaagt onnodig verwarrend.
        bericht="Het AI-model gaf een onleesbare opdracht aan een bron.",
        actie="Probeer het opnieuw, en formuleer uw vraag eventueel iets anders.",
        zichtbaar=False,
        llm_instructie=(
            "Dit is een fout in UW eigen tool-aanroep. Meld dit NIET aan de "
            "gebruiker. Bouw de argumenten opnieuw op als geldige JSON en roep "
            "de tool nog een keer aan."
        ),
    ),
    "LLM_ANTWOORD_AFGEKAPT": FoutMelding(
        code="LLM_ANTWOORD_AFGEKAPT",
        # Het model liep tegen zijn max_tokens aan. Zonder melding stopt het
        # antwoord midden in een zin en toont de UI het als geslaagd.
        bericht="Het antwoord was te lang en is halverwege afgebroken.",
        actie="Stel uw vraag in delen, of vraag om een kortere samenvatting.",
    ),
    "LLM_LEEG_ANTWOORD": FoutMelding(
        code="LLM_LEEG_ANTWOORD",
        # Een lege antwoordbel is voor de gebruiker niet te onderscheiden van
        # een vastgelopen assistent; een content-filter of een afgekapte
        # generatie levert precies dat op.
        bericht="Het AI-model gaf geen antwoord terug.",
        actie="Probeer het opnieuw, het liefst met een iets andere formulering.",
    ),
    "LLM_ONBEKEND": FoutMelding(
        code="LLM_ONBEKEND",
        bericht="Het AI-model gaf een onverwachte reactie.",
        actie="Probeer het opnieuw. Blijft het misgaan, meld het bij de beheerder.",
    ),
    "ANTWOORD_ONVOLLEDIG": FoutMelding(
        code="ANTWOORD_ONVOLLEDIG",
        bericht="De assistent kon een gegeven niet ophalen bij de bron.",
        actie="Stel uw vraag opnieuw. Blijft het misgaan, meld dit dan bij de "
        "beheerder van deze omgeving.",
        http_status=502,
    ),
    "HOST_FOUT": FoutMelding(
        code="HOST_FOUT",
        # Apart van LLM_ONBEKEND: een fout in de assistent zelf toeschrijven aan
        # het AI-model zet iedereen die het onderzoekt op een dwaalspoor.
        bericht="De assistent kon uw vraag niet afronden.",
        actie=(
            "Probeer het opnieuw. Blijft het misgaan, meld het dan bij de "
            "beheerder van deze omgeving."
        ),
        http_status=500,
    ),
    # --- Toestemming (PDR-008) ---
    "TOESTEMMING_VEREIST": FoutMelding(
        code="TOESTEMMING_VEREIST",
        # De harde poort in `vlam_host._bron_aanroep_gated`: zonder vastgelegde
        # toestemming (het `toestemming`-veld op het chat-contract, gevuld door
        # de "Delen"-knop) komt `netbeheerder__verbruik` hier niet voorbij, wie
        # de aanroep ook initieerde.
        bericht="Voor {bron_label} is eerst akkoord van de ondernemer nodig.",
        actie=(
            "Vraag de ondernemer om toestemming te geven, bijvoorbeeld via de "
            "'Delen'-knop, en verstuur uw vraag daarna opnieuw."
        ),
        bron="netbeheerder",
        http_status=403,
    ),
    # --- De bronnen ---
    "SOURCE_UNAVAILABLE": FoutMelding(
        code="SOURCE_UNAVAILABLE",
        bericht="{bron_label} is op dit moment niet bereikbaar.",
        actie="Probeer het over een minuut opnieuw, of kijk rechtstreeks op {alternatief}.",
        http_status=503,
    ),
    "API_FOUT": FoutMelding(
        code="API_FOUT",
        bericht="{bron_label} gaf een fout terug op de aanvraag.",
        actie="Probeer het over een minuut opnieuw, of kijk rechtstreeks op {alternatief}.",
        http_status=502,
    ),
    "BRON_NIET_GESTART": FoutMelding(
        code="BRON_NIET_GESTART",
        bericht="{bron_label} is op dit moment niet beschikbaar, en komt niet vanzelf terug.",
        # Bewust geen belofte dat de andere bronnen het wél doen: dat weet deze
        # melding niet. Het bronnen-statusblok in de systeemprompt vertelt het
        # model welke bronnen er nog zijn; dat mag het invullen.
        actie=(
            "Wachten helpt hier niet. Meld dit bij de beheerder van deze omgeving, "
            "of stel een vraag waarvoor deze gegevens niet nodig zijn."
        ),
        herstelbaar=False,
        http_status=503,
    ),
    "BRON_NIET_BESCHIKBAAR": FoutMelding(
        code="BRON_NIET_BESCHIKBAAR",
        bericht="{bron_label} kon de gevraagde gegevens niet leveren.",
        actie="Probeer het over een minuut opnieuw, of kijk rechtstreeks op {alternatief}.",
        http_status=503,
    ),
    "NIET_GEVONDEN": FoutMelding(
        code="NIET_GEVONDEN",
        bericht="In {bron_label} is niets gevonden voor {zoekterm}.",
        actie="Probeer een ander of algemener trefwoord.",
        herstelbaar=False,
        http_status=404,
    ),
    "IDENTIFICATIE_NIET_GEVONDEN": FoutMelding(
        code="IDENTIFICATIE_NIET_GEVONDEN",
        # Apart van NIET_GEVONDEN: bij een nummer heeft "probeer een algemener
        # trefwoord" geen betekenis, want een nummer kent geen algemenere variant.
        bericht="In {bron_label} bestaat {zoekterm} niet.",
        actie="Controleer het nummer, of zoek de regeling eerst op naam.",
        herstelbaar=False,
        http_status=404,
    ),
    "INPUT_INVALID": FoutMelding(
        code="INPUT_INVALID",
        bericht="De zoekopdracht voor {bron_label} was niet compleet.",
        actie="Noem een trefwoord waarop gezocht kan worden, bijvoorbeeld 'energiebesparing'.",
        herstelbaar=False,
        http_status=400,
    ),
    "ONTBREKEND_VELD": FoutMelding(
        code="ONTBREKEND_VELD",
        bericht="Er ontbreekt een gegeven om deze stap bij {bron_label} te kunnen doen: {veld}.",
        actie="Geef dit gegeven door, dan gaat de assistent verder.",
        herstelbaar=False,
        http_status=400,
    ),
    "ONTBREKENDE_VELDEN": FoutMelding(
        code="ONTBREKENDE_VELDEN",
        bericht="Er ontbreken gegevens om deze stap bij {bron_label} te kunnen doen: {veld}.",
        actie="Geef deze gegevens door, dan gaat de assistent verder.",
        herstelbaar=False,
        http_status=400,
    ),
    "ONTBREKEND_INTERN_VELD": FoutMelding(
        code="ONTBREKEND_INTERN_VELD",
        bericht=(
            "Deze stap bij {bron_label} lukte niet doordat een gegeven "
            "ontbrak dat de assistent zelf aanlevert."
        ),
        actie=(
            "Hier kunt u zelf niets aan doen. Probeer het opnieuw; blijft het "
            "misgaan, meld het dan bij de beheerder van deze omgeving."
        ),
        http_status=502,
    ),
    "EXECUTION_ERROR": FoutMelding(
        code="EXECUTION_ERROR",
        bericht="De regeltoets kon niet worden uitgevoerd op de aangeleverde gegevens.",
        actie=(
            "Probeer het opnieuw. Blijft het misgaan, kijk dan op rvo.nl "
            "of neem contact op met RVO."
        ),
        bron="regelrecht",
        http_status=502,
    ),
    "WET_NIET_TOEGESTAAN": FoutMelding(
        code="WET_NIET_TOEGESTAAN",
        bericht="Deze regeling kan de assistent niet toetsen.",
        actie=(
            "De assistent toetst op dit moment alleen de energiebesparings- "
            "en informatieplicht. Kijk voor andere regelingen op rvo.nl."
        ),
        bron="regelrecht",
        herstelbaar=False,
        http_status=404,
    ),
    "CLI_FOUT": FoutMelding(
        code="CLI_FOUT",
        bericht="{bron_label} kon niet worden geraadpleegd.",
        actie="Probeer het over een minuut opnieuw, of kijk rechtstreeks op {alternatief}.",
        http_status=502,
    ),
    "ONBEKENDE_TOOL": FoutMelding(
        code="ONBEKENDE_TOOL",
        bericht="De assistent probeerde een bron te raadplegen die hier niet beschikbaar is.",
        actie=(
            "Stel uw vraag opnieuw, het liefst iets concreter. Blijft het misgaan, "
            "meld het dan bij de beheerder van deze omgeving."
        ),
        # Opnieuw proberen is hier wél het advies (het model koos een tool die
        # niet bestaat), dus de retry-knop mag blijven staan.
        http_status=501,
    ),
    "NIET_TOEGESTAAN": FoutMelding(
        code="NIET_TOEGESTAAN",
        bericht="U kunt via de assistent alleen gegevens van uw eigen bedrijf inzien.",
        actie="Stel uw vraag over uw eigen bedrijf, dan zoekt de assistent het op.",
        herstelbaar=False,
        http_status=403,
    ),
    "MISSING_DEPENDENCY": FoutMelding(
        code="MISSING_DEPENDENCY",
        bericht="{bron_label} kan hier niet worden geraadpleegd: de assistent is niet compleet geïnstalleerd.",
        actie=(
            "Hier kunt u zelf niets aan doen. Meld dit bij de beheerder van "
            "deze omgeving."
        ),
        herstelbaar=False,
        http_status=503,
    ),
    "INVALID_INPUT": FoutMelding(
        code="INVALID_INPUT",
        bericht="De opdracht aan {bron_label} had niet de juiste vorm.",
        actie="Stel uw vraag opnieuw in andere woorden, of noem een concreter trefwoord.",
        herstelbaar=False,
        http_status=400,
    ),
    "PARSE_FOUT": FoutMelding(
        code="PARSE_FOUT",
        bericht="{bron_label} gaf een antwoord dat de assistent niet kon lezen.",
        actie="Probeer het over een minuut opnieuw, of kijk rechtstreeks op {alternatief}.",
        http_status=502,
    ),
    "TOOL_NIET_IN_TRANSPORT": FoutMelding(
        code="TOOL_NIET_IN_TRANSPORT",
        # Het CLI-transport loopt bewust achter op MCP (PDR-005/PDR-008). Opnieuw
        # vragen kan hier per definitie niet slagen, dus dat mag de melding ook
        # niet suggereren.
        bericht="Deze mogelijkheid is in deze versie van de assistent niet beschikbaar.",
        actie=(
            "Hier kunt u zelf niets aan doen. Meld dit bij de beheerder van deze "
            "omgeving. Andere vragen kunt u gewoon blijven stellen."
        ),
        herstelbaar=False,
        http_status=501,
    ),
    "TOOL_ONVERWACHT": FoutMelding(
        code="TOOL_ONVERWACHT",
        bericht="{bron_label} gaf een onverwachte fout.",
        actie=(
            "Probeer het opnieuw, of kijk rechtstreeks op {alternatief}. "
            "Blijft het misgaan, meld het dan bij de beheerder."
        ),
    ),
    # --- De vraag van de gebruiker ---
    "BRON_GEEN_SESSIE": FoutMelding(
        code="BRON_GEEN_SESSIE",
        bericht="{bron_label} kreeg niet door om welk bedrijf het gaat en kon niets opzoeken.",
        # Bewust géén "log opnieuw in": deze melding komt van een bron, en een
        # bron die de assistent een inlog-instructie kan laten uitspreken is een
        # phishing-vector. Wie er echt uit ligt, hoort de host te bepalen.
        actie=(
            "Probeer het opnieuw. Blijft het misgaan, meld het dan bij de "
            "beheerder van deze omgeving."
        ),
        http_status=502,
    ),
    "GEEN_SESSIE": FoutMelding(
        code="GEEN_SESSIE",
        bericht=(
            "U bent niet ingelogd, dus de assistent kan uw bedrijfsgegevens niet gebruiken."
        ),
        actie=(
            "Log eerst in. Zolang u niet bent ingelogd, raadpleegt de assistent "
            "geen overheidsbronnen."
        ),
        herstelbaar=False,
        http_status=401,
    ),
    "AANVRAAG_ONGELDIG": FoutMelding(
        code="AANVRAAG_ONGELDIG",
        # Het verzoek voldeed niet aan het API-model (een veld ontbreekt of heeft
        # het verkeerde type). Dat is een fout in de aanroepende software, niet
        # iets wat de gebruiker verkeerd deed, dus geen "stel uw vraag anders".
        bericht="Het verzoek aan de assistent was niet compleet.",
        actie=(
            "Ververs de pagina en verstuur uw vraag opnieuw. Blijft het misgaan, "
            "meld het dan bij de beheerder van deze omgeving."
        ),
        herstelbaar=False,
        http_status=422,
    ),
    "SESSIE_NIET_INGESTELD": FoutMelding(
        code="SESSIE_NIET_INGESTELD",
        # Lege allowlist: niemand komt erdoor, ook niet na opnieuw inloggen.
        # "Log eerst in" zou hier een doodlopend advies zijn.
        bericht="De assistent kent in deze omgeving nog geen gebruikers.",
        actie=(
            "Hier kunt u zelf niets aan doen. Meld dit bij de beheerder van "
            "deze omgeving."
        ),
        herstelbaar=False,
        http_status=503,
    ),
    "LEGE_VRAAG": FoutMelding(
        code="LEGE_VRAAG",
        bericht="Er is geen vraag meegestuurd.",
        actie=(
            "Typ uw vraag in het tekstvak en verstuur die opnieuw. Bijvoorbeeld: "
            "'Geldt de energiebesparingsplicht voor mijn bedrijf?'"
        ),
        herstelbaar=False,
        http_status=400,
    ),
    "VRAAG_TE_LANG": FoutMelding(
        code="VRAAG_TE_LANG",
        bericht="Uw vraag is langer dan {maximum}.",
        actie="Kort uw vraag in, of splits die op in meerdere vragen.",
        herstelbaar=False,
        http_status=413,
    ),
}


def maak_fout(code: str, **invulling) -> FoutMelding:
    """Bouw een `FoutMelding` uit de catalogus, met de placeholders ingevuld.

    Een onbekende code levert `LLM_ONBEKEND` op in plaats van een KeyError: een
    fout in de foutafhandeling mag het gesprek niet alsnog laten klappen.
    """
    sjabloon = FOUTEN.get(code)
    if sjabloon is None:
        # %r en afgekapt: de code kan van een bron komen en dus regeleindes
        # bevatten, waarmee een valse logregel te schrijven zou zijn.
        logger.warning("Onbekende foutcode opgevraagd: %r", str(code)[:80])
        sjabloon = FOUTEN["LLM_ONBEKEND"]

    backend = invulling.pop("backend", None)
    if backend:
        invulling.setdefault("backend_label", BACKEND_LABELS.get(backend, backend))
    bron = invulling.pop("bron", None) or sjabloon.bron
    # Lege waarden weglaten, zodat de neutrale formulering uit
    # _STANDAARD_INVULLING inspringt in plaats van een gat in de zin.
    velden = _Invulling({k: v for k, v in invulling.items() if v not in (None, "")})
    if bron:
        velden.setdefault("bron_label", BRON_LABELS.get(bron, "de bron"))
        velden.setdefault(
            "alternatief",
            BRON_ALTERNATIEF.get(bron, _STANDAARD_INVULLING["alternatief"]),
        )
    return replace(
        sjabloon,
        bericht=_hoofdletter(sjabloon.bericht.format_map(velden)),
        actie=_hoofdletter(sjabloon.actie.format_map(velden)),
        bron=bron,
    )


def _hoofdletter(zin: str) -> str:
    """Begin de zin met een hoofdletter zonder de rest te raken.

    Nodig omdat een zin met een bron-label kan beginnen ("de regelgeving-
    database ..."); `str.capitalize()` zou de rest verkleinen (KvK -> kvk).
    """
    return zin[:1].upper() + zin[1:]


# --- Classificatie van LLM-fouten -------------------------------------------

# Volgorde telt: `APITimeoutError` erft van `APIConnectionError`, dus de
# specifieke variant moet eerst gecontroleerd worden. Beide SDK's gebruiken
# dezelfde klassenamen in hun eigen namespace.
_LLM_REGELS: tuple[tuple[tuple[type, ...], str], ...] = (
    ((anthropic.APITimeoutError, openai.APITimeoutError, TimeoutError), "LLM_TIMEOUT"),
    (
        (
            anthropic.AuthenticationError,
            openai.AuthenticationError,
            anthropic.PermissionDeniedError,
            openai.PermissionDeniedError,
        ),
        "LLM_SLEUTEL_ONGELDIG",
    ),
    ((anthropic.RateLimitError, openai.RateLimitError), "LLM_TE_DRUK"),
    ((anthropic.NotFoundError, openai.NotFoundError), "LLM_MODEL_ONBEKEND"),
    (
        (anthropic.InternalServerError, openai.InternalServerError),
        "LLM_OVERBELAST",
    ),
    (
        (anthropic.APIConnectionError, openai.APIConnectionError),
        "LLM_ONBEREIKBAAR",
    ),
)

# Signalen in een 400-melding die zeggen dat het tegoed of de limiet op is.
# Beide aanbieders sturen dit als een gewone BadRequestError, dus op type is het
# niet te onderscheiden van een verzoek dat echt niet klopt - dezelfde reden
# waarom "context te lang" hieronder ook op tekst wordt herkend. Zonder deze tak
# krijgt de respondent te horen dat hij zijn vraag anders moet formuleren,
# terwijl er niets mis is met zijn vraag.
_BUDGET_SIGNALEN = (
    "credit balance",
    "insufficient_quota",
    "exceeded your current quota",
    "billing details",
    "plans & billing",
)

# Signalen in een 400-melding die op een te lange context wijzen. Het type is
# hier hetzelfde (BadRequestError), alleen de tekst verschilt per aanbieder.
_CONTEXT_SIGNALEN = (
    "prompt is too long",
    "context length",
    "context window",
    "maximum context",
    "input tokens",
    "te lang",
)


def classificeer_llm_fout(
    exc: BaseException, backend: str = "", timeout: int | None = None
) -> FoutMelding:
    """Vertaal een exception uit de Anthropic/OpenAI-SDK naar een melding.

    Mapt op exceptie-type, niet op tekst: de tekst van een SDK verandert, het
    type niet. `backend` en `timeout` dienen alleen om de melding concreet te
    maken (hoeveel seconden er is gewacht).
    """
    seconden = ""
    if timeout:
        seconden = f"{timeout} seconde" if timeout == 1 else f"{timeout} seconden"
    for typen, code in _LLM_REGELS:
        if isinstance(exc, typen):
            return maak_fout(code, seconden=seconden, backend=backend)

    if isinstance(exc, anthropic.BadRequestError | openai.BadRequestError):
        tekst = str(exc).lower()
        if any(signaal in tekst for signaal in _CONTEXT_SIGNALEN):
            return maak_fout("LLM_GESPREK_TE_LANG")
        if any(signaal in tekst for signaal in _BUDGET_SIGNALEN):
            return maak_fout("LLM_BUDGET_OP")
        return maak_fout("LLM_VERZOEK_ONGELDIG")

    # Overige APIStatusError: val terug op de statuscode.
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        if status >= 500:
            return maak_fout("LLM_OVERBELAST")
        if status in (401, 403):
            return maak_fout("LLM_SLEUTEL_ONGELDIG", backend=backend)
        if status == 429:
            return maak_fout("LLM_TE_DRUK")

    logger.warning("Onverwacht type LLM-fout (%s)", type(exc).__name__)
    return maak_fout("LLM_ONBEKEND")


# --- Classificatie van bronfouten -------------------------------------------


# Foutcodes die een bron mag laten zien. De catalogus bevat ook meldingen over
# de host zelf (sleutel ontbreekt, log eerst in); zonder deze grens zou een bron
# die `{"error": "LLM_SLEUTEL_ONGELDIG"}` stuurt de assistent de gebruiker om
# zijn API-sleutel laten vragen. De bron bepaalt wát er misging, niet wie er
# schuldig is.
_BRON_CODES = frozenset(
    {
        "SOURCE_UNAVAILABLE",
        "API_FOUT",
        "BRON_NIET_GESTART",
        "BRON_NIET_BESCHIKBAAR",
        "BRON_GEEN_SESSIE",
        "NIET_GEVONDEN",
        "INPUT_INVALID",
        "ONTBREKEND_VELD",
        "ONTBREKENDE_VELDEN",
        "ONTBREKEND_INTERN_VELD",
        "EXECUTION_ERROR",
        "WET_NIET_TOEGESTAAN",
        "CLI_FOUT",
        "ONBEKENDE_TOOL",
        "TOOL_ONVERWACHT",
        "TOOL_NIET_IN_TRANSPORT",
        # Schemavalidatie door de MCP-SDK: een fout van het model, hersteld door
        # het model. Staat hier omdat `mcp_client` 'm langs dit pad meegeeft.
        "LLM_TOOLCALL_ONGELDIG",
        # Codes van de bash-CLI-wrappers (services/cli/)
        "NIET_TOEGESTAAN",
        "MISSING_DEPENDENCY",
        "INVALID_INPUT",
        "PARSE_FOUT",
    }
)

# Een bron die meldt dat hij geen identiteit meekreeg zegt iets over de aanroep,
# niet over de inlog van de gebruiker; die twee mogen niet dezelfde zin krijgen.
_BRON_HERSCHRIJVING = {"GEEN_SESSIE": "BRON_GEEN_SESSIE"}

# Bovengrens op de bron-output die we parsen. Ver boven elk echt antwoord, maar
# het voorkomt dat een absurd geneste of gigantische payload de event-loop
# bezighoudt in `json.loads`.
_MAX_PAYLOAD_TEKENS = 2_000_000


# Gegevens die de host of het model zelf aanlevert. Ontbreken die, dan kan de
# ondernemer er niets aan doen en is "geef dit gegeven door" een zinloze
# opdracht; dat is dan een fout in de assistent, geen ontbrekend antwoord.
_INTERNE_VELDEN = frozenset({"kvk_nummer", "kvknummer", "law", "service", "bsn", "rsin"})

# Velden die noch de host noch de gebruiker aanlevert: het model haalt ze uit een
# eerdere tool-aanroep. `regeling_id` komt uit `rvo__zoek_regeling`. Ze stonden
# eerder bij _INTERNE_VELDEN, maar dat leidde tot een doodloper: ontbrak naast
# `regeling_id` ook een gegeven dat de gebruiker wel kan geven, dan kreeg hij
# "hier kunt u zelf niets aan doen, meld het bij de beheerder" in plaats van de
# vraag naar dat gegeven. Voor een ontbrekend modelveld hoeft de gebruiker niets
# te weten - het model zoekt de regeling alsnog op.
_MODEL_VELDEN = frozenset({"regeling_id"})

# Parameternamen zoals de bronnen ze kennen, in woorden waar een ondernemer iets
# aan heeft. Zonder deze vertaling leest de melding als "Er ontbreekt een gegeven
# ...: trefwoord" en weet de gebruiker nog steeds niet wat hij moet aanleveren.
_VELD_IN_MENSENTAAL = {
    "trefwoord": "een zoekwoord",
    "maatregelen": "welke energiebesparende maatregelen u hebt genomen",
    "bwb_id": "om welke regeling het gaat",
    "jaarlijks_elektriciteitsverbruik_kwh": "uw jaarlijks elektriciteitsverbruik in kWh",
    "jaarlijks_gasverbruik_m3": "uw jaarlijks gasverbruik in m³",
    "is_woonfunctie": "of het pand een woonfunctie heeft",
}


def _veldsleutel(veld: object) -> str:
    """De ruwe parameternaam van een ontbrekend-veld-item."""
    if isinstance(veld, dict):
        return str(veld.get("naam") or veld.get("name") or "").strip().lower()
    return str(veld).strip().lower()


def _alleen_modelvelden(payload: dict) -> bool:
    """Noemde de bron uitsluitend velden die het model zelf aanlevert?

    Onderscheidt "de bron zei welk veld ontbrak en dat is een zaak van het
    model" van "de bron zei niet welk veld ontbrak". In het tweede geval hoort
    de gebruiker de neutrale melding te krijgen.
    """
    velden = payload.get("ontbrekende_gegevens") or payload.get("velden")
    if not isinstance(velden, list) or not velden:
        return False
    return all(_veldsleutel(veld) in _MODEL_VELDEN for veld in velden[:5])


def _veldnamen(payload: dict) -> tuple[list[str], bool]:
    """De ontbrekende gegevens in woorden die een ondernemer herkent.

    Geeft `(namen, blokkeert_op_intern)` terug. Velden die de host of het model zelf
    aanlevert (het KvK-nummer uit de sessie, de gekozen wet, het regeling-ID)
    worden eruit gefilterd: daar kan de ondernemer niets mee, en ze om zo'n
    gegeven vragen is een opdracht die hij niet kán uitvoeren.

    De bronnen zijn onderling niet eenduidig: sommige sturen een lijst namen,
    andere een lijst dicts (`{"naam": "JAARLIJKS_GASVERBRUIK_M3", "beschrijving":
    "Jaarlijks gasverbruik"}`). De beschrijving wint, want een engine-constante
    in kapitalen is geen zin voor een ondernemer. Bewust NIET terugvallen op het
    `message`-veld van de bron: dat is technische tekst en die hoort in de log.
    """
    velden = payload.get("ontbrekende_gegevens") or payload.get("velden")
    if not isinstance(velden, list):
        return [], False

    namen: list[str] = []
    intern = 0
    for veld in velden[:5]:
        sleutel = _veldsleutel(veld)
        if sleutel in _INTERNE_VELDEN:
            intern += 1
            continue
        if sleutel in _MODEL_VELDEN:
            # Niet meetellen als blokkade: het model kan dit zelf ophalen.
            continue
        if sleutel in _VELD_IN_MENSENTAAL:
            namen.append(_VELD_IN_MENSENTAAL[sleutel])
            continue
        ruw = veld.get("beschrijving") or sleutel if isinstance(veld, dict) else veld
        schoon = schoon_echo(str(ruw).rstrip(". "), maximum=40)
        if schoon:
            namen.append(schoon)
    # Ontbreekt er óók een gegeven dat de assistent zelf aanlevert, dan helpt het
    # niet of de gebruiker de rest aanlevert: de aanroep faalt opnieuw op dat
    # interne veld. Dan liever eerlijk zeggen dat hij er niets aan kan doen dan
    # hem laten aanleveren wat hij misschien net al gaf.
    return namen, bool(intern)


# Excepties die op een fout in ónze code wijzen, niet op een bron die uitvalt.
# Alleen deze krijgen "onverwachte fout"; al het overige komt van het transport
# (een dichtgevallen stdio-pipe, een SDK-fout, een subprocess dat wegvalt) en
# hoort de bron-naam plus het alternatief te noemen. Bewust deze kant op: een
# nieuwe exceptiesoort uit de MCP-SDK levert dan de bruikbare melding op in
# plaats van de vage.
_PROGRAMMEERFOUTEN = (TypeError, AttributeError, KeyError, IndexError, NameError)


def _transportfout(exc: BaseException) -> str:
    """Kies de foutcode voor een exception uit een bron-aanroep."""
    # FileNotFoundError en PermissionError eerst: die erven van OSError maar
    # betekenen hier iets anders (de bron kán niet starten, opnieuw proberen
    # helpt niet) dan een verbinding die wegvalt.
    if isinstance(exc, FileNotFoundError | PermissionError):
        return "BRON_NIET_GESTART"
    if isinstance(exc, _PROGRAMMEERFOUTEN):
        return "TOOL_ONVERWACHT"
    return "SOURCE_UNAVAILABLE"


# Een identificatie (BWB-ID, KvK-nummer) is geen zoekterm: "probeer een
# algemener trefwoord" is daar zinloos advies.
_IDENTIFICATIE_RE = re.compile(r"^(BWB[RVB]\d+|\d{6,})$", re.IGNORECASE)


def _is_identificatie(zoekterm: str) -> bool:
    """Is dit een nummer/ID in plaats van een zoekwoord?"""
    return bool(_IDENTIFICATIE_RE.match((zoekterm or "").strip()))


def _is_leeg_zoekresultaat(resultaat: object) -> bool:
    """Een geslaagde zoekopdracht die niets opleverde.

    De bronnen melden dat met `aantal: 0` en een lege resultatenlijst, niet met
    een foutcode; zonder deze check komt de al geschreven "niets gevonden"-zin
    nooit in beeld en improviseert het model.
    """
    if not isinstance(resultaat, str) or not resultaat.strip().startswith("{"):
        return False
    if len(resultaat) > _MAX_PAYLOAD_TEKENS:
        return False
    try:
        payload = json.loads(resultaat)
    except Exception:  # noqa: BLE001
        return False
    if not isinstance(payload, dict):
        return False
    kern = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    resultaten = kern.get("resultaten")
    return isinstance(resultaten, list) and not resultaten and kern.get("aantal") == 0


def _foutpayload(resultaat: object) -> dict | None:
    """Haal de foutdict uit een tool-resultaat, of `None` als er geen fout is.

    Twee vormen: kaal (`{"error": ...}`) en verpakt in de provenance-envelope van
    de MCP-standaard (`{"data": {"error": ...}, "provenance": {...}}`). RegelRecht
    gebruikt de tweede voor álles, ook voor zijn fouten; zonder deze uitpakstap
    glipt precies die bron langs de catalogus heen.
    """
    if not isinstance(resultaat, str):
        return None
    tekst = resultaat.strip()
    if not tekst.startswith("{") or len(tekst) > _MAX_PAYLOAD_TEKENS:
        return None
    try:
        payload = json.loads(tekst)
    except Exception:  # noqa: BLE001 — ook RecursionError bij absurd geneste JSON
        return None
    if not isinstance(payload, dict):
        return None
    if "error" not in payload and isinstance(payload.get("data"), dict):
        payload = payload["data"]
    return payload if isinstance(payload.get("error"), str) and payload["error"] else None


def classificeer_tool_fout(
    tool_key: str, resultaat: object, zoekterm: str = ""
) -> FoutMelding | None:
    """Vertaal een tool-resultaat of -exception naar een melding.

    Geeft `None` terug als er niets aan de hand is, zodat de aanroeper dit als
    enkele check kan gebruiken op zowel geslaagde als mislukte aanroepen.
    """
    bron = bron_uit_tool(tool_key)
    schone_zoekterm = schoon_echo(zoekterm) if zoekterm else ""
    invulling = {
        "bron": bron,
        "zoekterm": f"'{schone_zoekterm}'" if schone_zoekterm else "",
    }

    if isinstance(resultaat, BaseException):
        return maak_fout(_transportfout(resultaat), **invulling)

    if _is_leeg_zoekresultaat(resultaat):
        # Een zoekopdracht zonder treffers is geen fout in de bron, maar voor de
        # gebruiker wél een doodloper: zonder melding improviseert het model.
        # Bij een gebruikerstest is dit het meest waarschijnlijke vastlopen.
        code = (
            "IDENTIFICATIE_NIET_GEVONDEN"
            if _is_identificatie(schone_zoekterm)
            else "NIET_GEVONDEN"
        )
        return maak_fout(code, **invulling)

    payload = _foutpayload(resultaat)
    if payload is None:
        return None

    ruwe_code = str(payload["error"]).strip().upper()
    code = _BRON_HERSCHRIJVING.get(ruwe_code, ruwe_code)
    if code not in _BRON_CODES:
        logger.warning(
            "Bron %r stuurde een code buiten de bron-set: %r",
            bron or "onbekend",
            str(payload["error"])[:80],
        )
        code = "TOOL_ONVERWACHT"

    if code == "NIET_GEVONDEN" and _is_identificatie(schone_zoekterm):
        code = "IDENTIFICATIE_NIET_GEVONDEN"
    if code in ("ONTBREKEND_VELD", "ONTBREKENDE_VELDEN"):
        namen, blokkeert_op_intern = _veldnamen(payload)
        if blokkeert_op_intern:
            code = "ONTBREKEND_INTERN_VELD"
        elif not namen and _alleen_modelvelden(payload):
            # De bron noemde alleen velden die het model zelf ophaalt. Er valt
            # de gebruiker dus niets te vragen; het model corrigeert zijn eigen
            # aanroep. Noemde de bron helemaal geen velden, dan blijft de
            # neutrale melding staan - die is bruikbaarder dan stilte.
            code = "LLM_TOOLCALL_ONGELDIG"
        else:
            code = "ONTBREKENDE_VELDEN" if len(namen) > 1 else "ONTBREKEND_VELD"
            invulling["veld"] = ", ".join(namen)
    if code == "LLM_TOOLCALL_ONGELDIG":
        # Geen bron-melding: de gebruiker hoeft niets te weten van een aanroep
        # die het model zelf corrigeert.
        return maak_fout(code)
    return maak_fout(code, **invulling)


# --- Uitgaande vormen --------------------------------------------------------


def naar_event(fout: FoutMelding, type_: str = "error") -> dict:
    """Bouw de SSE-payload.

    `message` blijft de volledige zin, zodat een frontend die alleen dat veld
    kent blijft werken; `bericht`/`actie`/`code` maken een retry-knop en een
    bron-vermelding in de UI mogelijk.
    """
    return {
        "type": type_,
        "code": fout.code,
        "message": fout.tekst,
        "bericht": fout.bericht,
        "actie": fout.actie,
        "bron": fout.bron,
        "herstelbaar": fout.herstelbaar,
    }


# Velden uit een foutantwoord die het model mag zien. Alles daarbuiten (paden,
# stack-tekst, een door de bron verzonnen `gebruikersmelding`) blijft in de log.
# `velden` staat er bewust NIET in: de melding is er al mee opgebouwd, mét het
# filter dat interne velden (kvk_nummer, regeling_id) wegneemt. Doorgeven zou het
# model alsnog om een gegeven laten vragen dat de gebruiker niet kán leveren.
# `ontbrekende_gegevens` blijft wel: de RegelRecht-flow leunt erop om de juiste
# feitelijke vragen te stellen.
_DOOR_TE_GEVEN_VELDEN = frozenset(
    {"error", "ontbrekende_gegevens", "benodigde_feiten", "validatiefout"}
)

_LLM_INSTRUCTIE = (
    "Geef de gebruikersmelding letterlijk door aan de gebruiker, in uw eigen "
    "antwoordopmaak. Verzin GEEN gegevens en gebruik GEEN eigen kennis als "
    "vervanging voor wat deze bron had moeten leveren."
)


def naar_llm(fout: FoutMelding) -> str:
    """Bouw het tool-resultaat dat het LLM krijgt.

    Bevat bewust geen exception-tekst, pad of URL: het LLM kan alles wat het
    hier ziet doorvertellen aan de gebruiker. De technische oorzaak staat in de
    log, niet in het gesprek.
    """
    payload = {"error": fout.code, "bron": fout.bron}
    # Alleen een melding meegeven als die ook echt voor de gebruiker is. De
    # systeemprompt draagt op om `gebruikersmelding` letterlijk door te geven;
    # dat veld meesturen bij een fout die het model zelf moet herstellen, zou
    # die instructie recht tegenspreken.
    if fout.zichtbaar:
        payload["gebruikersmelding"] = fout.tekst
    payload["instructie"] = fout.llm_instructie or _LLM_INSTRUCTIE
    return json.dumps(payload, ensure_ascii=False)


def verrijk_llm(resultaat: str, fout: FoutMelding) -> str:
    """Voeg de gebruikersmelding toe aan een bron-antwoord dat al een fout meldt.

    Bewust verrijken en niet vervangen: sommige foutantwoorden dragen informatie
    die het LLM nodig heeft om verder te kunnen (RegelRecht meldt bijvoorbeeld
    in `ontbrekende_gegevens` welke feiten het nog aan de gebruiker moet vragen).
    Het `message`-veld van de bron gaat er wél uit: dat is een technische tekst
    die het LLM anders kan doorvertellen.
    """
    try:
        payload = json.loads(resultaat)
    except Exception:  # noqa: BLE001 — ook RecursionError bij absurd geneste JSON
        return naar_llm(fout)
    if not isinstance(payload, dict):
        return naar_llm(fout)
    # Het technische bericht gaat eruit, op beide niveaus: de provenance-envelope
    # van de MCP-standaard zet de foutdict onder `data`.
    # Allowlist in plaats van `message` wegstrepen: een denylist van één veld
    # gaat ervan uit dat we alle andere veldnamen kennen die een bron ooit
    # meestuurt. Een bron die zijn technische tekst in `detail` zet, of zelf een
    # `gebruikersmelding` verzint, zou er anders langs komen — en die tekst gaat
    # met het gezag van de host naar het model.
    behouden = {
        sleutel: waarde
        for sleutel, waarde in payload.items()
        if sleutel in _DOOR_TE_GEVEN_VELDEN
    }
    # De genormaliseerde code, niet de rauwe waarde: die is door de bron bepaald
    # en kan een lap tekst of een eigen instructie zijn.
    behouden["error"] = fout.code
    if isinstance(payload.get("data"), dict):
        behouden["data"] = {
            sleutel: waarde
            for sleutel, waarde in payload["data"].items()
            if sleutel in _DOOR_TE_GEVEN_VELDEN
        }
        # Ook hier de genormaliseerde code: de provenance-envelope is juist de
        # vorm die RegelRecht voor álles gebruikt, dus zonder deze regel komt de
        # rauwe bronwaarde er langs de allowlist heen alsnog doorheen.
        behouden["data"]["error"] = fout.code
    # Interne velden er ook hier uit: de melding laat `kvk_nummer` bewust weg
    # omdat de gebruiker die niet kan aanleveren, en dan moet het model er via
    # deze lijst niet alsnog om kunnen vragen.
    for laag in (behouden, behouden.get("data")):
        if isinstance(laag, dict) and isinstance(laag.get("ontbrekende_gegevens"), list):
            laag["ontbrekende_gegevens"] = [
                veld
                for veld in laag["ontbrekende_gegevens"]
                if _veldsleutel(veld) not in _INTERNE_VELDEN
            ]
    if fout.zichtbaar:
        behouden["gebruikersmelding"] = fout.tekst
    behouden["instructie"] = fout.llm_instructie or _LLM_INSTRUCTIE
    return json.dumps(behouden, ensure_ascii=False)
