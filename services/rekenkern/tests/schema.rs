//! De JSON Schema's van het contract (schema/) tegen echte verzoeken,
//! antwoorden en fouten van de kern. Vraagt `REKENKERN_WETTEN=<wetten.json>`
//! voor de antwoorden; de schema's zelf worden altijd gecontroleerd.

use da_rekenkern::kern::{Kern, Verzoek, ALLOWLIST};
use jsonschema::Validator;
use serde_json::{json, Value};

fn schema(naam: &str) -> Value {
    let pad = format!("{}/schema/{naam}.schema.json", env!("CARGO_MANIFEST_DIR"));
    serde_json::from_str(&std::fs::read_to_string(pad).expect("schema leesbaar")).expect("schema is JSON")
}

fn validator(naam: &str) -> Validator {
    let mut s = schema(naam);
    // De oriëntatie verwijst naar keuzes en antwoord; die worden los getoetst.
    if naam == "orientatie" {
        s["properties"]["keuzes"] = json!(true);
        s["properties"]["antwoorden"]["items"] = json!(true);
    }
    jsonschema::validator_for(&s).unwrap_or_else(|e| panic!("{naam}: {e}"))
}

fn geldig(v: &Validator, w: &Value) -> Result<(), String> {
    let fouten: Vec<String> = v.iter_errors(w).map(|e| format!("{} bij {}", e, e.instance_path())).collect();
    if fouten.is_empty() {
        Ok(())
    } else {
        Err(fouten.join("; "))
    }
}

#[test]
fn verzoek_volgt_de_allowlist() {
    let v = validator("verzoek");
    for (wet, output, uitleggen) in ALLOWLIST {
        let goed = json!({ "wet": wet, "output": output, "peildatum": "2026-07-01", "parameters": { "x": true }, "uitleggen": uitleggen });
        geldig(&v, &goed).unwrap_or_else(|e| panic!("{wet}#{output}: {e}"));
    }
    let fout = [
        json!({ "wet": "participatiewet", "output": "is_uitgesloten_lid_3", "peildatum": "2026-07-01", "parameters": {} }),
        json!({ "wet": "participatiewet", "output": "heeft_recht_op_lks", "peildatum": "2025-01-01", "parameters": {} }),
        json!({ "wet": "participatiewet", "output": "mag_proefplaatsing_aangaan", "peildatum": "2026-07-01", "parameters": {}, "uitleggen": ["hoogte_lks_eurocent_per_maand"] }),
        json!({ "wet": "participatiewet", "output": "heeft_recht_op_lks", "peildatum": "2026-07-01", "parameters": {}, "extra": 1 }),
        json!({ "wet": "participatiewet", "output": "heeft_recht_op_lks", "peildatum": "2026-07-01", "parameters": { "x": [1] } }),
    ];
    for f in fout {
        assert!(geldig(&v, &f).is_err(), "zou ongeldig moeten zijn: {f}");
    }
}

#[test]
fn keuzes_en_fouten() {
    let k = validator("keuzes");
    geldig(&k, &json!({ "doelgroepen": [], "uren": 32, "loonwaarde": 60, "uurloon": 1499 })).expect("leeg");
    geldig(
        &k,
        &json!({ "doelgroepen": ["register", "wajong"], "uren": 32, "loonwaarde": 60, "uurloon": 1499 }),
    )
    .expect("twee");
    assert!(geldig(
        &k,
        &json!({ "doelgroepen": ["wao"], "uren": 32, "loonwaarde": 60, "uurloon": 1499 })
    )
    .is_err());
    assert!(geldig(&k, &json!({ "doelgroepen": [], "uren": 0, "loonwaarde": 60, "uurloon": 1499 })).is_err());
    let f = validator("fout");
    geldig(&f, &json!({ "code": "REKENKERN_NIET_TOEGESTAAN", "bericht": "x" })).expect("fout");
    assert!(geldig(&f, &json!({ "code": "IETS_ANDERS", "bericht": "x" })).is_err());
}

#[test]
fn antwoorden_en_orientaties_van_de_kern_volgen_het_schema() {
    let Ok(pad) = std::env::var("REKENKERN_WETTEN") else {
        eprintln!("REKENKERN_WETTEN niet gezet; overgeslagen");
        return;
    };
    let kern = Kern::laad_json(&std::fs::read_to_string(pad).expect("wetten")).expect("laden");
    let o = validator("orientatie");
    let a = validator("antwoord");
    let f = validator("fout");
    for d in [
        vec![],
        vec!["bijstand"],
        vec!["register", "wajong"],
        vec!["wia"],
        vec!["beschut", "wsw"],
        vec!["geen"],
    ] {
        let keuzes = json!({ "doelgroepen": d, "uren": 32, "loonwaarde": 60, "uurloon": 1499 });
        let uit = serde_json::to_value(kern.orienteer_json(&keuzes.to_string()).expect("oriëntatie")).expect("json");
        geldig(&o, &uit).unwrap_or_else(|e| panic!("{d:?}: {e}"));
        geldig(&validator("keuzes"), &uit["keuzes"]).unwrap_or_else(|e| panic!("{d:?}: {e}"));
        for antwoord in uit["antwoorden"].as_array().into_iter().flatten() {
            geldig(&a, antwoord).unwrap_or_else(|e| panic!("{d:?}: {e}"));
        }
    }
    let fout = kern
        .bereken(&Verzoek {
            wet: "participatiewet".into(),
            output: "x".into(),
            peildatum: "2026-07-01".into(),
            parameters: Default::default(),
            uitleggen: vec![],
        })
        .expect_err("niet toegestaan");
    geldig(&f, &serde_json::to_value(fout).expect("json")).expect("fout volgt schema");
}
