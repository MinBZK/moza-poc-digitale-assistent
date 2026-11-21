// Web Worker met de rekenkern van de Digitale assistent (WASM). Laadt één keer
// de gepinde wetversies uit deze map, toetst ze aan manifest.json, en rekent
// daarna op verzoek. Feiten en uitkomsten blijven in de browser: deze worker
// doet geen enkel netwerkverzoek buiten de eigen bundel.
//
// Verzoek:  { id, soort: "bereken", verzoek }   (docs/rekenkern/contract.md)
//           { id, soort: "orienteer", keuzes }
//           { id, soort: "kiesDoelgroep", huidig, waarde, aan }
//           { id, soort: "balans", uitkomsten, kosten }
//           { id, soort: "doelgroepen" | "allowlist" | "manifest" }
// Antwoord: { id, ok: true, ...antwoord, ms } of { id, ok: false, fout: { code, bericht } }
import init, * as kern from "./pkg/da_rekenkern.js";

const BASIS = new URL("./", import.meta.url);

const haal = async (naam) => {
  const antwoord = await fetch(new URL(naam, BASIS));
  if (!antwoord.ok) throw new Error(`${naam}: HTTP ${antwoord.status}`);
  return antwoord;
};

const sha256 = async (buffer) =>
  [...new Uint8Array(await crypto.subtle.digest("SHA-256", buffer))]
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");

const klaar = (async () => {
  const manifest = await (await haal("manifest.json")).json();
  const [wasm, wetten] = await Promise.all([
    haal("pkg/da_rekenkern_bg.wasm").then((r) => r.arrayBuffer()),
    haal("wetten.json").then((r) => r.arrayBuffer()),
  ]);
  for (const [naam, buffer] of [["pkg/da_rekenkern_bg.wasm", wasm], ["wetten.json", wetten]]) {
    if ((await sha256(buffer)) !== manifest.bestanden[naam])
      throw new Error(`REKENKERN_BUNDEL_ONGELDIG: ${naam} past niet bij manifest.json`);
  }
  await init({ module_or_path: wasm });
  return { manifest, rekenkern: new kern.Rekenkern(new TextDecoder().decode(wetten)) };
})();

const voer = ({ rekenkern, manifest }, d) => {
  switch (d.soort) {
    case "bereken":
      return rekenkern.bereken(JSON.stringify(d.verzoek));
    case "orienteer":
      return rekenkern.orienteer(JSON.stringify(d.keuzes));
    case "kiesDoelgroep":
      return kern.kiesDoelgroep(JSON.stringify(d.huidig), d.waarde, d.aan);
    case "balans":
      return kern.balans(JSON.stringify(d.uitkomsten), d.kosten);
    case "doelgroepen":
      return kern.doelgroepen();
    case "allowlist":
      return kern.allowlist();
    case "manifest":
      return JSON.stringify({ ok: true, manifest });
    default:
      return JSON.stringify({ ok: false, fout: { code: "REKENKERN_VERZOEK_ONGELDIG", bericht: `onbekende soort ${d.soort}` } });
  }
};

self.onmessage = async ({ data }) => {
  const begin = performance.now();
  try {
    const antwoord = JSON.parse(voer(await klaar, data));
    self.postMessage({ id: data.id, ...antwoord, ms: Math.round(performance.now() - begin) });
  } catch (fout) {
    const bericht = String((fout && fout.message) || fout);
    const code = bericht.startsWith("REKENKERN_") ? bericht.split(":")[0] : "REKENKERN_BUNDEL_ONGELDIG";
    self.postMessage({ id: data.id, ok: false, fout: { code, bericht } });
  }
};
