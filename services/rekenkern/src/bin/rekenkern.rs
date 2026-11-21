//! De kern op de commandoregel, voor tests en metingen. Rekent lokaal; er gaat niets over het netwerk.
//!
//!   rekenkern bereken   <wetten.json> <verzoek.json>
//!   rekenkern orienteer <wetten.json> <keuzes.json>
//!   rekenkern wetten    <corpus-regulation-map> <wetten.json>

use da_rekenkern::kern::Kern;
use std::collections::BTreeMap;
use std::path::Path;
use std::process::ExitCode;

fn lees_map(p: &Path, wetten: &mut BTreeMap<String, String>, wortel: &Path) -> std::io::Result<()> {
    for e in std::fs::read_dir(p)? {
        let pad = e?.path();
        if pad.is_dir() {
            if pad.file_name().is_some_and(|n| n == "scenarios") {
                continue;
            }
            lees_map(&pad, wetten, wortel)?;
        } else if pad.extension().is_some_and(|x| x == "yaml") && pad.file_name().is_some_and(|n| n != "status.yaml") {
            let rel = pad.strip_prefix(wortel).unwrap_or(&pad).to_string_lossy().to_string();
            wetten.insert(rel, std::fs::read_to_string(&pad)?);
        }
    }
    Ok(())
}

fn main() -> ExitCode {
    let a: Vec<String> = std::env::args().collect();
    if a.len() != 4 {
        eprintln!("gebruik: rekenkern bereken|orienteer <wetten.json> <invoer.json> | rekenkern wetten <map> <uit.json>");
        return ExitCode::from(2);
    }
    let resultaat = (|| -> Result<String, String> {
        if a[1] == "wetten" {
            let mut w = BTreeMap::new();
            let wortel = Path::new(&a[2]);
            lees_map(wortel, &mut w, wortel.parent().unwrap_or(wortel)).map_err(|e| e.to_string())?;
            std::fs::write(
                &a[3],
                serde_json::to_string(&serde_json::json!({ "wetten": w })).map_err(|e| e.to_string())?,
            )
            .map_err(|e| e.to_string())?;
            return Ok(format!("{} wetversies", w.len()));
        }
        let kern = Kern::laad_json(&std::fs::read_to_string(&a[2]).map_err(|e| e.to_string())?).map_err(|e| e.to_string())?;
        let invoer = std::fs::read_to_string(&a[3]).map_err(|e| e.to_string())?;
        let json = match a[1].as_str() {
            "bereken" => serde_json::to_string_pretty(&kern.bereken_json(&invoer).map_err(|e| e.to_string())?),
            "orienteer" => serde_json::to_string_pretty(&kern.orienteer_json(&invoer).map_err(|e| e.to_string())?),
            o => return Err(format!("onbekend commando {o}")),
        };
        json.map_err(|e| e.to_string())
    })();
    match resultaat {
        Ok(s) => {
            println!("{s}");
            ExitCode::SUCCESS
        }
        Err(e) => {
            eprintln!("{e}");
            ExitCode::FAILURE
        }
    }
}
