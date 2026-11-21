//! "Waarom deze uitkomst?" uit de beslisgraaf, zonder taalmodel: vaste
//! zinnen per knooptype. Drie niveaus: `kort` (de uitkomst en het bedrag),
//! `motivering` (de voorwaarden die de uitkomst direct dragen, met hun
//! gegevens en vindplaats) en `volledig` (de hele graaf als boom). Elke zin
//! noemt alleen wat in de graaf staat; bedragen zijn de exacte waarde van de
//! engine, afgerond op centen.

use crate::graaf::{Graaf, Knoop, Vergelijking, Vindplaats};
use serde::Serialize;
use serde_json::Value;
use std::collections::BTreeSet;

/// Leesbare namen voor uitkomsten en gegevens van de casus.
const LABELS: &str = include_str!("../casus/iemand-aannemen/labels.json");

#[derive(Debug, Clone, Serialize, PartialEq, Default)]
pub struct Uitleg {
    pub kort: Vec<String>,
    pub motivering: Vec<Motivering>,
    pub volledig: Vec<Regel>,
    /// Wat het corpus bij deze uitkomst niet meerekent, uit de markeringen.
    pub voorbehouden: Vec<String>,
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct Motivering {
    pub tekst: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub status: Option<&'static str>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub vindplaats: Option<Vindplaats>,
    pub gegevens: Vec<String>,
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct Regel {
    pub diepte: usize,
    pub tekst: String,
    pub knoop: String,
}

fn labels() -> serde_json::Map<String, Value> {
    serde_json::from_str(LABELS).unwrap_or_default()
}

pub fn label(naam: &str) -> String {
    if let Some(Value::String(l)) = labels().get(naam) {
        return l.clone();
    }
    let n = naam.trim_end_matches("_eurocent").replace("_eurocent_", "_");
    let mut t = n.replace('_', " ");
    if let Some(eerste) = t.get_mut(0..1) {
        eerste.make_ascii_uppercase();
    }
    t
}

fn euro(cent: f64) -> String {
    let c = cent.round() as i64;
    let (heel, rest) = (c.abs() / 100, c.abs() % 100);
    let mut s = heel.to_string();
    let mut i = s.len() as i64 - 3;
    while i > 0 {
        s.insert(i as usize, '.');
        i -= 3;
    }
    format!("{}€ {},{:02}", if c < 0 { "-" } else { "" }, s, rest)
}

const MAANDEN: [&str; 12] = [
    "januari",
    "februari",
    "maart",
    "april",
    "mei",
    "juni",
    "juli",
    "augustus",
    "september",
    "oktober",
    "november",
    "december",
];

fn datum(s: &str) -> Option<String> {
    let d: Vec<&str> = s.split('-').collect();
    if d.len() != 3 || d[0].len() != 4 {
        return None;
    }
    let m: usize = d[1].parse().ok()?;
    let dag: u32 = d[2].parse().ok()?;
    Some(format!("{} {} {}", dag, MAANDEN.get(m.checked_sub(1)?)?, d[0]))
}

fn periode(naam: &str) -> &'static str {
    if naam.contains("per_maand") {
        " per maand"
    } else if naam.contains("per_jaar") {
        " per jaar"
    } else if naam.contains("per_uur") {
        " per uur"
    } else {
        ""
    }
}

/// Een waarde zoals een mens hem leest.
pub fn waarde(k: &Knoop) -> String {
    match (&k.waarde, k.eenheid.as_deref()) {
        (Value::Bool(true), _) => "ja".into(),
        (Value::Bool(false), _) => "nee".into(),
        (Value::Null, _) => "niet ingevuld".into(),
        (Value::Object(o), _) if o.contains_key("__unknown") => "onbekend".into(),
        (Value::Number(n), Some("eurocent")) => format!("{}{}", euro(n.as_f64().unwrap_or(0.0)), periode(&k.naam)),
        (Value::Number(n), _) if k.naam.ends_with("_eurocent") || k.naam.contains("_eurocent_") => {
            format!("{}{}", euro(n.as_f64().unwrap_or(0.0)), periode(&k.naam))
        }
        (Value::Number(n), _) => n.to_string().replace('.', ","),
        (Value::String(s), _) => datum(s).unwrap_or_else(|| label(s).to_lowercase()),
        (w, _) => w.to_string(),
    }
}

fn operand_tekst(naam: &Option<String>, w: &Value) -> String {
    let leeg = Knoop {
        id: String::new(),
        soort: "fact",
        naam: naam.clone().unwrap_or_default(),
        omschrijving: None,
        waarde: w.clone(),
        status: None,
        eenheid: None,
        vergelijking: None,
        bron: None,
        ontbreekt: vec![],
        vindplaats: None,
    };
    match naam {
        Some(n) => format!("{} ({})", label(n).to_lowercase(), waarde(&leeg)),
        None => waarde(&leeg),
    }
}

/// Een vergelijking in woorden. Een vergelijking met een lege waarde is de
/// vraag of een gegeven is ingevuld; zo leest een mens hem ook.
fn vergelijking_tekst(v: &Vergelijking) -> String {
    let leeg = |o: &crate::graaf::Operand| o.letterlijk && o.waarde.is_null();
    if let [a, b] = v.operanden.as_slice() {
        let (gegeven, _) = if leeg(b) {
            (a, b)
        } else if leeg(a) {
            (b, a)
        } else {
            (a, a)
        };
        if leeg(a) || leeg(b) {
            let naam = gegeven
                .naam
                .as_deref()
                .map(|n| label(n).to_lowercase())
                .unwrap_or_else(|| "de uitkomst".into());
            return match v.operator.as_str() {
                "=" => format!("{naam} is niet ingevuld"),
                "≠" => format!("{naam} is ingevuld"),
                op => format!("{naam} {op} leeg"),
            };
        }
    }
    v.operanden
        .iter()
        .map(|o| operand_tekst(&o.naam, &o.waarde))
        .collect::<Vec<_>>()
        .join(&format!(" {} ", v.operator))
}

fn vindplaats_tekst(v: &Vindplaats) -> String {
    let wet = v.wetnaam.clone().unwrap_or_else(|| label(&v.wet));
    match (&v.artikel, &v.lid) {
        (Some(a), Some(l)) => format!("{wet}, artikel {a} lid {l}"),
        (Some(a), None) => format!("{wet}, artikel {a}"),
        _ => wet,
    }
}

fn status_tekst(s: Option<&str>) -> &'static str {
    match s {
        Some("ja") => "vervuld",
        Some("nee") => "niet vervuld",
        Some(_) => "nog niet te bepalen",
        None => "",
    }
}

fn vindplaats_van(g: &Graaf, id: &str) -> Option<Vindplaats> {
    g.doelen(id)
        .into_iter()
        .find(|(_, s)| *s == "based_on")
        .and_then(|(k, _)| k.vindplaats.clone())
}

fn knoop_tekst(g: &Graaf, k: &Knoop) -> String {
    match k.soort {
        "fact" => {
            let bron = if k.bron == Some("wet") { " (uit de wet)" } else { "" };
            format!("{}: {}{}", label(&k.naam), waarde(k), bron)
        }
        "law" => k.vindplaats.as_ref().map(vindplaats_tekst).unwrap_or_else(|| k.naam.clone()),
        _ => {
            let kern = match &k.vergelijking {
                Some(v) => vergelijking_tekst(v),
                None => label(&k.naam),
            };
            let mut t = match k.status {
                Some(_) => format!("{}: {}", kern, status_tekst(k.status)),
                None => format!("{}: {}", kern, waarde(k)),
            };
            if !k.ontbreekt.is_empty() {
                t.push_str(&format!(
                    " (ontbreekt: {})",
                    k.ontbreekt.iter().map(|n| label(n).to_lowercase()).collect::<Vec<_>>().join(", ")
                ));
            }
            if let Some(v) = vindplaats_van(g, &k.id) {
                t.push_str(&format!(" — {}", vindplaats_tekst(&v)));
            }
            t
        }
    }
}

fn kort(g: &Graaf, k: &Knoop) -> String {
    let l = label(&k.naam);
    match k.status {
        Some("ja") => format!("{l}: de voorwaarden zijn vervuld."),
        Some("nee") => format!("{l}: de voorwaarden zijn niet vervuld."),
        Some(_) => {
            let ontbreekt = k.ontbreekt.iter().map(|n| label(n).to_lowercase()).collect::<Vec<_>>().join(", ");
            if ontbreekt.is_empty() {
                format!("{l}: dit is nog niet te bepalen.")
            } else {
                format!("{l}: dit is nog niet te bepalen; daarvoor ontbreekt {ontbreekt}.")
            }
        }
        None => {
            let _ = g;
            format!("{l}: {}.", waarde(k))
        }
    }
}

fn boom(g: &Graaf, id: &str, diepte: usize, bezocht: &mut BTreeSet<String>, uit: &mut Vec<Regel>) {
    let Some(k) = g.knoop(id) else { return };
    let herhaald = !bezocht.insert(id.to_string());
    let tekst = if herhaald && k.soort != "fact" {
        format!("{} (zie hierboven)", knoop_tekst(g, k))
    } else {
        knoop_tekst(g, k)
    };
    uit.push(Regel {
        diepte,
        tekst,
        knoop: k.id.clone(),
    });
    // Een gegeven is een blad; een knoop die al uitgeschreven is, wordt niet nog eens uitgeklapt.
    if herhaald || k.soort == "fact" {
        return;
    }
    let mut onder: Vec<(&Knoop, &str)> = g.bronnen(id).into_iter().filter(|(_, s)| *s != "has_fact").collect();
    for (f, s) in g.doelen(id) {
        if s == "has_fact" {
            onder.push((f, s));
        }
    }
    // Eerst de voorwaarden die de uitkomst droegen, dan berekeningen, dan gegevens.
    onder.sort_by_key(|(k, s)| {
        (
            if *s == "has_fact" {
                2
            } else if k.soort == "calculation" {
                1
            } else {
                0
            },
            k.id.clone(),
        )
    });
    for (kind, _) in onder {
        boom(g, &kind.id, diepte + 1, bezocht, uit);
    }
}

pub fn uitleg(g: &Graaf) -> Uitleg {
    let mut u = Uitleg::default();
    for id in &g.beslissingen {
        if let Some(k) = g.knoop(id) {
            u.kort.push(kort(g, k));
        }
    }
    if let Some(hoofd) = g.beslissingen.first() {
        for (k, _) in g.bronnen(hoofd) {
            let gegevens = g
                .doelen(&k.id)
                .into_iter()
                .filter(|(_, s)| *s == "has_fact")
                .map(|(f, _)| knoop_tekst(g, f))
                .collect();
            u.motivering.push(Motivering {
                tekst: knoop_tekst(g, k),
                status: k.status,
                vindplaats: vindplaats_van(g, &k.id),
                gegevens,
            });
        }
        // Wat de hoofduitkomst rechtstreeks aan gegevens gebruikt, ook zonder tussenliggende voorwaarde.
        let direct: Vec<String> = g
            .doelen(hoofd)
            .into_iter()
            .filter(|(_, s)| *s == "has_fact")
            .map(|(f, _)| knoop_tekst(g, f))
            .collect();
        if !direct.is_empty() {
            u.motivering.push(Motivering {
                tekst: "Gebruikte gegevens".into(),
                status: None,
                vindplaats: vindplaats_van(g, hoofd),
                gegevens: direct,
            });
        }
    }
    let mut bezocht = BTreeSet::new();
    for id in &g.beslissingen {
        boom(g, id, 0, &mut bezocht, &mut u.volledig);
    }
    u.voorbehouden = g
        .markeringen
        .iter()
        .map(|m| format!("Niet meegerekend: {} ({}).", m.onderwerp, vindplaats_tekst(&m.vindplaats)))
        .collect();
    u
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn euro_rondt_af_op_centen_met_punten() {
        assert_eq!(euro(89740.8), "€ 897,41");
        assert_eq!(euro(507520.0), "€ 5.075,20");
        assert_eq!(euro(123456789.0), "€ 1.234.567,89");
    }

    #[test]
    fn datum_in_woorden() {
        assert_eq!(datum("2026-02-01").as_deref(), Some("1 februari 2026"));
        assert_eq!(datum("geen datum"), None);
    }

    #[test]
    fn label_valt_terug_op_naam() {
        assert_eq!(label("datum_aanvraag_iets_onbekends"), "Datum aanvraag iets onbekends");
    }
}
