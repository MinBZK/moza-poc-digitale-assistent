//! Opzoeken in de geladen wetversies: de definitie van een actie, de
//! omschrijving en eenheid van een gegeven, de url van een artikel. De trace
//! van de engine noemt wat er gerekend is; de letterlijke drempels en de
//! omschrijvingen staan alleen in het model.

use serde_json::Value;
use std::collections::BTreeMap;

#[derive(Default)]
pub struct Wetboek {
    /// Per wet de versies, oplopend op `valid_from`.
    versies: BTreeMap<String, Vec<(String, Value)>>,
}

impl Wetboek {
    pub fn voeg(&mut self, yaml: &str) {
        let Ok(v) = serde_yaml_ng::from_str::<Value>(yaml) else { return };
        let (Some(id), Some(vanaf)) = (v.get("$id").and_then(Value::as_str), v.get("valid_from").and_then(Value::as_str)) else {
            return;
        };
        let lijst = self.versies.entry(id.to_string()).or_default();
        lijst.push((vanaf.to_string(), v));
        lijst.sort_by(|a, b| a.0.cmp(&b.0));
    }

    /// De versie die op de peildatum geldt: de laatste met `valid_from` op of vóór die datum.
    fn versie(&self, wet: &str, peildatum: &str) -> Option<&(String, Value)> {
        self.versies.get(wet)?.iter().rev().find(|(vanaf, _)| vanaf.as_str() <= peildatum)
    }

    fn artikelen<'a>(&'a self, wet: &str, peildatum: &str) -> impl Iterator<Item = &'a Value> {
        self.versie(wet, peildatum)
            .and_then(|(_, v)| v.get("articles"))
            .and_then(Value::as_array)
            .into_iter()
            .flatten()
    }

    fn uitvoeringen<'a>(&'a self, wet: &str, peildatum: &str) -> impl Iterator<Item = &'a Value> {
        self.artikelen(wet, peildatum)
            .filter_map(|a| a.get("machine_readable")?.get("execution"))
    }

    /// De actie die `output` berekent.
    pub fn actie(&self, wet: &str, output: &str, peildatum: &str) -> Option<Value> {
        self.uitvoeringen(wet, peildatum)
            .filter_map(|e| e.get("actions").and_then(Value::as_array))
            .flatten()
            .find(|a| a.get("output").and_then(Value::as_str) == Some(output))
            .cloned()
    }

    /// De declaratie van een parameter of output met deze naam.
    fn declaratie(&self, wet: &str, naam: &str, peildatum: &str) -> Option<&Value> {
        self.uitvoeringen(wet, peildatum).find_map(|e| {
            ["output", "parameters", "input"]
                .iter()
                .filter_map(|s| e.get(*s).and_then(Value::as_array))
                .flatten()
                .find(|d| d.get("name").and_then(Value::as_str) == Some(naam))
        })
    }

    pub fn omschrijving(&self, wet: &str, naam: &str, peildatum: &str) -> Option<String> {
        let d = self.declaratie(wet, naam, peildatum)?.get("description")?.as_str()?;
        Some(d.split_whitespace().collect::<Vec<_>>().join(" "))
    }

    pub fn eenheid(&self, wet: &str, naam: &str, peildatum: &str) -> Option<String> {
        self.declaratie(wet, naam, peildatum)?
            .get("type_spec")?
            .get("unit")?
            .as_str()
            .map(String::from)
    }

    pub fn naam(&self, wet: &str, peildatum: &str) -> Option<String> {
        self.versie(wet, peildatum)?.1.get("name")?.as_str().map(String::from)
    }

    pub fn geldig_vanaf(&self, wet: &str, peildatum: &str) -> Option<String> {
        self.versie(wet, peildatum).map(|(v, _)| v.clone())
    }

    pub fn artikel_url(&self, wet: &str, artikel: &str, peildatum: &str) -> Option<String> {
        self.artikelen(wet, peildatum)
            .find(|a| a.get("number").and_then(Value::as_str) == Some(artikel))
            .and_then(|a| a.get("url"))
            .and_then(Value::as_str)
            .map(String::from)
    }
}
