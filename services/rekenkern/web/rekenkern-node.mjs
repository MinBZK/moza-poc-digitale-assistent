// De rekenkern in Node, voor tests en scripts van een afnemer. Dezelfde
// bestanden en functies als worker.js in de browser, en dezelfde toets van
// de bundel tegen manifest.json.
//
//   import { laad } from "./rekenkern-node.mjs";
//   const kern = await laad();             // map van deze module
//   kern.orienteer({ doelgroepen: ["bijstand"], uren: 32, loonwaarde: 60, uurloon: 1499 });
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const sha256 = (buffer) => createHash("sha256").update(buffer).digest("hex");

/** Geeft het `ok`-antwoord terug of gooit met de foutcode van de kern. */
const uitpakken = (json, sleutel) => {
  const a = JSON.parse(json);
  if (!a.ok) {
    const fout = new Error(`${a.fout.code}: ${a.fout.bericht}`);
    fout.code = a.fout.code;
    throw fout;
  }
  return a[sleutel];
};

export const laad = async (map = fileURLToPath(new URL("./", import.meta.url))) => {
  const manifest = JSON.parse(readFileSync(map + "/manifest.json", "utf8"));
  const wasm = readFileSync(map + "/pkg/da_rekenkern_bg.wasm");
  const wetten = readFileSync(map + "/wetten.json");
  for (const [naam, buffer] of [["pkg/da_rekenkern_bg.wasm", wasm], ["wetten.json", wetten]])
    if (sha256(buffer) !== manifest.bestanden[naam])
      throw new Error(`REKENKERN_BUNDEL_ONGELDIG: ${naam} past niet bij manifest.json`);
  const kern = await import(map + "/pkg/da_rekenkern.js");
  kern.initSync({ module: wasm });
  const rekenkern = new kern.Rekenkern(wetten.toString("utf8"));
  return {
    manifest,
    bereken: (verzoek) => uitpakken(rekenkern.bereken(JSON.stringify(verzoek)), "antwoord"),
    orienteer: (keuzes) => uitpakken(rekenkern.orienteer(JSON.stringify(keuzes)), "orientatie"),
    kiesDoelgroep: (huidig, waarde, aan) => uitpakken(kern.kiesDoelgroep(JSON.stringify(huidig), waarde, aan), "doelgroepen"),
    balans: (uitkomsten, kosten) => uitpakken(kern.balans(JSON.stringify(uitkomsten), kosten), "balans"),
    doelgroepen: () => uitpakken(kern.doelgroepen(), "doelgroepen"),
    allowlist: () => JSON.parse(kern.allowlist()),
    geweigerd: () => uitpakken(rekenkern.geweigerd(), "geweigerd"),
  };
};
