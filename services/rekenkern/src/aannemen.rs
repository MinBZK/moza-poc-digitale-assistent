//! Casus "iemand aannemen met afstand tot de arbeidsmarkt": van de vier
//! antwoorden van de ondernemer naar aanroepen van de engine, en van de
//! uitkomsten naar wat een scherm toont. Overgenomen uit moza-portaal
//! (`personeel/iemand-aannemen/_uitkomsten.ts`), zodat elke afnemer dezelfde
//! vertaling gebruikt. Uitgangssituaties en uitsluitingen volgen de
//! Uitkomstenkaart Financieel CV; waar de kaart twee lezingen toelaat, de
//! zuinigste ("nooit te gunstig").
//!
//! Hier staat geen wetinhoud: welke feiten een route openen is een keuze van
//! deze casus, de regels zelf zitten in het corpus.

use serde::{Deserialize, Serialize};
use serde_json::{json, Map, Value};
use std::collections::{BTreeMap, BTreeSet};

pub const PEILDATUM: &str = "2026-07-01";
/// Wettelijk minimumloon per uur per 1 juli 2026, in eurocent.
pub const WML_UUR_EUROCENT: i64 = 1499;
/// Loonkosten-vuistregel: plus 8 procent vakantiebijslag en 20 procent werkgeverslasten.
const OPSLAG: f64 = 1.08 * 1.2;

/// De neutrale basis: elke route staat dicht tot een antwoord hem opent.
const BASISFEITEN: &str = include_str!("../casus/iemand-aannemen/basisfeiten.json");

pub const DOELGROEPEN: [(&str, &str); 7] = [
    ("register", "Iemand uit het doelgroepregister (banenafspraak)"),
    ("wajong", "Iemand met een Wajong-uitkering"),
    ("wia", "Iemand met een WIA-uitkering"),
    ("bijstand", "Iemand met een bijstandsuitkering"),
    ("wsw", "Heeft een Wsw-indicatie of werkt in de sociale werkvoorziening"),
    ("beschut", "Is door de gemeente aangewezen op beschut werk"),
    ("geen", "Geen van deze"),
];

/// De antwoorden op de vier vragen.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Keuzes {
    pub doelgroepen: Vec<String>,
    pub uren: f64,
    pub loonwaarde: f64,
    /// Bruto uurloon in eurocent.
    pub uurloon: i64,
}

pub type Feiten = Map<String, Value>;

/// Eén aanroep van de engine.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Invoer {
    pub wet: String,
    pub output: String,
    pub peildatum: String,
    pub parameters: Feiten,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub uitleggen: Vec<String>,
}

type Nodig = fn(&BTreeSet<&str>) -> bool;

pub struct Doel {
    pub wet: &'static str,
    pub output: &'static str,
    pub uitleggen: &'static [&'static str],
    /// Kan deze uitkomst bij deze keuzes iets opleveren? Zo niet, dan blijft de aanroep weg.
    pub nodig: Nodig,
}

fn via_gemeente(d: &BTreeSet<&str>) -> bool {
    d.contains("bijstand") && !d.contains("wajong") && !d.contains("wia")
}
fn iets(d: &BTreeSet<&str>) -> bool {
    !d.is_empty() && !d.contains("geen")
}

/// Wat de oriëntatie rekent, met de bedragen eerst. WW 76a heeft geen vinkje
/// en blijft dus weg.
pub const DOELEN: [Doel; 7] = [
    Doel {
        wet: "participatiewet",
        output: "heeft_recht_op_lks",
        uitleggen: &["hoogte_lks_eurocent_per_maand"],
        nodig: via_gemeente,
    },
    Doel {
        wet: "wet_arbeidsongeschiktheidsvoorziening_jonggehandicapten",
        output: "heeft_recht_op_loondispensatie",
        uitleggen: &["aanspraak_beloning_per_uur_eurocent"],
        nodig: |d| d.contains("wajong"),
    },
    Doel {
        wet: "wet_tegemoetkomingen_loondomein",
        output: "heeft_recht_op_lkv",
        uitleggen: &["hoogte_lkv_per_jaar_eurocent", "categorie_lkv"],
        nodig: iets,
    },
    Doel {
        wet: "ziektewet",
        output: "heeft_recht_op_no_risk_polis",
        uitleggen: &["duur_no_risk_polis_jaren"],
        nodig: iets,
    },
    Doel {
        wet: "participatiewet",
        output: "mag_proefplaatsing_aangaan",
        uitleggen: &[],
        nodig: via_gemeente,
    },
    Doel {
        wet: "participatiewet",
        output: "heeft_aanspraak_op_begeleiding_op_de_werkplek",
        uitleggen: &[],
        nodig: via_gemeente,
    },
    Doel {
        wet: "wet_werk_en_inkomen_naar_arbeidsvermogen",
        output: "mag_jobcoaching_toekennen",
        uitleggen: &["mag_werkplekaanpassing_toekennen"],
        nodig: |d| d.contains("wia"),
    },
];

/// Vraag 1 is meerkeuze. Wajong vinkt het register aan (Wfsv 38b lid 1 c).
/// Beschut werk sluit het register uit (aanhef 38b lid 1), dus ook Wajong.
/// "Geen van deze" sluit de andere keuzes uit.
pub fn kies_doelgroep(huidig: &[String], waarde: &str, aan: bool) -> Vec<String> {
    if aan && waarde == "geen" {
        return vec!["geen".into()];
    }
    let mut nieuw: Vec<&str> = huidig.iter().map(String::as_str).filter(|d| *d != waarde && *d != "geen").collect();
    if aan {
        if waarde == "beschut" {
            nieuw.retain(|d| *d != "register" && *d != "wajong");
        }
        if waarde == "register" || waarde == "wajong" {
            nieuw.retain(|d| *d != "beschut");
        }
        nieuw.push(waarde);
    }
    if nieuw.contains(&"wajong") && !nieuw.contains(&"register") {
        nieuw.push("register");
    }
    DOELGROEPEN
        .iter()
        .map(|(d, _)| *d)
        .filter(|d| nieuw.contains(d))
        .map(String::from)
        .collect()
}

fn zet(f: &mut Feiten, namen: &[&str]) {
    for n in namen {
        f.insert((*n).into(), Value::Bool(true));
    }
}

/// Een getal zoals JavaScript het schrijft: geheel waar het kan.
fn getal(x: f64) -> Value {
    if x.fract() == 0.0 {
        json!(x as i64)
    } else {
        json!(x)
    }
}

pub fn basisfeiten() -> Feiten {
    serde_json::from_str(BASISFEITEN).unwrap_or_default()
}

/// De feiten die bij elk vinkje een route in de engine openen, bovenop de basis.
pub fn feiten_voor(a: &Keuzes) -> Feiten {
    let d: BTreeSet<&str> = a.doelgroepen.iter().map(String::as_str).collect();
    let onder_wml = a.loonwaarde < 100.0;
    let uwv_uitkering = d.contains("wajong") || d.contains("wia");
    let verloond = getal(a.uren * 52.0);
    let mut f = Feiten::new();
    zet(
        &mut f,
        &[
            "heeft_loonaangifte_verzoek_ingediend",
            "werkgever_is_voornemens_dienstbetrekking_aan_te_gaan",
            "dienstbetrekking_is_tot_stand_gekomen",
            "verricht_arbeid_in_dienstbetrekking",
            "heeft_arbeidsverhouding_of_voorbereiding",
            "dienstbetrekking_aangevangen_na_aanvang_referteperiode",
        ],
    );
    f.insert("overeengekomen_arbeidsduur_uren_per_week".into(), getal(a.uren));
    f.insert("loonwaarde_percentage".into(), getal(a.loonwaarde));
    for n in [
        "verloonde_uren",
        "verloonde_uren_voorwaarden_2_6",
        "verloonde_uren_voorwaarden_2_10",
        "verloonde_uren_voorwaarden_2_14",
    ] {
        f.insert(n.into(), verloond.clone());
    }
    if d.contains("register") {
        zet(&mut f, &["was_arbeidsbeperkte_lid_1_of_2", "registratie_nog_niet_geeindigd"]);
        f.insert("datum_eerste_opname_doelgroepregister".into(), json!("2025-11-03"));
    }
    // Wie een UWV-uitkering heeft, valt niet onder de Pwet-doelgroep (Pwet 7 lid 3 c).
    if d.contains("bijstand") && !uwv_uitkering {
        zet(
            &mut f,
            &[
                "behoort_tot_doelgroep_artikel_7_lid_1_a",
                "ontvangt_algemene_bijstand",
                "college_verleent_toestemming_proefplaatsing",
                "is_pwet_toegeleid_naar_dienstbetrekking",
                "is_pwet_toegeleid_of_lks_lid_2",
            ],
        );
        // Pwet 10d lid 2 b: de laatste dag als persoon van artikel 7 lid 1 a, hier
        // de dag vóór de aanvang van de dienstbetrekking (basis: 2026-01-01).
        f.insert("datum_laatst_persoon_7_lid_1_a_of_7a_lid_2_b".into(), json!("2025-12-31"));
        if onder_wml {
            zet(
                &mut f,
                &[
                    "behoort_tot_doelgroep_lks",
                    "kan_minimumloon_niet_verdienen",
                    "college_heeft_loonwaarde_vastgesteld_conform_10d",
                ],
            );
            f.insert("datum_aanvraag_lks".into(), json!("2026-02-01"));
        }
    }
    if d.contains("wajong") {
        zet(
            &mut f,
            &[
                "heeft_wajong_arbeidsondersteuning_of_uitkering",
                "heeft_recht_op_arbeidsondersteuning_wajong",
                "had_of_heeft_wajong_arbeidsongeschiktheidsuitkering",
                "aanvraag_loondispensatie_ingediend",
            ],
        );
        f.insert("arbeidsprestatie_duidelijk_minder_dan_minimumloon".into(), json!(onder_wml));
        f.insert("gebruikelijke_beloning_per_uur_eurocent".into(), json!(WML_UUR_EUROCENT));
        f.insert(
            "gerechtvaardigde_beloning_per_uur_eurocent".into(),
            json!(((WML_UUR_EUROCENT as f64 * a.loonwaarde) / 100.0).round() as i64),
        );
        f.insert("vastgesteld_aanspraakpercentage_minimumloon".into(), getal(a.loonwaarde));
        f.insert("verwachte_duur_verminderde_prestatie_maanden".into(), json!(12));
    }
    if d.contains("wia") {
        zet(
            &mut f,
            &[
                "had_wia_recht_maand_voor_aanvang",
                "heeft_wia_uitkering_hoofdstuk_6",
                "is_ziek_geworden",
                "is_ziek_geworden_wia",
                "heeft_geldige_doelgroepverklaring_2_7",
                "heeft_structurele_functionele_beperking",
                "aanvraag_jobcoaching_ingediend",
                "aanvraag_werkplekaanpassing_ingediend",
                "ondersteuning_is_noodzakelijk_en_compenseert_beperkingen",
                "voorziening_is_meeneembaar_en_individueel_afgestemd",
                "ondersteuning_is_in_overwegende_mate_op_individu_gericht",
            ],
        );
        // WGA: wachttijd van 104 weken doorlopen, verdiencapaciteit ten hoogste 65 procent.
        f.insert("eerste_dag_wachttijd".into(), json!("2023-01-02"));
        f.insert("eerste_dag_wachttijd_wia".into(), json!("2023-01-02"));
        f.insert("verdiencapaciteit_percentage_maatmaninkomen".into(), json!(50));
        // Boven het drempelbedrag van € 195,16 (Reïntegratiebesluit 3).
        f.insert("kosten_voorziening_eurocent".into(), json!(100000));
    }
    if d.contains("wsw") {
        zet(
            &mut f,
            &[
                "is_wsw_geindiceerd_of_oude_indicatie",
                "is_wsw_werknemer",
                "is_wsw_dienstbetrekking",
                "is_wsw_of_beschut_werk_dienstbetrekking",
                "had_wsw_dienstbetrekking_of_indicatie_voorafgaand",
                "verricht_wsw_arbeid_artikel_2_zonder_terbeschikkingstelling",
                "verricht_arbeid_in_wsw_dienstbetrekking_artikel_2",
            ],
        );
    }
    if d.contains("beschut") {
        zet(
            &mut f,
            &[
                "college_heeft_vastgesteld_uitsluitend_beschut_werk",
                "is_uitgesloten_beschut_werk_pwet_10b",
                "behoort_tot_doelgroep_10b_lid_1",
                "heeft_dienstbetrekking_beschut_werk",
                "is_wsw_of_beschut_werk_dienstbetrekking",
            ],
        );
    }
    f
}

/// Eén invoer per doel, met de basis en de feiten van de keuzes.
pub fn invoer_voor(a: &Keuzes) -> Vec<Invoer> {
    let d: BTreeSet<&str> = a.doelgroepen.iter().map(String::as_str).collect();
    let mut parameters = basisfeiten();
    parameters.extend(feiten_voor(a));
    DOELEN
        .iter()
        .filter(|doel| (doel.nodig)(&d))
        .map(|doel| Invoer {
            wet: doel.wet.into(),
            output: doel.output.into(),
            peildatum: PEILDATUM.into(),
            parameters: parameters.clone(),
            uitleggen: doel.uitleggen.iter().map(|s| (*s).into()).collect(),
        })
        .collect()
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Regel {
    pub id: String,
    #[serde(rename = "bedragPerJaar")]
    pub bedrag_per_jaar: i64,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub categorie: Option<String>,
    /// Alleen bij loondispensatie: wat de werkgever per uur betaalt, in eurocent.
    #[serde(rename = "aanspraakPerUur", default, skip_serializing_if = "Option::is_none")]
    pub aanspraak_per_uur: Option<Value>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub aanname: Option<String>,
    /// Wat de engine bij deze regeling niet rekent en de jurist als voorbehoud wil tonen.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub voorbehoud: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Overig {
    pub id: String,
    pub geldt: bool,
    #[serde(rename = "duurJaren", default, skip_serializing_if = "Option::is_none")]
    pub duur_jaren: Option<Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Uitkomsten {
    pub regels: Vec<Regel>,
    pub overige: Vec<Overig>,
    pub aannames: Vec<String>,
}

/// Wat de engine bij het loonkostenvoordeel niet rekent en de jurist als
/// disclaimer wil tonen (juristfeedback ronde 3, punt 4). De zes maanden staan
/// alleen in Wtl 2.6 lid 1 b (arbeidsgehandicapte werknemer).
pub fn lkv_voorbehoud(categorie: Option<&str>) -> Vec<String> {
    let ids: &[&str] = match categorie {
        None | Some("") => &[],
        Some("arbeidsgehandicapte_werknemer") => &["zes_maanden", "samenloop"],
        Some(_) => &["samenloop"],
    };
    ids.iter().map(|s| (*s).into()).collect()
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct BalansRegel {
    pub id: &'static str,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub regel: Option<Regel>,
    /// Wat de regeling in de balans aftrekt, in eurocent per jaar.
    pub bedrag: i64,
    pub status: &'static str,
}

/// De drie regelingen met een bedrag, altijd in dezelfde volgorde, zodat de
/// balans ze ook toont als ze niet gelden. Nooit meer terug dan de loonkosten;
/// per regeling afgetopt in volgorde.
pub fn balans_regels(u: &Uitkomsten, kosten: i64) -> Vec<BalansRegel> {
    let mut over = kosten.max(0);
    ["lks", "ld", "lkv"]
        .into_iter()
        .map(|id| match u.regels.iter().find(|r| r.id == id) {
            None => BalansRegel {
                id,
                regel: None,
                bedrag: 0,
                status: if id == "ld" && u.aannames.iter().any(|a| a == "ld_cao") {
                    "niet_meegeteld"
                } else {
                    "geldt_niet"
                },
            },
            Some(regel) => {
                let bedrag = regel.bedrag_per_jaar.min(over);
                over -= bedrag;
                BalansRegel {
                    id,
                    regel: Some(regel.clone()),
                    bedrag,
                    status: "bedrag",
                }
            }
        })
        .collect()
}

pub type Outputs = Map<String, Value>;

fn waar(o: &Outputs, naam: &str) -> bool {
    o.get(naam) == Some(&Value::Bool(true))
}
fn num(o: &Outputs, naam: &str) -> f64 {
    o.get(naam).and_then(Value::as_f64).unwrap_or(0.0)
}

/// Van de engine-uitkomsten (sleutel "<wet>#<output>") naar wat het scherm toont.
pub fn uitkomsten_uit(a: &Keuzes, uit: &BTreeMap<String, Outputs>) -> Uitkomsten {
    let d: BTreeSet<&str> = a.doelgroepen.iter().map(String::as_str).collect();
    let leeg = Outputs::new();
    let van = |wet: &str, output: &str| uit.get(&format!("{wet}#{output}")).unwrap_or(&leeg);
    let lks = van("participatiewet", "heeft_recht_op_lks");
    let ld = van(
        "wet_arbeidsongeschiktheidsvoorziening_jonggehandicapten",
        "heeft_recht_op_loondispensatie",
    );
    let lkv = van("wet_tegemoetkomingen_loondomein", "heeft_recht_op_lkv");
    let nrp = van("ziektewet", "heeft_recht_op_no_risk_polis");
    let vz = van("wet_werk_en_inkomen_naar_arbeidsvermogen", "mag_jobcoaching_toekennen");

    let mut regels = Vec::new();
    if waar(lks, "heeft_recht_op_lks") {
        regels.push(Regel {
            id: "lks".into(),
            bedrag_per_jaar: (num(lks, "hoogte_lks_eurocent_per_maand") * 12.0).round() as i64,
            categorie: None,
            aanspraak_per_uur: None,
            aanname: Some("lks_lid4".into()),
            voorbehoud: vec![],
        });
    }
    // Boven het minimumloon hangt het van de cao af of loondispensatie het loon verlaagt.
    let ld_recht = waar(ld, "heeft_recht_op_loondispensatie");
    let ld_boven_wml = ld_recht && a.uurloon > WML_UUR_EUROCENT;
    if ld_recht && !ld_boven_wml {
        let per_uur = num(ld, "aanspraak_beloning_per_uur_eurocent");
        regels.push(Regel {
            id: "ld".into(),
            bedrag_per_jaar: ((WML_UUR_EUROCENT as f64 - per_uur) * a.uren * 52.0 * OPSLAG).round() as i64,
            categorie: None,
            aanspraak_per_uur: Some(getal(per_uur)),
            aanname: None,
            voorbehoud: vec![],
        });
    }
    let lkv_jaar = num(lkv, "hoogte_lkv_per_jaar_eurocent");
    if waar(lkv, "heeft_recht_op_lkv") && lkv_jaar > 0.0 {
        let categorie = match lkv.get("categorie_lkv") {
            Some(Value::String(s)) => s.clone(),
            Some(v) => v.to_string(),
            None => String::new(),
        };
        regels.push(Regel {
            id: "lkv".into(),
            bedrag_per_jaar: lkv_jaar.round() as i64,
            voorbehoud: lkv_voorbehoud(Some(&categorie)),
            aanname: if categorie == "arbeidsgehandicapte_werknemer" {
                Some("wia_nieuw".into())
            } else {
                None
            },
            categorie: Some(categorie),
            aanspraak_per_uur: None,
        });
    }

    let overige = vec![
        Overig {
            id: "nrp".into(),
            geldt: waar(nrp, "heeft_recht_op_no_risk_polis"),
            duur_jaren: Some(getal(num(nrp, "duur_no_risk_polis_jaren"))),
        },
        Overig {
            id: "pp_pwet".into(),
            geldt: waar(van("participatiewet", "mag_proefplaatsing_aangaan"), "mag_proefplaatsing_aangaan"),
            duur_jaren: None,
        },
        Overig {
            id: "pp_ww".into(),
            geldt: waar(
                van("werkloosheidswet", "uwv_mag_toestemming_verlenen"),
                "uwv_mag_toestemming_verlenen",
            ),
            duur_jaren: None,
        },
        Overig {
            id: "begeleiding".into(),
            geldt: waar(
                van("participatiewet", "heeft_aanspraak_op_begeleiding_op_de_werkplek"),
                "heeft_aanspraak_op_begeleiding_op_de_werkplek",
            ),
            duur_jaren: None,
        },
        Overig {
            id: "vz_wia".into(),
            geldt: waar(vz, "mag_jobcoaching_toekennen") || waar(vz, "mag_werkplekaanpassing_toekennen"),
            duur_jaren: None,
        },
        // Wajong 2:22 zit niet in de doelen; de kaart noemt het bij elk Wajong-recht.
        Overig {
            id: "vz_wajong".into(),
            geldt: d.contains("wajong"),
            duur_jaren: None,
        },
    ];

    let mut aannames = Vec::new();
    if ld_boven_wml {
        aannames.push("ld_cao".into());
    }
    if d.contains("wsw") {
        aannames.push("wsw_zuinig".into());
    }
    if d.contains("beschut") && !d.contains("bijstand") {
        aannames.push("beschut_lks".into());
    }
    if d.contains("geen") {
        aannames.push("geen".into());
    }
    Uitkomsten { regels, overige, aannames }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn s(v: &[&str]) -> Vec<String> {
        v.iter().map(|x| (*x).into()).collect()
    }

    #[test]
    fn wajong_vinkt_register_aan() {
        assert_eq!(kies_doelgroep(&[], "wajong", true), s(&["register", "wajong"]));
    }
    #[test]
    fn beschut_haalt_register_en_wajong_weg() {
        assert_eq!(kies_doelgroep(&s(&["register", "wajong"]), "beschut", true), s(&["beschut"]));
    }
    #[test]
    fn register_haalt_beschut_weg() {
        assert_eq!(
            kies_doelgroep(&s(&["beschut", "bijstand"]), "register", true),
            s(&["register", "bijstand"])
        );
    }
    #[test]
    fn geen_sluit_de_rest_uit() {
        assert_eq!(kies_doelgroep(&s(&["register", "wia"]), "geen", true), s(&["geen"]));
    }
    #[test]
    fn basisfeiten_laden() {
        assert!(basisfeiten().len() > 100);
    }
    #[test]
    fn balans_topt_af_in_volgorde() {
        let r = |id: &str, b| Regel {
            id: id.into(),
            bedrag_per_jaar: b,
            categorie: None,
            aanspraak_per_uur: None,
            aanname: None,
            voorbehoud: vec![],
        };
        let u = Uitkomsten {
            regels: vec![r("lks", 800), r("lkv", 500)],
            overige: vec![],
            aannames: vec![],
        };
        let b = balans_regels(&u, 1000);
        assert_eq!(
            b.iter().map(|x| (x.id, x.bedrag, x.status)).collect::<Vec<_>>(),
            vec![("lks", 800, "bedrag"), ("ld", 0, "geldt_niet"), ("lkv", 200, "bedrag")]
        );
    }
}
