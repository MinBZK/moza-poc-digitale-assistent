//! De minimale beslisgraaf van één uitkomst, afgeleid uit de trace van de
//! engine, volgens de Graph-conditie van Bos, Schuth en Chen, *From Rules as
//! Executed to Citizen Explanation* (JURIX 2026).
//!
//! Knopen: `decision` (de gevraagde uitkomst of het bedrag), `rule` (een
//! voorwaarde die de engine toetste), `fact` (een gegeven), `calculation`
//! (een tussenwaarde) en `law` (de vindplaats). Randen: `has_fact` (regel of
//! berekening gebruikt een gegeven), `satisfied`/`failed`/`unknown` (de
//! voorwaarde was wel/niet/nog niet vervuld, richting de knoop die hem
//! gebruikt), `used_in` (een berekening voedt een andere knoop) en
//! `based_on` (een regel of berekening rust op een artikel). `unknown` en
//! `based_on` zijn toevoegingen op het paper: de engine kent onbekende
//! uitkomsten, en de vindplaats is een rand in plaats van een eigenschap.
//!
//! Minimaal betekent: alleen wat de uitkomst draagt. Bij een AND die niet
//! slaagt, tellen alleen de operanden die niet slaagden; bij een OR die
//! slaagt alleen de operanden die slaagden; bij een IF de genomen tak. De
//! typen komen uit de trace zelf, niet uit een externe ontologie.

use crate::wetboek::Wetboek;
use serde::Serialize;
use serde_json::{Map, Value};
use std::collections::BTreeMap;

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct Knoop {
    pub id: String,
    pub soort: &'static str,
    pub naam: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub omschrijving: Option<String>,
    #[serde(skip_serializing_if = "Value::is_null")]
    pub waarde: Value,
    /// Bij een regel of beslissing met een boolean: `ja`, `nee` of `onbekend`.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub status: Option<&'static str>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub eenheid: Option<String>,
    /// Bij een vergelijking: de operator en de operanden zoals de wet ze noemt,
    /// met letterlijke drempels uit het model.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub vergelijking: Option<Vergelijking>,
    /// Bij een feit: `invoer` (aangeleverd) of `wet` (een waarde uit het corpus).
    #[serde(skip_serializing_if = "Option::is_none")]
    pub bron: Option<&'static str>,
    /// Bij een onbekende uitkomst: welke gegevens ontbraken.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub ontbreekt: Vec<String>,
    /// Bij een wet-knoop: de vindplaats.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub vindplaats: Option<Vindplaats>,
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct Vergelijking {
    pub operator: String,
    pub operanden: Vec<Operand>,
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct Operand {
    /// Naam van het gegeven of de uitkomst; leeg bij een letterlijke waarde of een deelberekening.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub naam: Option<String>,
    pub waarde: Value,
    pub letterlijk: bool,
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct Vindplaats {
    pub wet: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub wetnaam: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub artikel: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub lid: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub url: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub geldig_vanaf: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub toelichting: Option<String>,
}

#[derive(Debug, Clone, Serialize, PartialEq, Eq, PartialOrd, Ord)]
pub struct Rand {
    pub van: String,
    pub naar: String,
    pub soort: &'static str,
}

/// Wat het corpus bij deze uitkomst uitdrukkelijk niet meerekent (een
/// `marking` in het model), met de reden en de vindplaats. Een afnemer toont
/// dit als voorbehoud, zonder eigen tekst.
#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct Markering {
    pub onderwerp: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub toelichting: Option<String>,
    pub vindplaats: Vindplaats,
}

#[derive(Debug, Clone, Serialize, PartialEq, Default)]
pub struct Graaf {
    /// De id's van de beslissingsknopen: eerst de gevraagde uitkomst, dan de bedragen erbij.
    pub beslissingen: Vec<String>,
    pub knopen: Vec<Knoop>,
    pub randen: Vec<Rand>,
    pub markeringen: Vec<Markering>,
}

impl Graaf {
    pub fn knoop(&self, id: &str) -> Option<&Knoop> {
        self.knopen.iter().find(|k| k.id == id)
    }
    /// De knopen die naar `id` wijzen, met de soort rand.
    pub fn bronnen(&self, id: &str) -> Vec<(&Knoop, &'static str)> {
        self.randen
            .iter()
            .filter(|r| r.naar == id)
            .filter_map(|r| self.knoop(&r.van).map(|k| (k, r.soort)))
            .collect()
    }
    /// De knopen waar `id` naar wijst, met de soort rand.
    pub fn doelen(&self, id: &str) -> Vec<(&Knoop, &'static str)> {
        self.randen
            .iter()
            .filter(|r| r.van == id)
            .filter_map(|r| self.knoop(&r.naar).map(|k| (k, r.soort)))
            .collect()
    }
}

const VERGELIJKINGEN: [(&str, &str); 8] = [
    ("EQUALS", "="),
    ("NOT_EQUALS", "≠"),
    ("GREATER_THAN", ">"),
    ("GREATER_THAN_OR_EQUAL", "≥"),
    ("LESS_THAN", "<"),
    ("LESS_THAN_OR_EQUAL", "≤"),
    ("IN", "in"),
    ("NOT_IN", "niet in"),
];

fn operator(op: &str) -> Option<&'static str> {
    VERGELIJKINGEN.iter().find(|(o, _)| *o == op).map(|(_, s)| *s)
}

pub fn status(w: &Value) -> Option<&'static str> {
    match w {
        Value::Bool(true) => Some("ja"),
        Value::Bool(false) => Some("nee"),
        Value::Object(o) if o.get("__unknown") == Some(&Value::Bool(true)) => Some("onbekend"),
        _ => None,
    }
}

fn ontbreekt(w: &Value) -> Vec<String> {
    let mut namen: Vec<String> = w
        .get("missing")
        .and_then(Value::as_array)
        .map(|m| {
            m.iter()
                .filter_map(|x| x.get("name").and_then(Value::as_str).map(String::from))
                .collect()
        })
        .unwrap_or_default();
    namen.sort();
    namen.dedup();
    namen
}

fn rand_voor(status: Option<&'static str>) -> &'static str {
    match status {
        Some("ja") => "satisfied",
        Some("nee") => "failed",
        Some(_) => "unknown",
        None => "used_in",
    }
}

fn tekst(v: &Value, sleutel: &str) -> Option<String> {
    v.get(sleutel).and_then(Value::as_str).map(String::from)
}

/// Een kind van een trace-knoop, of leeg.
fn kinderen(n: &Value) -> &[Value] {
    n.get("children").and_then(Value::as_array).map(Vec::as_slice).unwrap_or(&[])
}

fn soort(n: &Value) -> &str {
    n.get("node_type").and_then(Value::as_str).unwrap_or("")
}
fn naam(n: &Value) -> &str {
    n.get("name").and_then(Value::as_str).unwrap_or("")
}
fn resolve(n: &Value) -> &str {
    n.get("resolve_type").and_then(Value::as_str).unwrap_or("")
}
fn resultaat(n: &Value) -> Value {
    n.get("result").cloned().unwrap_or(Value::Null)
}

/// De acties binnen één wet-context (het artikel bovenaan of een cross-law-aanroep), op naam.
struct Context<'a> {
    wet: String,
    acties: BTreeMap<&'a str, &'a Value>,
}

impl<'a> Context<'a> {
    fn van(wet: &str, knoop: &'a Value) -> Context<'a> {
        let mut acties = BTreeMap::new();
        for k in kinderen(knoop) {
            if soort(k) == "action" {
                acties.insert(naam(k), k);
            }
        }
        Context { wet: wet.into(), acties }
    }
}

struct Bouwer<'a> {
    wetboek: &'a Wetboek,
    peildatum: &'a str,
    knopen: Vec<Knoop>,
    randen: Vec<Rand>,
    /// (wet, actie) → knoop-id, zodat een uitkomst die vaker gebruikt wordt één knoop blijft.
    gezien: BTreeMap<(String, String), String>,
}

impl<'a> Bouwer<'a> {
    fn voeg(&mut self, k: Knoop) -> String {
        let id = k.id.clone();
        if !self.knopen.iter().any(|x| x.id == id) {
            self.knopen.push(k);
        }
        id
    }

    fn rand(&mut self, van: &str, naar: &str, soort: &'static str) {
        let r = Rand {
            van: van.into(),
            naar: naar.into(),
            soort,
        };
        if !self.randen.contains(&r) {
            self.randen.push(r);
        }
    }

    fn wet_knoop(&mut self, wet: &str, actie: &Value) -> Option<String> {
        let a = actie
            .get("legal_basis")
            .filter(|v| v.get("article").is_some())
            .or_else(|| actie.get("anchor"))?;
        let artikel = tekst(a, "article");
        let lid = tekst(a, "paragraph").or_else(|| lid_uit_toelichting(a));
        let wet_id = tekst(a, "law_id").unwrap_or_else(|| wet.to_string());
        let id = format!(
            "law:{}:{}:{}",
            wet_id,
            artikel.clone().unwrap_or_default(),
            lid.clone().unwrap_or_default()
        );
        let vindplaats = Vindplaats {
            wetnaam: tekst(a, "law").or_else(|| self.wetboek.naam(&wet_id, self.peildatum)),
            url: tekst(a, "url").or_else(|| self.wetboek.artikel_url(&wet_id, artikel.as_deref()?, self.peildatum)),
            geldig_vanaf: tekst(a, "valid_from").or_else(|| self.wetboek.geldig_vanaf(&wet_id, self.peildatum)),
            toelichting: tekst(a, "explanation"),
            wet: wet_id,
            artikel: artikel.clone(),
            lid: lid.clone(),
        };
        let naam = match (&artikel, &lid) {
            (Some(a), Some(l)) => format!("artikel {a} lid {l}"),
            (Some(a), None) => format!("artikel {a}"),
            _ => "artikel".into(),
        };
        Some(self.voeg(Knoop {
            id,
            soort: "law",
            naam,
            omschrijving: None,
            waarde: Value::Null,
            status: None,
            eenheid: None,
            vergelijking: None,
            bron: None,
            ontbreekt: vec![],
            vindplaats: Some(vindplaats),
        }))
    }

    fn feit(&mut self, wet: &str, n: &Value) -> String {
        let r = resolve(n);
        let bron = if matches!(r, "DEFINITION" | "OPEN_TERM" | "OPEN_TERM_SILENT") {
            "wet"
        } else {
            "invoer"
        };
        let w = resultaat(n);
        let id = format!("fact:{}", naam(n));
        let eenheid = n
            .get("type_spec")
            .and_then(|t| tekst(t, "unit"))
            .or_else(|| self.wetboek.eenheid(wet, naam(n), self.peildatum));
        self.voeg(Knoop {
            id,
            soort: "fact",
            naam: naam(n).into(),
            omschrijving: self.wetboek.omschrijving(wet, naam(n), self.peildatum),
            status: None,
            ontbreekt: if status(&w) == Some("onbekend") { ontbreekt(&w) } else { vec![] },
            waarde: w,
            eenheid,
            vergelijking: None,
            bron: Some(bron),
            vindplaats: None,
        })
    }

    /// Een actie wordt een regel (boolean) of berekening; geeft de knoop-id.
    fn actie(&mut self, ctx: &Context, actie: &Value, beslissing: bool) -> String {
        let sleutel = (ctx.wet.clone(), naam(actie).to_string());
        if let Some(id) = self.gezien.get(&sleutel).cloned() {
            if beslissing {
                if let Some(k) = self.knopen.iter_mut().find(|k| k.id == id) {
                    k.soort = "decision";
                }
            }
            return id;
        }
        let w = resultaat(actie);
        let st = status(&w);
        let soort_knoop = if beslissing {
            "decision"
        } else if st.is_some() {
            "rule"
        } else {
            "calculation"
        };
        let id = format!("{}#{}", ctx.wet, naam(actie));
        self.gezien.insert(sleutel, id.clone());
        let yaml = self.wetboek.actie(&ctx.wet, naam(actie), self.peildatum);
        let expressie = kinderen(actie).first();
        // Bestaat de actie uit één vergelijking, dan draagt de regel zelf de operator.
        let vergelijking = match (expressie, yaml.as_ref().and_then(|y| y.get("value"))) {
            (Some(e), Some(y)) if soort(e) == "operation" && operator(naam(e)).is_some() => Some(self.vergelijking(e, y)),
            _ => None,
        };
        let eenheid = actie
            .get("type_spec")
            .and_then(|t| tekst(t, "unit"))
            .or_else(|| self.wetboek.eenheid(&ctx.wet, naam(actie), self.peildatum));
        self.voeg(Knoop {
            id: id.clone(),
            soort: soort_knoop,
            naam: naam(actie).into(),
            omschrijving: self.wetboek.omschrijving(&ctx.wet, naam(actie), self.peildatum),
            status: st,
            ontbreekt: if st == Some("onbekend") { ontbreekt(&w) } else { vec![] },
            waarde: w,
            eenheid,
            vergelijking: vergelijking.clone(),
            bron: None,
            vindplaats: None,
        });
        if let Some(w) = self.wet_knoop(&ctx.wet, actie) {
            self.rand(&id, &w, "based_on");
        }
        if let Some(e) = expressie {
            let y = yaml.as_ref().and_then(|y| y.get("value")).cloned();
            if vergelijking.is_some() {
                for kind in kinderen(e) {
                    self.operand(ctx, kind, &id);
                }
            } else {
                self.expressie(ctx, e, y.as_ref(), &id);
            }
        }
        id
    }

    fn vergelijking(&self, e: &Value, y: &Value) -> Vergelijking {
        let mut operanden = Vec::new();
        let mut trace_kinderen: Vec<&Value> = kinderen(e).iter().collect();
        for sleutel in ["subject", "value", "values", "date"] {
            let Some(v) = y.get(sleutel) else { continue };
            let lijst: Vec<&Value> = match v {
                Value::Array(a) => a.iter().collect(),
                x => vec![x],
            };
            for o in lijst {
                operanden.push(match o {
                    Value::String(s) if s.starts_with('$') => {
                        let n = &s[1..];
                        let pos = trace_kinderen.iter().position(|k| naam(k) == n);
                        let waarde = pos.map(|p| resultaat(trace_kinderen.remove(p))).unwrap_or(Value::Null);
                        Operand {
                            naam: Some(n.into()),
                            waarde,
                            letterlijk: false,
                        }
                    }
                    Value::Object(_) => {
                        let pos = trace_kinderen.iter().position(|k| soort(k) == "operation");
                        let waarde = pos.map(|p| resultaat(trace_kinderen.remove(p))).unwrap_or(Value::Null);
                        Operand {
                            naam: None,
                            waarde,
                            letterlijk: false,
                        }
                    }
                    x => Operand {
                        naam: None,
                        waarde: x.clone(),
                        letterlijk: true,
                    },
                });
            }
        }
        Vergelijking {
            operator: operator(naam(e)).unwrap_or("?").into(),
            operanden,
        }
    }

    /// Een operand van een vergelijking of berekening: een gegeven, een andere uitkomst of een deelberekening.
    fn operand(&mut self, ctx: &Context, n: &Value, ouder: &str) {
        match (soort(n), resolve(n)) {
            ("resolve", "OUTPUT") | ("cached", _) => {
                if let Some(actie) = ctx.acties.get(naam(n)).copied() {
                    let id = self.actie(ctx, actie, false);
                    let st = self.knopen.iter().find(|k| k.id == id).and_then(|k| k.status);
                    self.rand(&id, ouder, rand_voor(st));
                }
            }
            ("resolve", "RESOLVED_INPUT") => {
                for kind in kinderen(n) {
                    if soort(kind) == "cross_law_reference" {
                        self.cross_law(kind, ouder);
                    }
                }
                if !kinderen(n).iter().any(|k| soort(k) == "cross_law_reference") {
                    let f = self.feit(&ctx.wet, n);
                    self.rand(ouder, &f, "has_fact");
                }
            }
            ("resolve", _) => {
                if naam(n) == "bsn" {
                    return;
                }
                let f = self.feit(&ctx.wet, n);
                self.rand(ouder, &f, "has_fact");
            }
            ("cross_law_reference", _) => self.cross_law(n, ouder),
            ("open_term_resolution", _) | ("operation", _) => {
                for kind in kinderen(n) {
                    self.operand(ctx, kind, ouder);
                }
            }
            _ => {}
        }
    }

    fn cross_law(&mut self, n: &Value, ouder: &str) {
        let Some((wet, output)) = naam(n).split_once('#') else { return };
        let ctx = Context::van(wet, n);
        if let Some(actie) = ctx.acties.get(output).copied() {
            let id = self.actie(&ctx, actie, false);
            let st = self.knopen.iter().find(|k| k.id == id).and_then(|k| k.status);
            self.rand(&id, ouder, rand_voor(st));
        }
    }

    /// Loopt een expressie af en neemt alleen de doorslaggevende operanden mee.
    fn expressie(&mut self, ctx: &Context, e: &Value, y: Option<&Value>, ouder: &str) {
        if soort(e) != "operation" {
            self.operand(ctx, e, ouder);
            return;
        }
        let w = resultaat(e);
        let kids = kinderen(e);
        let y_lijst = |sleutel: &str| -> Vec<Value> {
            y.and_then(|y| y.get(sleutel))
                .and_then(Value::as_array)
                .cloned()
                .unwrap_or_default()
        };
        match naam(e) {
            "AND" | "OR" => {
                let doorslag = if naam(e) == "AND" { Value::Bool(false) } else { Value::Bool(true) };
                let beslissend: Vec<&Value> = if w == doorslag {
                    kids.iter().filter(|k| resultaat(k) == doorslag).collect()
                } else {
                    kids.iter().collect()
                };
                // Koppel elk trace-kind aan zijn eigen YAML-operand, ook als twee
                // operanden dezelfde operatie hebben; elke operand telt één keer.
                let yk = [y_lijst("conditions"), y_lijst("values")].concat();
                let mut gebruikt = vec![false; yk.len()];
                let paren: Vec<(&Value, Option<Value>)> = kids.iter().map(|k| (k, zoek_yaml(k, &yk, &mut gebruikt))).collect();
                for (k, yy) in paren {
                    if beslissend.iter().any(|b| std::ptr::eq(*b, k)) {
                        self.expressie(ctx, k, yy.as_ref(), ouder);
                    }
                }
            }
            "NOT" => {
                if let Some(k) = kids.first() {
                    let yy = y.and_then(|y| y.get("value")).cloned();
                    self.expressie(ctx, k, yy.as_ref(), ouder);
                }
            }
            "IF" => {
                let cases = y_lijst("cases");
                let mut gekozen = None;
                for (i, k) in kids.iter().enumerate() {
                    let n = naam(k);
                    if let Some(idx) = n.strip_prefix("CASE_").and_then(|x| x.parse::<usize>().ok()) {
                        if resultaat(k) == Value::Bool(true) {
                            gekozen = Some((idx, i));
                        }
                    }
                }
                match gekozen {
                    Some((idx, i)) => {
                        let case = cases.get(idx);
                        if let Some(when) = kids[i].get("children").and_then(Value::as_array).and_then(|c| c.first()) {
                            self.expressie(ctx, when, case.and_then(|c| c.get("when")), ouder);
                        }
                        if let Some(then) = kids.get(i + 1).filter(|k| naam(k) == "THEN") {
                            for t in kinderen(then) {
                                self.expressie(ctx, t, case.and_then(|c| c.get("then")), ouder);
                            }
                        }
                    }
                    None => {
                        for k in kids {
                            let n = naam(k);
                            let yy = if let Some(idx) = n.strip_prefix("CASE_").and_then(|x| x.parse::<usize>().ok()) {
                                cases.get(idx).and_then(|c| c.get("when")).cloned()
                            } else if n == "DEFAULT" {
                                y.and_then(|y| y.get("default")).cloned()
                            } else {
                                None
                            };
                            for c in kinderen(k) {
                                self.expressie(ctx, c, yy.as_ref(), ouder);
                            }
                        }
                    }
                }
            }
            op if operator(op).is_some() => {
                // Een vergelijking binnen een grotere expressie wordt een eigen regel.
                let id = format!("{ouder}/{}", e.get("node_id").and_then(Value::as_str).unwrap_or(op));
                let verg = y.map(|y| self.vergelijking(e, y));
                let st = status(&w);
                self.voeg(Knoop {
                    id: id.clone(),
                    soort: "rule",
                    naam: verg.as_ref().map(beschrijf).unwrap_or_else(|| op.to_string()),
                    omschrijving: None,
                    status: st,
                    ontbreekt: if st == Some("onbekend") { ontbreekt(&w) } else { vec![] },
                    waarde: w.clone(),
                    eenheid: None,
                    vergelijking: verg,
                    bron: None,
                    vindplaats: None,
                });
                for k in kids {
                    self.operand(ctx, k, &id);
                }
                self.rand(&id, ouder, rand_voor(st));
            }
            _ => {
                // Rekenkundige operaties en datums: de operanden voeden de ouder rechtstreeks.
                for k in kids {
                    self.operand(ctx, k, ouder);
                }
            }
        }
    }
}

/// De `$namen` waar een YAML-operatie direct naar verwijst.
fn verwijzingen(y: &Value) -> Vec<String> {
    let mut uit = Vec::new();
    if let Value::Object(o) = y {
        for (sleutel, v) in o {
            if sleutel == "operation" {
                continue;
            }
            let lijst: Vec<&Value> = match v {
                Value::Array(a) => a.iter().collect(),
                x => vec![x],
            };
            for x in lijst {
                if let Some(n) = x.as_str().and_then(|s| s.strip_prefix('$')) {
                    uit.push(n.to_string());
                }
            }
        }
    }
    uit
}

/// Zoekt bij een trace-kind de YAML-operand met dezelfde operatie waarvan de
/// verwijzingen in de trace terugkomen; bij gelijke kandidaten de eerste die
/// nog niet gebruikt is.
fn zoek_yaml(k: &Value, kandidaten: &[Value], gebruikt: &mut [bool]) -> Option<Value> {
    if soort(k) != "operation" {
        return None;
    }
    let namen: Vec<&str> = kinderen(k).iter().filter(|c| soort(c) == "resolve").map(naam).collect();
    let past = |c: &Value| c.get("operation").and_then(Value::as_str) == Some(naam(k));
    let idx = (0..kandidaten.len())
        .find(|&i| !gebruikt[i] && past(&kandidaten[i]) && verwijzingen(&kandidaten[i]).iter().all(|n| namen.contains(&n.as_str())))
        .or_else(|| (0..kandidaten.len()).find(|&i| !gebruikt[i] && past(&kandidaten[i])))?;
    gebruikt[idx] = true;
    Some(kandidaten[idx].clone())
}

fn beschrijf(v: &Vergelijking) -> String {
    let deel = |o: &Operand| match (&o.naam, o.letterlijk) {
        (Some(n), _) => n.clone(),
        (None, true) => match &o.waarde {
            Value::Null => "leeg".into(),
            w => w.to_string(),
        },
        (None, false) => "berekening".into(),
    };
    v.operanden.iter().map(deel).collect::<Vec<_>>().join(&format!(" {} ", v.operator))
}

fn lid_uit_toelichting(a: &Value) -> Option<String> {
    let t = a.get("explanation").and_then(Value::as_str)?;
    let rest = t.strip_prefix("Lid ")?;
    let lid: String = rest.chars().take_while(|c| c.is_ascii_alphanumeric()).collect();
    (!lid.is_empty()).then_some(lid)
}

/// Bouwt de beslisgraaf voor `output` (en de bedragen in `outputs`) uit de trace.
pub fn beslisgraaf(
    wetboek: &Wetboek,
    wet: &str,
    output: &str,
    peildatum: &str,
    outputs: &Map<String, Value>,
    trace: Option<&Value>,
) -> Graaf {
    let Some(wortel) = trace else { return Graaf::default() };
    let ctx = Context::van(wet, wortel);
    let mut b = Bouwer {
        wetboek,
        peildatum,
        knopen: vec![],
        randen: vec![],
        gezien: BTreeMap::new(),
    };
    let mut beslissingen = Vec::new();
    let mut volgorde: Vec<&str> = vec![output];
    volgorde.extend(outputs.keys().map(String::as_str).filter(|k| *k != output));
    for naam in volgorde {
        if let Some(actie) = ctx.acties.get(naam).copied() {
            beslissingen.push(b.actie(&ctx, actie, true));
        }
    }
    b.randen.sort();
    let mut markeringen = Vec::new();
    verzamel_markeringen(wortel, &mut markeringen);
    // Minimaal: alleen markeringen van artikelen waar de uitkomst op rust.
    let artikelen: Vec<(&str, Option<&str>)> = b
        .knopen
        .iter()
        .filter_map(|k| k.vindplaats.as_ref())
        .map(|v| (v.wet.as_str(), v.artikel.as_deref()))
        .collect();
    markeringen.retain(|m| artikelen.contains(&(m.vindplaats.wet.as_str(), m.vindplaats.artikel.as_deref())));
    Graaf {
        beslissingen,
        knopen: b.knopen,
        randen: b.randen,
        markeringen,
    }
}

/// Alle markeringen in de trace, ook die in een andere wet waar de uitkomst op rust.
fn verzamel_markeringen(n: &Value, uit: &mut Vec<Markering>) {
    if let Some(onderwerp) = naam(n).strip_prefix("marking:") {
        let a = n.get("anchor").cloned().unwrap_or(Value::Null);
        let toelichting = n
            .get("message")
            .and_then(Value::as_str)
            .and_then(|m| m.split_once(" — ").map(|(_, t)| t))
            .map(|t| t.split(" (needs a new shape").next().unwrap_or(t).trim().to_string());
        let vindplaats = Vindplaats {
            wet: tekst(&a, "law_id").unwrap_or_default(),
            wetnaam: tekst(&a, "law"),
            artikel: tekst(&a, "article"),
            lid: tekst(&a, "paragraph"),
            url: tekst(&a, "url"),
            geldig_vanaf: tekst(&a, "valid_from"),
            toelichting: None,
        };
        let m = Markering {
            onderwerp: onderwerp.trim().to_string(),
            toelichting,
            vindplaats,
        };
        if !uit
            .iter()
            .any(|x| x.onderwerp == m.onderwerp && x.vindplaats.wet == m.vindplaats.wet && x.vindplaats.artikel == m.vindplaats.artikel)
        {
            uit.push(m);
        }
    }
    for k in kinderen(n) {
        verzamel_markeringen(k, uit);
    }
}
