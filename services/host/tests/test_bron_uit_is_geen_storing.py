"""Een bron die bewust uitstaat is geen storing, en de ondernemer hoort er niets over.

Tijdens het gebruikersonderzoek stond de Business Wallet uit, zodat de
ondernemer zijn verbruik zelf opgeeft. De assistent zei daarop: "de Business
Wallet is momenteel niet beschikbaar". Voor de respondent is dat een storing in
iets waarvan hij niet wist dat het bestond, midden in een flow die verder
gewoon werkt. Een uitgezette bron hoort niet genoemd te worden: niet als
belofte, en ook niet als gemis.

Een bron die wél is ingericht maar niet opkwam, is een storing. Die blijft
gemeld worden, met het alternatief voor de gebruiker (`bronnen_status.md`).
"""


from prompts.composer import compose_system_prompt

STORING_KOP = "BESCHIKBAARHEID VAN BRONNEN"




# --- de host maakt het onderscheid -------------------------------------------


def test_een_niet_ingerichte_bron_staat_uit_en_is_geen_storing(host_met_bronnen):
    host = host_met_bronnen(uit=["netbeheerder"])
    assert host.bronnen_uit == ["netbeheerder"]
    assert host.bronnen_offline == []


def test_een_bron_die_niet_opkwam_is_een_storing_en_staat_niet_uit(host_met_bronnen):
    host = host_met_bronnen(storing=["koop"])
    assert host.bronnen_offline == ["koop"]
    assert host.bronnen_uit == []


def test_beide_tegelijk_blijven_gescheiden(host_met_bronnen):
    host = host_met_bronnen(uit=["netbeheerder"], storing=["koop"])
    assert host.bronnen_offline == ["koop"]
    assert host.bronnen_uit == ["netbeheerder"]


def test_alles_verbonden_geeft_lege_lijsten(host_met_bronnen):
    host = host_met_bronnen()
    assert host.bronnen_offline == []
    assert host.bronnen_uit == []


# --- wat het model te zien krijgt ---------------------------------------------


def test_een_uitgezette_bron_komt_niet_in_het_storingsblok():
    prompt = compose_system_prompt("claude", has_tools=True, bronnen_uit=["netbeheerder"])
    assert STORING_KOP not in prompt
    assert "Business Wallet (energiegegevens van de netbeheerder) - alternatief" not in prompt


def test_een_uitgezette_bron_krijgt_de_instructie_om_er_over_te_zwijgen():
    prompt = compose_system_prompt("claude", has_tools=True, bronnen_uit=["netbeheerder"])
    assert "NIET NOEMEN" in prompt
    assert "Business Wallet" in prompt.split("NIET NOEMEN", 1)[1][:400]


def test_zonder_uitgezette_bronnen_geen_zwijg_instructie():
    prompt = compose_system_prompt("claude", has_tools=True)
    assert "NIET NOEMEN" not in prompt


def test_een_storing_wordt_nog_steeds_gemeld():
    prompt = compose_system_prompt("claude", has_tools=True, bronnen_offline=["koop"])
    assert STORING_KOP in prompt


def test_voorbeelden_die_op_de_uitgezette_bron_leunen_verdwijnen_stil():
    """`informatieplicht_flow.md` noemt de wallet als optionele stap. Met de
    wallet uit blijft het voorbeeld, zonder de stap en zonder een 'LET OP:
    niet beschikbaar' erachter - dat is precies de zin die het model naspreekt."""
    prompt = compose_system_prompt("claude", has_tools=True, bronnen_uit=["netbeheerder"])
    assert "LET OP: in deze omgeving is" not in prompt


def test_de_host_geeft_beide_lijsten_door(host_met_bronnen):
    host = host_met_bronnen(uit=["netbeheerder"], storing=["koop"])
    prompt = host._system_prompt("claude", has_tools=True)
    assert STORING_KOP in prompt
    assert "KOOP" in prompt.split(STORING_KOP, 1)[1][:300]
    assert "NIET NOEMEN" in prompt
