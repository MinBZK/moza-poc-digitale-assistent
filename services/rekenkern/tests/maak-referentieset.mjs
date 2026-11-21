// Legt de referentieset vast: elke combinatie van vraag 1, bij loonwaarde 60
// en 100 en uurloon € 14,99 en € 20,00 (32 uur), met de invoer zoals het
// portaal hem maakte (invoerVoor/feitenVoor uit _uitkomsten.ts) en de outputs
// van de portaalbundel (regelrecht-uitleg, corpus 42054d7d). Eenmalig gedraaid
// vanuit een checkout van moza-portaal; de uitkomst is de fixture.
//
// Gebruik: node maak-referentieset.mjs <moza-portaal> <uit.json>
import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

const [portaal, uit] = process.argv.slice(2).map((p) => resolve(p));
const MAP = `${portaal}/src/app/(public)/[personaId]/(portaal)/personeel/iemand-aannemen/`;
const U = await import(MAP + "_uitkomsten.ts");
const { bereken } = await import(`${portaal}/scripts/regelrecht-node.mjs`);
const basis = JSON.parse(readFileSync(MAP + "_basisfeiten.json", "utf8"));
const manifest = JSON.parse(readFileSync(`${portaal}/public/regelrecht/manifest.json`, "utf8"));

// Alle geldige antwoorden op vraag 1: elke deelverzameling, genormaliseerd zoals het scherm doet.
const opties = U.DOELGROEPEN.map(([id]) => id).filter((id) => id !== "geen");
const sets = new Map([["geen", ["geen"]]]);
for (let m = 1; m < 1 << opties.length; m++) {
  let d = [];
  opties.forEach((o, i) => {
    if (m & (1 << i)) d = U.kiesDoelgroep(d, o, true);
  });
  sets.set(d.join(","), d);
}

const gevallen = [];
for (const doelgroepen of sets.values())
  for (const loonwaarde of [60, 100])
    for (const uurloon of [1499, 2000]) {
      const keuzes = { doelgroepen, uren: 32, loonwaarde, uurloon };
      const invoer = U.invoerVoor(keuzes, basis);
      const outputs = {};
      const engine = {};
      for (const i of invoer) {
        const r = bereken(i).outputs;
        const namen = [i.output, ...(i.uitleggen ?? [])];
        outputs[`${i.wet}#${i.output}`] = Object.fromEntries(namen.filter((n) => n in r).map((n) => [n, r[n]]));
        engine[`${i.wet}:${i.output}`] = r;
      }
      // De parameters zijn de basis plus de feiten van de keuzes; de basis staat één keer bovenaan.
      const parameters = invoer[0]?.parameters ?? {};
      const feiten = Object.fromEntries(Object.entries(parameters).filter(([k, v]) => basis[k] !== v));
      gevallen.push({
        keuzes,
        feiten,
        aanroepen: invoer.map(({ wet, output, uitleggen }) => ({ wet, output, uitleggen: uitleggen ?? [] })),
        outputs,
        uitkomsten: U.uitkomstenUit(keuzes, engine),
      });
    }

writeFileSync(
  uit,
  JSON.stringify({ bron: { kern: "regelrecht-uitleg (moza-portaal public/regelrecht)", engine: { repo: "MinBZK/regelrecht", revisie: manifest.regelrecht }, corpus: manifest.corpus }, basis, gevallen }) + "\n",
);
console.log(`${gevallen.length} gevallen uit ${sets.size} antwoorden op vraag 1`);
