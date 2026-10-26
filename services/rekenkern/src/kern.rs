//! De kern: wetten laden en een verzoek rekenen. Alleen de zeven uitkomsten
//! van de allowlist; elke andere `wet#output` wordt geweigerd voordat de
//! engine iets ziet. Er is geen netwerk en geen logging: feiten en uitkomsten
//! verlaten de kern alleen als antwoord aan de aanroeper.

use crate::aannemen::{invoer_voor, uitkomsten_uit, Keuzes, Outputs, Uitkomsten};
use crate::graaf::{beslisgraaf, Graaf};
use crate::uitleg::{uitleg, Uitleg};
use crate::wetboek::Wetboek;
use regelrecht_engine::trace::TraceDocument;
use regelrecht_engine::{LawExecutionService, TraceBuilder, Value};
use serde::{Deserialize, Serialize};
use serde_json::Map;
use std::collections::BTreeMap;

/// De uitkomsten die de kern rekent, met de outputs die erbij mogen.
/// Deze lijst is het contract (docs/rekenkern/contract.md); wie hem
/// uitbreidt, werkt ook het schema en de PDR bij.
pub const ALLOWLIST: [(&str, &str, &[&str]); 7] = [
    ("participatiewet", "heeft_recht_op_lks", &["hoogte_lks_eurocent_per_maand"]),
    (
        "wet_arbeidsongeschiktheidsvoorziening_jonggehandicapten",
        "heeft_recht_op_loondispensatie",
        &["aanspraak_beloning_per_uur_eurocent"],
    ),
    (
        "wet_tegemoetkomingen_loondomein",
        "heeft_recht_op_lkv",
        &["hoogte_lkv_per_jaar_eurocent", "categorie_lkv"],
    ),
    ("ziektewet", "heeft_recht_op_no_risk_polis", &["duur_no_risk_polis_jaren"]),
    ("participatiewet", "mag_proefplaatsing_aangaan", &[]),
    ("participatiewet", "heeft_aanspraak_op_begeleiding_op_de_werkplek", &[]),
    (
        "wet_werk_en_inkomen_naar_arbeidsvermogen",
        "mag_jobcoaching_toekennen",
        &["mag_werkplekaanpassing_toekennen"],
    ),
];

/// De datums waarop de kern rekent; een andere peildatum valt buiten de
/// gepinde wetversies en het contract.
pub const PEILDATUMS: [&str; 1] = ["2026-07-01"];

/// Een verzoek aan de kern: één uitkomst van één wet.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Verzoek {
    pub wet: String,
    pub output: String,
    pub peildatum: String,
    pub parameters: Map<String, serde_json::Value>,
    #[serde(default)]
    pub uitleggen: Vec<String>,
}

/// Het antwoord: de gevraagde outputs, de beslisgraaf en de uitleg zonder taalmodel.
#[derive(Debug, Clone, Serialize)]
pub struct Antwoord {
    pub wet: String,
    pub output: String,
    pub peildatum: String,
    pub outputs: Map<String, serde_json::Value>,
    pub graaf: Graaf,
    pub uitleg: Uitleg,
}

/// Fouten van de kern. De code is stabiel en staat in het contract; de
/// tekst is voor de ontwikkelaar, niet voor de ondernemer.
#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct Fout {
    pub code: &'static str,
    pub bericht: String,
}

impl Fout {
    fn nieuw(code: &'static str, bericht: impl Into<String>) -> Fout {
        Fout {
            code,
            bericht: bericht.into(),
        }
    }
}

impl std::fmt::Display for Fout {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}: {}", self.code, self.bericht)
    }
}

pub const VERZOEK_ONGELDIG: &str = "REKENKERN_VERZOEK_ONGELDIG";
pub const NIET_TOEGESTAAN: &str = "REKENKERN_NIET_TOEGESTAAN";
pub const PEILDATUM_ONBEKEND: &str = "REKENKERN_PEILDATUM_ONBEKEND";
pub const PARAMETER_ONGELDIG: &str = "REKENKERN_PARAMETER_ONGELDIG";
pub const WETTEN_ONGELDIG: &str = "REKENKERN_WETTEN_ONGELDIG";
pub const ENGINE: &str = "REKENKERN_ENGINE";

pub struct Kern {
    service: LawExecutionService,
    wetboek: Wetboek,
    /// Wetversies die de engine niet kon laden, met de reden.
    pub geweigerd: Vec<(String, String)>,
}

/// De gegevens van een bundel: wetbestand per pad.
#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Wetten {
    pub wetten: BTreeMap<String, String>,
}

impl Kern {
    pub fn laad(wetten: &BTreeMap<String, String>) -> Result<Kern, Fout> {
        if wetten.is_empty() {
            return Err(Fout::nieuw(WETTEN_ONGELDIG, "geen wetten"));
        }
        let mut service = LawExecutionService::new();
        let mut wetboek = Wetboek::default();
        let mut geweigerd = Vec::new();
        for (pad, yaml) in wetten {
            match service.load_law(yaml) {
                Ok(_) => wetboek.voeg(yaml),
                Err(e) => geweigerd.push((pad.clone(), e.to_string())),
            }
        }
        Ok(Kern {
            service,
            wetboek,
            geweigerd,
        })
    }

    pub fn laad_json(json: &str) -> Result<Kern, Fout> {
        let w: Wetten = serde_json::from_str(json).map_err(|e| Fout::nieuw(WETTEN_ONGELDIG, e.to_string()))?;
        Kern::laad(&w.wetten)
    }

    /// Toetst het verzoek aan de allowlist en rekent het.
    pub fn bereken(&self, v: &Verzoek) -> Result<Antwoord, Fout> {
        let toegestaan = ALLOWLIST
            .iter()
            .find(|(w, o, _)| *w == v.wet && *o == v.output)
            .ok_or_else(|| Fout::nieuw(NIET_TOEGESTAAN, format!("{}#{}", v.wet, v.output)))?;
        if let Some(extra) = v.uitleggen.iter().find(|u| !toegestaan.2.contains(&u.as_str())) {
            return Err(Fout::nieuw(
                NIET_TOEGESTAAN,
                format!("{}#{} bij {}#{}", v.wet, extra, v.wet, v.output),
            ));
        }
        if !PEILDATUMS.contains(&v.peildatum.as_str()) {
            return Err(Fout::nieuw(PEILDATUM_ONBEKEND, v.peildatum.clone()));
        }
        let mut parameters = BTreeMap::new();
        for (naam, waarde) in &v.parameters {
            let w: Value = serde_json::from_value(waarde.clone()).map_err(|e| Fout::nieuw(PARAMETER_ONGELDIG, format!("{naam}: {e}")))?;
            parameters.insert(naam.clone(), w);
        }
        let mut namen: Vec<&str> = vec![v.output.as_str()];
        namen.extend(v.uitleggen.iter().map(String::as_str));
        let r = self
            .service
            .evaluate_law_with_trace_builder(&v.wet, &namen, parameters, &v.peildatum, TraceBuilder::new_untimed())
            .map_err(|e| Fout::nieuw(ENGINE, e.to_string()))?;
        let mut outputs = Map::new();
        for naam in &namen {
            if let Some(w) = r.outputs.get(*naam) {
                outputs.insert(
                    (*naam).into(),
                    serde_json::to_value(w).map_err(|e| Fout::nieuw(ENGINE, e.to_string()))?,
                );
            }
        }
        let trace = r
            .trace
            .map(TraceDocument::new)
            .and_then(|t| serde_json::to_value(t).ok())
            .and_then(|t| t.get("root").cloned());
        let graaf = beslisgraaf(&self.wetboek, &v.wet, &v.output, &v.peildatum, &outputs, trace.as_ref());
        let uitleg = uitleg(&graaf);
        Ok(Antwoord {
            wet: v.wet.clone(),
            output: v.output.clone(),
            peildatum: v.peildatum.clone(),
            outputs,
            graaf,
            uitleg,
        })
    }

    pub fn bereken_json(&self, verzoek: &str) -> Result<Antwoord, Fout> {
        let v: Verzoek = serde_json::from_str(verzoek).map_err(|e| Fout::nieuw(VERZOEK_ONGELDIG, e.to_string()))?;
        self.bereken(&v)
    }
}

/// De oriëntatie van één set keuzes: elke aanroep die de keuzes nodig maken,
/// met per aanroep het antwoord van de kern, en wat een scherm toont.
#[derive(Debug, Clone, Serialize)]
pub struct Orientatie {
    pub keuzes: Keuzes,
    pub antwoorden: Vec<Antwoord>,
    pub uitkomsten: Uitkomsten,
}

impl Kern {
    pub fn orienteer(&self, keuzes: &Keuzes) -> Result<Orientatie, Fout> {
        let mut antwoorden = Vec::new();
        let mut uit: BTreeMap<String, Outputs> = BTreeMap::new();
        for i in invoer_voor(keuzes) {
            let a = self.bereken(&Verzoek {
                wet: i.wet,
                output: i.output,
                peildatum: i.peildatum,
                parameters: i.parameters,
                uitleggen: i.uitleggen,
            })?;
            uit.insert(format!("{}#{}", a.wet, a.output), a.outputs.clone());
            antwoorden.push(a);
        }
        Ok(Orientatie {
            keuzes: keuzes.clone(),
            uitkomsten: uitkomsten_uit(keuzes, &uit),
            antwoorden,
        })
    }

    pub fn orienteer_json(&self, keuzes: &str) -> Result<Orientatie, Fout> {
        let k: Keuzes = serde_json::from_str(keuzes).map_err(|e| Fout::nieuw(VERZOEK_ONGELDIG, e.to_string()))?;
        if k.uren <= 0.0 || k.uren > 168.0 || k.loonwaarde < 0.0 || k.loonwaarde > 100.0 || k.uurloon < 0 {
            return Err(Fout::nieuw(VERZOEK_ONGELDIG, "uren, loonwaarde of uurloon buiten bereik"));
        }
        if let Some(d) = k
            .doelgroepen
            .iter()
            .find(|d| !crate::aannemen::DOELGROEPEN.iter().any(|(id, _)| id == d))
        {
            return Err(Fout::nieuw(VERZOEK_ONGELDIG, format!("onbekende doelgroep {d}")));
        }
        self.orienteer(&k)
    }
}
