// De gebouwde bundel in Node, zoals een afnemer hem laadt (rekenkern-node.mjs).
// Overgenomen uit moza-portaal (scripts/iemand-aannemen-uitkomsten.test.mjs):
// de tests van vraag 1, de uitkomsten per geval, het voorbehoud, de aanroepen
// en de balans. De tests van route, schermen en opslag blijven in het portaal.
//
// Gebruik: node --test services/rekenkern/tests/bundel.test.mjs
//          (REKENKERN_BUNDEL=<map> om een andere bundel dan dist/rekenkern-<versie> te testen)
import { test } from "node:test";
import assert from "node:assert/strict";
import { cpSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const HIER = fileURLToPath(new URL("./", import.meta.url));
const versie = readFileSync(HIER + "../Cargo.toml", "utf8").match(/^version = "([^"]+)"/m)[1];
const BUNDEL = process.env.REKENKERN_BUNDEL ?? join(HIER, `../../../dist/rekenkern-${versie}`);
const { laad } = await import(join(BUNDEL, "rekenkern-node.mjs"));
const kern = await laad(BUNDEL);

const referentie = JSON.parse(readFileSync(HIER + "fixtures/referentieset.json", "utf8"));
const verschillen = JSON.parse(readFileSync(HIER + "fixtures/verwachte-verschillen.json", "utf8"));

const reken = (doelgroepen, loonwaarde, uren = 32, uurloon = 1499) =>
  kern.orienteer({ doelgroepen, uren, loonwaarde, uurloon }).uitkomsten;
const regel = (u, id) => u.regels.find((r) => r.id === id);
const overig = (u, id) => u.overige.find((o) => o.id === id);
const LKS_GEMEENTE_60_JAAR = Math.round(89740.8 * 12);

test("bundel: manifest noemt engine, corpus en een hash per bestand", () => {
  const m = kern.manifest;
  assert.equal(m.engine.repo, "MinBZK/regelrecht");
  assert.match(m.engine.revisie, /^[0-9a-f]{40}$/);
  assert.equal(m.corpus.repo, "MinBZK/regelrecht-corpus-FCV");
  assert.match(m.corpus.revisie, /^[0-9a-f]{40}$/);
  for (const naam of ["pkg/da_rekenkern_bg.wasm", "pkg/da_rekenkern.js", "wetten.json", "worker.js"])
    assert.match(m.bestanden[naam], /^[0-9a-f]{64}$/, naam);
  assert.deepEqual(kern.geweigerd(), []);
});

test("bundel: een gewijzigd wetbestand wordt geweigerd", async () => {
  const kopie = mkdtempSync(join(tmpdir(), "rekenkern-"));
  cpSync(BUNDEL, kopie, { recursive: true });
  const wetten = JSON.parse(readFileSync(join(kopie, "wetten.json"), "utf8"));
  const eerste = Object.keys(wetten.wetten)[0];
  wetten.wetten[eerste] += "\n# gewijzigd\n";
  writeFileSync(join(kopie, "wetten.json"), JSON.stringify(wetten));
  await assert.rejects(laad(kopie), /REKENKERN_BUNDEL_ONGELDIG: wetten.json/);
});

test("contract: buiten de allowlist wordt geweigerd", () => {
  const verzoek = { wet: "participatiewet", output: "heeft_recht_op_lks", peildatum: "2026-07-01", parameters: {} };
  assert.throws(() => kern.bereken({ ...verzoek, output: "is_uitgesloten_lid_3" }), { code: "REKENKERN_NIET_TOEGESTAAN" });
  assert.throws(() => kern.bereken({ ...verzoek, uitleggen: ["hoogte_lkv_per_jaar_eurocent"] }), { code: "REKENKERN_NIET_TOEGESTAAN" });
  assert.throws(() => kern.bereken({ ...verzoek, peildatum: "2025-01-01" }), { code: "REKENKERN_PEILDATUM_ONBEKEND" });
  assert.throws(() => kern.bereken({ ...verzoek, extra: 1 }), { code: "REKENKERN_VERZOEK_ONGELDIG" });
  assert.throws(() => kern.orienteer({ doelgroepen: ["onbekend"], uren: 32, loonwaarde: 60, uurloon: 1499 }), { code: "REKENKERN_VERZOEK_ONGELDIG" });
  assert.equal(kern.allowlist().allowlist.length, 7);
});

test("referentieset: dezelfde outputs als de portaalbundel, op de verwachte verschillen na", () => {
  const onverwacht = [];
  for (const g of referentie.gevallen) {
    const o = kern.orienteer(g.keuzes);
    assert.deepEqual(o.antwoorden.map((a) => ({ wet: a.wet, output: a.output })), g.aanroepen.map(({ wet, output }) => ({ wet, output })));
    for (const a of o.antwoorden)
      for (const [naam, oud] of Object.entries(g.outputs[`${a.wet}#${a.output}`])) {
        const nieuw = a.outputs[naam];
        const gelijk = typeof oud === "number" ? Math.abs(nieuw - oud) < 1e-3 : JSON.stringify(nieuw) === JSON.stringify(oud);
        const verwacht = verschillen.outputs.some((v) => v.uitkomst === `${a.wet}#${a.output}` && v.output === naam);
        if (!gelijk && !verwacht) onverwacht.push(`${g.keuzes.doelgroepen} ${a.output}.${naam}: ${JSON.stringify(oud)} → ${JSON.stringify(nieuw)}`);
      }
    const eigen = structuredClone(o.uitkomsten);
    for (const r of eigen.regels) delete r.voorbehoud;
    assert.deepEqual(eigen, g.uitkomsten, JSON.stringify(g.keuzes));
  }
  assert.deepEqual(onverwacht, []);
});

test("bedragen: loonkostensubsidie € 897,41 per maand bij bijstand en loonwaarde 60", () => {
  const o = kern.orienteer({ doelgroepen: ["bijstand"], uren: 32, loonwaarde: 60, uurloon: 1499 });
  const lks = o.antwoorden.find((a) => a.output === "heeft_recht_op_lks");
  assert.ok(Math.abs(lks.outputs.hoogte_lks_eurocent_per_maand - 89740.8) < 1e-6);
  assert.ok(lks.uitleg.kort.includes("Hoogte van de loonkostensubsidie: € 897,41 per maand."));
});

test("bedragen: loonkostenvoordeel € 1.680,64 (banenafspraak) en € 5.075,20 (arbeidsgehandicapte)", () => {
  assert.equal(regel(reken(["register"], 60), "lkv").bedragPerJaar, 168064);
  assert.equal(regel(reken(["wia"], 60), "lkv").bedragPerJaar, 507520);
});

test("bedragen: loondispensatie, aanspraak € 8,99 per uur bij Wajong en loonwaarde 60", () => {
  assert.equal(regel(reken(["register", "wajong"], 60), "ld").aanspraakPerUur, 899.4);
});

test("graaf: elke beslissing bestaat, elke rand wijst naar bestaande knopen, regels hebben een vindplaats", () => {
  for (const keuzes of [["bijstand"], ["register", "wajong"], ["wia"], ["beschut"]]) {
    for (const a of kern.orienteer({ doelgroepen: keuzes, uren: 32, loonwaarde: 60, uurloon: 1499 }).antwoorden) {
      const ids = new Set(a.graaf.knopen.map((k) => k.id));
      assert.ok(a.graaf.beslissingen.length > 0 && a.graaf.beslissingen.every((b) => ids.has(b)), a.output);
      for (const r of a.graaf.randen) assert.ok(ids.has(r.van) && ids.has(r.naar), JSON.stringify(r));
      const soorten = new Set(a.graaf.randen.map((r) => r.soort));
      for (const s of soorten) assert.ok(["has_fact", "satisfied", "failed", "unknown", "used_in", "based_on"].includes(s), s);
      const metGrond = new Set(a.graaf.randen.filter((r) => r.soort === "based_on").map((r) => r.van));
      for (const id of a.graaf.beslissingen) assert.ok(metGrond.has(id), `${id} zonder vindplaats`);
      assert.ok(a.uitleg.kort.length === a.graaf.beslissingen.length);
    }
  }
});

test("graaf: bij een AND die niet slaagt telt alleen wat niet slaagde", () => {
  // Register alleen: geen bijstand, dus de loonkostensubsidie wordt niet gerekend; LKV wel.
  const o = kern.orienteer({ doelgroepen: ["beschut"], uren: 32, loonwaarde: 60, uurloon: 1499 });
  const lkv = o.antwoorden.find((a) => a.output === "heeft_recht_op_lkv");
  const beslissing = lkv.graaf.knopen.find((k) => k.id === lkv.graaf.beslissingen[0]);
  assert.equal(beslissing.status, "nee");
  const naar = lkv.graaf.randen.filter((r) => r.naar === beslissing.id && r.soort !== "based_on");
  assert.ok(naar.length > 0);
  assert.ok(naar.every((r) => r.soort === "failed"), JSON.stringify(naar));
});

test("vraag 1: Wajong vinkt het register aan", () => {
  assert.deepEqual(kern.kiesDoelgroep([], "wajong", true), ["register", "wajong"]);
});

test("vraag 1: beschut werk haalt register en Wajong weg", () => {
  assert.deepEqual(kern.kiesDoelgroep(["register", "wajong"], "beschut", true), ["beschut"]);
});

test("vraag 1: register haalt beschut werk weg", () => {
  assert.deepEqual(kern.kiesDoelgroep(["beschut", "bijstand"], "register", true), ["register", "bijstand"]);
});

test("vraag 1: geen van deze sluit de rest uit", () => {
  assert.deepEqual(kern.kiesDoelgroep(["register", "wia"], "geen", true), ["geen"]);
});

test("vraag 1: zeven opties, WIA zonder WAO", () => {
  const d = kern.doelgroepen();
  assert.deepEqual(d.map((x) => x.id), ["register", "wajong", "wia", "bijstand", "wsw", "beschut", "geen"]);
  assert.equal(d.find((x) => x.id === "wia").tekst, "Iemand met een WIA-uitkering");
});

test("gemeente (bijstand, 60)", () => {
  const u = reken(["bijstand"], 60);
  assert.equal(regel(u, "lks").bedragPerJaar, LKS_GEMEENTE_60_JAAR);
  assert.equal(regel(u, "lks").aanname, "lks_lid4");
  assert.equal(regel(u, "lkv").bedragPerJaar, 168064);
  assert.equal(regel(u, "lkv").categorie, "banenafspraak");
  assert.equal(regel(u, "ld"), undefined);
  assert.equal(overig(u, "nrp").geldt, true);
  assert.equal(overig(u, "nrp").duurJaren, -1);
  assert.equal(overig(u, "pp_pwet").geldt, true);
  assert.equal(overig(u, "begeleiding").geldt, true);
});

test("register op 100 procent: loonkostenvoordeel blijft", () => {
  const u = reken(["register"], 100);
  assert.equal(regel(u, "lks"), undefined);
  assert.equal(regel(u, "lkv").bedragPerJaar, 168064);
  assert.equal(overig(u, "nrp").geldt, true);
});

test("register op 60 procent: geen loonkostensubsidie zonder gemeente", () => {
  const u = reken(["register"], 60);
  assert.equal(regel(u, "lks"), undefined);
  assert.equal(regel(u, "lkv").bedragPerJaar, 168064);
});

test("Wajong 70 procent", () => {
  const u = reken(["register", "wajong"], 70);
  const ld = regel(u, "ld");
  assert.equal(ld.aanspraakPerUur, 1049.3);
  assert.equal(ld.bedragPerJaar, Math.round((1499 - 1049.3) * 32 * 52 * 1.08 * 1.2));
  assert.equal(regel(u, "lkv").bedragPerJaar, 168064);
  assert.equal(regel(u, "lks"), undefined);
  assert.equal(overig(u, "nrp").geldt, true);
  assert.equal(overig(u, "nrp").duurJaren, -1);
  assert.equal(overig(u, "vz_wajong").geldt, true);
  assert.equal(overig(u, "vz_wia").geldt, false);
});

test("Wajong 80 procent: geen loondispensatie", () => {
  assert.equal(regel(reken(["register", "wajong"], 80), "ld"), undefined);
});

test("WIA: loonkostenvoordeel arbeidsgehandicapte, no-riskpolis vijf jaar", () => {
  const u = reken(["wia"], 100);
  assert.equal(regel(u, "lkv").bedragPerJaar, 507520);
  assert.equal(regel(u, "lkv").categorie, "arbeidsgehandicapte_werknemer");
  assert.equal(regel(u, "lkv").aanname, "wia_nieuw");
  assert.equal(overig(u, "nrp").geldt, true);
  assert.equal(overig(u, "nrp").duurJaren, 5);
  assert.equal(overig(u, "vz_wia").geldt, true);
  assert.equal(regel(u, "lks"), undefined);
});

test("beschut werk: geen loonkostenvoordeel, wel no-riskpolis", () => {
  const u = reken(["beschut"], 60);
  assert.equal(regel(u, "lks"), undefined);
  assert.equal(regel(u, "lkv"), undefined);
  assert.equal(overig(u, "nrp").geldt, true);
  assert.equal(overig(u, "nrp").duurJaren, -1);
  assert.ok(u.aannames.includes("beschut_lks"));
});

test("beschut werk + bijstand: loonkostensubsidie, geen loonkostenvoordeel", () => {
  const u = reken(["bijstand", "beschut"], 60);
  assert.equal(regel(u, "lks").bedragPerJaar, LKS_GEMEENTE_60_JAAR);
  assert.equal(regel(u, "lkv"), undefined);
});

test("register + bijstand: als gemeente (bijstand, 60)", () => {
  const u = reken(["register", "bijstand"], 60);
  assert.equal(regel(u, "lks").bedragPerJaar, LKS_GEMEENTE_60_JAAR);
  assert.equal(regel(u, "lkv").bedragPerJaar, 168064);
});

test("WIA + register: het hoogste loonkostenvoordeel", () => {
  const u = reken(["register", "wia"], 100);
  assert.equal(regel(u, "lkv").bedragPerJaar, 507520);
  assert.equal(regel(u, "lkv").categorie, "arbeidsgehandicapte_werknemer");
});

test("Wajong + bijstand: geen loonkostensubsidie", () => {
  assert.equal(regel(reken(["register", "wajong", "bijstand"], 60), "lks"), undefined);
});

test("geen van deze: niets, wel de toelichting", () => {
  const u = reken(["geen"], 60);
  assert.deepEqual(u.regels, []);
  assert.ok(u.overige.every((o) => !o.geldt));
  assert.ok(u.aannames.includes("geen"));
});

test("niets aangevinkt: geen bedragen en geen no-riskpolis", () => {
  const u = reken([], 60);
  assert.deepEqual(u.regels, []);
  assert.equal(overig(u, "nrp").geldt, false);
  assert.deepEqual(u.aannames, []);
});

test("lkv-voorbehoud: zes maanden alleen bij arbeidsgehandicapte, samenloop altijd", () => {
  assert.deepEqual(regel(reken(["register"], 60), "lkv").voorbehoud, ["samenloop"]);
  assert.deepEqual(regel(reken(["wia"], 60), "lkv").voorbehoud, ["zes_maanden", "samenloop"]);
});

test("alleen aanroepen die iets kunnen opleveren, bedragen eerst", () => {
  const doelen = (d) => kern.orienteer({ doelgroepen: d, uren: 32, loonwaarde: 60, uurloon: 1499 }).antwoorden.map((a) => a.output);
  assert.deepEqual(doelen(["bijstand"]), [
    "heeft_recht_op_lks",
    "heeft_recht_op_lkv",
    "heeft_recht_op_no_risk_polis",
    "mag_proefplaatsing_aangaan",
    "heeft_aanspraak_op_begeleiding_op_de_werkplek",
  ]);
  assert.deepEqual(doelen(["register", "wajong"]), ["heeft_recht_op_loondispensatie", "heeft_recht_op_lkv", "heeft_recht_op_no_risk_polis"]);
  assert.deepEqual(doelen(["wia"]), ["heeft_recht_op_lkv", "heeft_recht_op_no_risk_polis", "mag_jobcoaching_toekennen"]);
  assert.deepEqual(doelen(["geen"]), []);
});

test("loondispensatie telt niet mee bij een uurloon boven het minimumloon", () => {
  const u = reken(["register", "wajong"], 70, 32, 2000);
  assert.equal(regel(u, "ld"), undefined);
  assert.ok(u.aannames.includes("ld_cao"));
  assert.ok(regel(reken(["register", "wajong"], 70), "ld").bedragPerJaar > 0);
});

test("balans: altijd loonkostensubsidie, loondispensatie en loonkostenvoordeel, in die volgorde", () => {
  const u = reken(["register", "bijstand"], 60);
  const rijen = kern.balans(u, 10_000_000);
  assert.deepEqual(
    rijen.map((r) => [r.id, r.status]),
    [
      ["lks", "bedrag"],
      ["ld", "geldt_niet"],
      ["lkv", "bedrag"],
    ],
  );
  assert.equal(rijen[0].bedrag, LKS_GEMEENTE_60_JAAR);
  assert.equal(rijen[1].bedrag, 0);
  assert.equal(rijen[2].bedrag, regel(u, "lkv").bedragPerJaar);
});

test("balans: nooit meer terug dan de loonkosten", () => {
  const u = reken(["register", "bijstand"], 60);
  const rijen = kern.balans(u, LKS_GEMEENTE_60_JAAR + 100);
  assert.equal(rijen[0].bedrag, LKS_GEMEENTE_60_JAAR);
  assert.equal(rijen[2].bedrag, 100);
  assert.equal(kern.balans(u, 0).reduce((s, r) => s + r.bedrag, 0), 0);
});

test("balans: loondispensatie boven het minimumloon is niet meegeteld", () => {
  assert.equal(kern.balans(reken(["register", "wajong"], 70, 32, 2000), 10_000_000)[1].status, "niet_meegeteld");
  assert.equal(kern.balans(reken(["register", "wajong"], 70), 10_000_000)[1].status, "bedrag");
});
