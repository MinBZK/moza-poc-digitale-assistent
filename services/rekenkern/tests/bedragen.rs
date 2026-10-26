//! De bekende bedragen bij 32 uur en het minimumloon, zoals de demo en de
//! scenario's van het corpus ze noemen. Vraagt `REKENKERN_WETTEN=<wetten.json>`.

use da_rekenkern::aannemen::Keuzes;
use da_rekenkern::kern::Kern;

fn kern() -> Option<Kern> {
    let pad = std::env::var("REKENKERN_WETTEN").ok()?;
    Some(Kern::laad_json(&std::fs::read_to_string(pad).expect("wetten leesbaar")).expect("wetten laden"))
}

fn keuzes(doelgroepen: &[&str], loonwaarde: f64) -> Keuzes {
    Keuzes {
        doelgroepen: doelgroepen.iter().map(|d| (*d).into()).collect(),
        uren: 32.0,
        loonwaarde,
        uurloon: 1499,
    }
}

fn output(kern: &Kern, k: &Keuzes, uitkomst: &str, naam: &str) -> serde_json::Value {
    let o = kern.orienteer(k).expect("oriëntatie");
    let a = o
        .antwoorden
        .iter()
        .find(|a| format!("{}#{}", a.wet, a.output) == uitkomst)
        .unwrap_or_else(|| panic!("{uitkomst} niet gerekend"));
    a.outputs[naam].clone()
}

#[test]
fn loonkostensubsidie_bij_bijstand_en_loonwaarde_60() {
    let Some(kern) = kern() else { return };
    let k = keuzes(&["bijstand"], 60.0);
    assert_eq!(output(&kern, &k, "participatiewet#heeft_recht_op_lks", "heeft_recht_op_lks"), true);
    let cent = output(&kern, &k, "participatiewet#heeft_recht_op_lks", "hoogte_lks_eurocent_per_maand")
        .as_f64()
        .expect("bedrag");
    assert!((cent - 89740.8).abs() < 1e-6, "{cent}");
    let o = kern.orienteer(&k).expect("oriëntatie");
    let a = &o.antwoorden[0];
    assert!(
        a.uitleg.kort.iter().any(|z| z.contains("€ 897,41 per maand")),
        "{:?}",
        a.uitleg.kort
    );
}

#[test]
fn loonkostenvoordeel_banenafspraak_en_arbeidsgehandicapte() {
    let Some(kern) = kern() else { return };
    let lkv = "wet_tegemoetkomingen_loondomein#heeft_recht_op_lkv";
    let register = keuzes(&["register"], 60.0);
    assert_eq!(
        output(&kern, &register, lkv, "hoogte_lkv_per_jaar_eurocent").as_f64(),
        Some(168064.0)
    );
    assert_eq!(output(&kern, &register, lkv, "categorie_lkv"), "banenafspraak");
    let wia = keuzes(&["wia"], 60.0);
    assert_eq!(output(&kern, &wia, lkv, "hoogte_lkv_per_jaar_eurocent").as_f64(), Some(507520.0));
    assert_eq!(output(&kern, &wia, lkv, "categorie_lkv"), "arbeidsgehandicapte_werknemer");
}

#[test]
fn loondispensatie_bij_wajong_en_loonwaarde_60() {
    let Some(kern) = kern() else { return };
    let k = keuzes(&["register", "wajong"], 60.0);
    let ld = "wet_arbeidsongeschiktheidsvoorziening_jonggehandicapten#heeft_recht_op_loondispensatie";
    assert_eq!(output(&kern, &k, ld, "heeft_recht_op_loondispensatie"), true);
    let cent = output(&kern, &k, ld, "aanspraak_beloning_per_uur_eurocent")
        .as_f64()
        .expect("bedrag");
    assert!((cent - 899.4).abs() < 1e-6, "{cent}");
}
