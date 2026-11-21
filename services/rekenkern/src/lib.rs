//! Rekenkern van de Digitale assistent. Draait in de browser van de
//! afnemer (WASM) en native voor tests; feiten en uitkomsten verlaten de kern
//! alleen als antwoord aan de aanroeper. Zie docs/rekenkern/contract.md.

pub mod aannemen;
pub mod graaf;
pub mod kern;
pub mod uitleg;
#[cfg(feature = "wasm")]
pub mod wasm;
pub mod wetboek;

pub fn versie() -> &'static str {
    env!("CARGO_PKG_VERSION")
}
