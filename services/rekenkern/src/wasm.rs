//! De kern in de browser. Elke functie neemt en geeft JSON-tekst; een antwoord
//! is altijd `{"ok": true, ...}` of `{"ok": false, "fout": {code, bericht}}`,
//! zodat een worker het zonder exceptions kan doorgeven. Er wordt hier niets
//! gerekend of bewoord: alles zit in de kern.

use crate::aannemen::{balans_regels, kies_doelgroep, Uitkomsten, DOELGROEPEN};
use crate::kern::{Fout, Kern, ALLOWLIST, PEILDATUMS, VERZOEK_ONGELDIG};
use serde::Serialize;
use serde_json::json;
use wasm_bindgen::prelude::*;

fn goed(sleutel: &str, waarde: impl Serialize) -> String {
    json!({ "ok": true, sleutel: waarde }).to_string()
}

fn fout(f: Fout) -> String {
    json!({ "ok": false, "fout": f }).to_string()
}

fn ongeldig(e: impl std::fmt::Display) -> String {
    fout(Fout {
        code: VERZOEK_ONGELDIG,
        bericht: e.to_string(),
    })
}

#[wasm_bindgen]
pub struct Rekenkern {
    kern: Kern,
}

#[wasm_bindgen]
impl Rekenkern {
    /// Laadt de wetten uit `wetten.json` van de bundel. Gooit bij een ongeldige bundel.
    #[wasm_bindgen(constructor)]
    pub fn new(wetten: &str) -> Result<Rekenkern, JsError> {
        Kern::laad_json(wetten)
            .map(|kern| Rekenkern { kern })
            .map_err(|f| JsError::new(&f.to_string()))
    }

    /// Rekent één verzoek `{wet, output, peildatum, parameters, uitleggen}`.
    pub fn bereken(&self, verzoek: &str) -> String {
        match self.kern.bereken_json(verzoek) {
            Ok(a) => goed("antwoord", a),
            Err(f) => fout(f),
        }
    }

    /// Rekent de oriëntatie van "iemand aannemen" voor `{doelgroepen, uren, loonwaarde, uurloon}`.
    pub fn orienteer(&self, keuzes: &str) -> String {
        match self.kern.orienteer_json(keuzes) {
            Ok(o) => goed("orientatie", o),
            Err(f) => fout(f),
        }
    }

    /// Wetversies die de engine niet kon laden; leeg bij een goede bundel.
    pub fn geweigerd(&self) -> String {
        goed("geweigerd", &self.kern.geweigerd)
    }
}

/// De uitkomsten die de kern rekent en de peildatums: het contract.
#[wasm_bindgen]
pub fn allowlist() -> String {
    let lijst: Vec<_> = ALLOWLIST
        .iter()
        .map(|(w, o, u)| json!({ "wet": w, "output": o, "uitleggen": u }))
        .collect();
    json!({ "ok": true, "allowlist": lijst, "peildatums": PEILDATUMS }).to_string()
}

/// De zeven antwoorden op vraag 1, met hun tekst.
#[wasm_bindgen]
pub fn doelgroepen() -> String {
    let lijst: Vec<_> = DOELGROEPEN.iter().map(|(id, tekst)| json!({ "id": id, "tekst": tekst })).collect();
    goed("doelgroepen", lijst)
}

/// Zet een vinkje bij vraag 1 aan of uit, met de uitsluitingen van Wfsv 38b.
#[wasm_bindgen(js_name = kiesDoelgroep)]
pub fn kies_doelgroep_js(huidig: &str, waarde: &str, aan: bool) -> String {
    match serde_json::from_str::<Vec<String>>(huidig) {
        Ok(h) => goed("doelgroepen", kies_doelgroep(&h, waarde, aan)),
        Err(e) => ongeldig(e),
    }
}

/// De balans van loonkosten (eurocent per jaar) tegen de regelingen met een bedrag.
#[wasm_bindgen]
pub fn balans(uitkomsten: &str, kosten: f64) -> String {
    match serde_json::from_str::<Uitkomsten>(uitkomsten) {
        Ok(u) => goed("balans", balans_regels(&u, kosten.round() as i64)),
        Err(e) => ongeldig(e),
    }
}

#[wasm_bindgen]
pub fn versie() -> String {
    crate::versie().to_string()
}
