//! De referentieset (fixtures/referentieset.json) tegen de kern.
//!
//! 1. De vertaling van keuzes naar aanroepen is dezelfde als die van het
//!    portaal waaruit hij overgenomen is: per geval dezelfde parameters en
//!    dezelfde aanroepen. Draait altijd.
//! 2. De outputs van de kern tegen die van de portaalbundel. Vraagt de wetten
//!    van de bundel (`REKENKERN_WETTEN=<wetten.json>`); zonder die variabele
//!    slaat de test zich over. Verschillen die uit een gewijzigd corpus komen,
//!    staan met reden in fixtures/verwachte-verschillen.json; elk ander
//!    verschil laat de test falen.

use da_rekenkern::aannemen::{invoer_voor, Keuzes};
use da_rekenkern::kern::{Kern, Verzoek};
use serde_json::{Map, Value};
use std::collections::BTreeMap;

fn fixture() -> Value {
    serde_json::from_str(include_str!("fixtures/referentieset.json")).expect("fixture leesbaar")
}

fn keuzes(g: &Value) -> Keuzes {
    serde_json::from_value(g["keuzes"].clone()).expect("keuzes")
}

/// De feiten die de kern sinds de overname zelf toevoegt (het portaal kende ze
/// niet), met de reden. Ze moeten in de basis of de feitenlaag terugkomen,
/// niet in de vergelijking verdwijnen.
fn toegevoegd() -> BTreeMap<String, Value> {
    let v: Value = serde_json::from_str(include_str!("fixtures/verwachte-verschillen.json")).expect("verschillen leesbaar");
    v["feiten"].as_object().cloned().unwrap_or_default().into_iter().collect()
}

#[test]
fn invoer_gelijk_aan_portaal() {
    let f = fixture();
    let nieuw = toegevoegd();
    let gevallen = f["gevallen"].as_array().expect("gevallen");
    assert_eq!(gevallen.len(), 128);
    for g in gevallen {
        let k = keuzes(g);
        let invoer = invoer_voor(&k);
        let aanroepen: Vec<Value> = invoer
            .iter()
            .map(|i| serde_json::json!({ "wet": i.wet, "output": i.output, "uitleggen": i.uitleggen }))
            .collect();
        assert_eq!(Value::Array(aanroepen), g["aanroepen"], "aanroepen bij {k:?}");
        if let Some(i) = invoer.first() {
            let mut eigen: Map<String, Value> = i.parameters.clone();
            eigen.retain(|naam, _| !nieuw.contains_key(naam));
            // De portaalparameters zijn de basis plus de feiten van de keuzes.
            let mut portaal = f["basis"].as_object().cloned().unwrap_or_default();
            portaal.extend(g["feiten"].as_object().cloned().unwrap_or_default());
            portaal.retain(|naam, _| !nieuw.contains_key(naam));
            assert_eq!(eigen, portaal, "parameters bij {k:?}");
        }
    }
}

#[test]
fn outputs_gelijk_aan_portaalbundel() {
    let Ok(pad) = std::env::var("REKENKERN_WETTEN") else {
        eprintln!("REKENKERN_WETTEN niet gezet; vergelijking overgeslagen");
        return;
    };
    let kern = Kern::laad_json(&std::fs::read_to_string(pad).expect("wetten leesbaar")).expect("wetten laden");
    assert!(kern.geweigerd.is_empty(), "geweigerde wetversies: {:?}", kern.geweigerd);
    let verwacht: Value = serde_json::from_str(include_str!("fixtures/verwachte-verschillen.json")).expect("verschillen leesbaar");
    let toegestaan = verwacht["outputs"].as_array().cloned().unwrap_or_default();
    let mut onverwacht = Vec::new();
    let mut gezien = std::collections::BTreeSet::new();
    for g in fixture()["gevallen"].as_array().expect("gevallen") {
        let k = keuzes(g);
        for i in invoer_voor(&k) {
            let sleutel = format!("{}#{}", i.wet, i.output);
            let a = kern
                .bereken(&Verzoek {
                    wet: i.wet,
                    output: i.output,
                    peildatum: i.peildatum,
                    parameters: i.parameters,
                    uitleggen: i.uitleggen,
                })
                .expect("berekening");
            let oud = g["outputs"][&sleutel].as_object().cloned().unwrap_or_default();
            for (naam, waarde) in &oud {
                let nieuw = a.outputs.get(naam).cloned().unwrap_or(Value::Null);
                if !gelijk(&nieuw, waarde) {
                    let regel = toegestaan.iter().position(|t| past(t, &sleutel, naam, &k, waarde, &nieuw));
                    match regel {
                        Some(r) => {
                            gezien.insert(r);
                        }
                        None => onverwacht.push(format!(
                            "{} {sleutel} {naam}: portaal {waarde}, kern {nieuw}",
                            serde_json::to_string(&k.doelgroepen).unwrap_or_default()
                        )),
                    }
                }
            }
        }
    }
    let ongebruikt: Vec<_> = (0..toegestaan.len())
        .filter(|r| !gezien.contains(r))
        .map(|r| toegestaan[r]["reden"].clone())
        .collect();
    assert!(
        onverwacht.is_empty(),
        "{} onverwachte verschillen:\n{}",
        onverwacht.len(),
        onverwacht.join("\n")
    );
    assert!(
        ongebruikt.is_empty(),
        "verwachte verschillen die niet meer optreden: {ongebruikt:?}"
    );
}

/// Getallen gelijk tot op een duizendste eurocent; de rest exact.
fn gelijk(a: &Value, b: &Value) -> bool {
    match (a.as_f64(), b.as_f64()) {
        (Some(x), Some(y)) => (x - y).abs() < 1e-3,
        _ => a == b,
    }
}

/// Past een verschil op een regel uit verwachte-verschillen.json?
/// Een regel noemt `uitkomst` (wet#output), `output`, optioneel `doelgroep`
/// (moet in de keuzes zitten), `portaal` en `kern` (optioneel; anders elke waarde).
fn past(t: &Value, sleutel: &str, naam: &str, k: &Keuzes, oud: &Value, nieuw: &Value) -> bool {
    t["uitkomst"] == sleutel
        && t["output"] == naam
        && t.get("doelgroep")
            .and_then(Value::as_str)
            .is_none_or(|d| k.doelgroepen.iter().any(|x| x == d))
        && t.get("portaal").is_none_or(|w| gelijk(w, oud))
        && t.get("kern")
            .is_none_or(|w| gelijk(w, nieuw) || (w == "onbekend" && nieuw.get("__unknown").is_some()))
}

/// Verkenning bij een nieuwe corpus-pin: welke gegevens ontbreken of breken
/// per uitkomst over de hele referentieset. Draai met
/// `REKENKERN_WETTEN=… cargo test --test referentie -- --ignored --nocapture`.
#[test]
#[ignore]
fn verken_ontbrekende_gegevens() {
    let pad = std::env::var("REKENKERN_WETTEN").expect("REKENKERN_WETTEN");
    let kern = Kern::laad_json(&std::fs::read_to_string(pad).expect("wetten leesbaar")).expect("wetten laden");
    let mut telling: BTreeMap<String, usize> = BTreeMap::new();
    for g in fixture()["gevallen"].as_array().expect("gevallen") {
        for i in invoer_voor(&keuzes(g)) {
            let sleutel = format!("{}#{}", i.wet, i.output);
            match kern.bereken(&Verzoek {
                wet: i.wet,
                output: i.output,
                peildatum: i.peildatum,
                parameters: i.parameters,
                uitleggen: i.uitleggen,
            }) {
                Err(e) => *telling.entry(format!("FOUT {sleutel}: {}", e.bericht)).or_default() += 1,
                Ok(a) => {
                    for w in a.outputs.values() {
                        for m in w.get("missing").and_then(Value::as_array).into_iter().flatten() {
                            *telling
                                .entry(format!("ONBEKEND {sleutel}: {}", m["name"].as_str().unwrap_or("?")))
                                .or_default() += 1;
                        }
                    }
                }
            }
        }
    }
    for (regel, n) in telling {
        println!("{n:4} {regel}");
    }
}

/// Wat een scherm toont (regels, overige, aannames) is per geval gelijk aan
/// wat het portaal er met `uitkomstenUit` van maakte. Het voorbehoud bij het
/// loonkostenvoordeel zat in het portaal in een losse functie; de kern zet
/// het bij de regel, dus dat veld telt hier niet mee.
#[test]
fn uitkomsten_gelijk_aan_portaal() {
    let Ok(pad) = std::env::var("REKENKERN_WETTEN") else {
        eprintln!("REKENKERN_WETTEN niet gezet; vergelijking overgeslagen");
        return;
    };
    let kern = Kern::laad_json(&std::fs::read_to_string(pad).expect("wetten leesbaar")).expect("wetten laden");
    for g in fixture()["gevallen"].as_array().expect("gevallen") {
        let k = keuzes(g);
        let mut eigen = serde_json::to_value(kern.orienteer(&k).expect("oriëntatie").uitkomsten).expect("json");
        for r in eigen["regels"].as_array_mut().into_iter().flatten() {
            r.as_object_mut().map(|o| o.remove("voorbehoud"));
        }
        assert_eq!(eigen, g["uitkomsten"], "uitkomsten bij {k:?}");
    }
}
