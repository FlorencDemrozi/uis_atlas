// UiS organisation: faculties and their departments, names in both languages and
// fixed colour slots (never by rank). Keys are the names written by the pipeline
// (pipeline/config.py FACULTIES); tests/test_policy.py checks that they match.
//
// Colour rule: a researcher's dot has their faculty's colour. Only when a view is
// scoped to one faculty do departments get their own colours (Dept.ownColor).

export interface Unit { key: string; code: string; en: string; enShort: string; nb: string; nbShort: string; color: string }
export interface Dept extends Unit { faculty: string; ownColor: string; notStated: boolean }
export interface Faculty extends Unit { depts: Dept[] }

type Names = [key: string, code: string, en: string, enShort: string, nb: string, nbShort: string];

function faculty(slot: number, f: Names, depts: Names[], notStated: [en: string, nb: string]): Faculty {
  const color = `var(--fac-${slot})`;
  const unit = ([key, code, en, enShort, nb, nbShort]: Names): Unit => ({ key, code, en, enShort, nb, nbShort, color });
  const fac: Faculty = { ...unit(f), depts: [] };
  fac.depts = depts.map((d, i) => ({ ...unit(d), faculty: fac.key, ownColor: `var(--dept-${i + 1})`, notStated: false }));
  fac.depts.push({
    key: `${fac.key} (department not stated)`, code: `${fac.code}-x`, color, faculty: fac.key,
    en: `${fac.en} (department not stated)`, enShort: notStated[0],
    nb: `${fac.nb} (institutt ikke oppgitt)`, nbShort: notStated[1],
    ownColor: "var(--dept-none)", notStated: true,
  });
  return fac;
}

export const FACULTIES: Faculty[] = [
  faculty(1, ["Faculty of Science and Technology", "tn", "Faculty of Science and Technology", "Science and Technology",
    "Det teknisk-naturvitenskapelige fakultet", "Teknisk-naturvitenskap"], [
    ["Electrical Engineering and Computer Science", "tn-ide", "Department of Electrical Engineering and Computer Science",
      "Electrical Eng. & Computer Sci.", "Institutt for data- og elektroteknologi", "Data- og elektroteknologi"],
    ["Energy and Petroleum Engineering", "tn-iep", "Department of Energy and Petroleum Engineering",
      "Energy & Petroleum Eng.", "Institutt for energi- og petroleumsteknologi", "Energi- og petroleumsteknologi"],
    ["Chemistry, Bioscience and Environmental Engineering", "tn-ikbm", "Department of Chemistry, Bioscience and Environmental Engineering",
      "Chemistry, Bioscience & Env. Eng.", "Institutt for kjemi, biovitenskap og miljøteknologi", "Kjemi, biovitenskap og miljø"],
    ["Safety, Economics and Planning", "tn-isop", "Department of Safety, Economics and Planning",
      "Safety, Economics & Planning", "Institutt for sikkerhet, økonomi og planlegging", "Sikkerhet, økonomi og planlegging"],
    ["Mathematics and Physics", "tn-imf", "Department of Mathematics and Physics",
      "Mathematics & Physics", "Institutt for matematikk og fysikk", "Matematikk og fysikk"],
    ["Mechanical and Structural Engineering and Materials Science", "tn-imbm", "Department of Mechanical and Structural Engineering and Materials Science",
      "Mech., Structural & Materials", "Institutt for maskin, bygg og materialteknologi", "Maskin, bygg og materialer"],
  ], ["Sci. & Tech. – dept. not stated", "Tek.-nat. – institutt ikke oppgitt"]),
  faculty(2, ["Faculty of Arts and Education", "uh", "Faculty of Arts and Education", "Arts and Education",
    "Fakultet for utdanningsvitenskap og humaniora", "Utdanningsvitenskap og humaniora"], [
    ["Department of Education and Sports Science", "uh-igis", "Department of Education and Sports Science",
      "Education & Sports Science", "Institutt for grunnskolelærerutdanning, idrett og spesialpedagogikk",
      "Grunnskolelærerutd., idrett og spesialped."],
    ["Department of Cultural Studies and Languages", "uh-iks", "Department of Cultural Studies and Languages",
      "Cultural Studies & Languages", "Institutt for kultur- og språkvitenskap", "Kultur- og språkvitenskap"],
    ["Department of Early Childhood Education", "uh-ibl", "Department of Early Childhood Education",
      "Early Childhood Education", "Institutt for barnehagelærerutdanning", "Barnehagelærerutdanning"],
  ], ["Arts & Education – dept. not stated", "Utd.vit. og hum. – institutt ikke oppgitt"]),
  faculty(3, ["Faculty of Performing Arts", "uk", "Faculty of Performing Arts", "Performing Arts",
    "Fakultet for utøvende kunstfag", "Utøvende kunstfag"], [
    ["Department of Jazz, Dance, Practical-Pedagogical Education and Music Production", "uk-jazz",
      "Department of Jazz, Dance, Practical-Pedagogical Education and Music Production",
      "Jazz, Dance, PPE & Music Prod.", "Avdeling for jazz, dans, PPU og musikkproduksjon", "Jazz, dans, PPU og musikkprod."],
    ["Department of Classical Music", "uk-klassisk", "Department of Classical Music",
      "Classical Music", "Avdeling for klassisk musikk", "Klassisk musikk"],
  ], ["Performing Arts – dept. not stated", "Utøvende kunstfag – avdeling ikke oppgitt"]),
  faculty(4, ["UiS School of Business and Law", "hhs", "UiS School of Business and Law", "Business and Law",
    "Handelshøgskolen ved UiS", "Handelshøgskolen"], [
    ["Department of Economics and Finance", "hhs-sof", "Department of Economics and Finance",
      "Economics & Finance", "Avdeling for samfunnsøkonomi og finans", "Samfunnsøkonomi og finans"],
    ["Department of Innovation, Management and Marketing", "hhs-ilm", "Department of Innovation, Management and Marketing",
      "Innovation, Mgmt. & Marketing", "Avdeling for innovasjon, ledelse og markedsføring", "Innovasjon, ledelse og markedsføring"],
    ["Department of Accounting and Law", "hhs-rr", "Department of Accounting and Law",
      "Accounting & Law", "Avdeling for regnskap og rettsvitenskap", "Regnskap og rettsvitenskap"],
  ], ["Business & Law – dept. not stated", "Handelshøgskolen – avdeling ikke oppgitt"]),
  faculty(5, ["Faculty of Health Sciences", "hv", "Faculty of Health Sciences", "Health Sciences",
    "Det helsevitenskapelige fakultet", "Helsevitenskap"], [
    ["Department of Quality and Health Technology", "hv-kht", "Department of Quality and Health Technology",
      "Quality & Health Technology", "Avdeling for kvalitet og helseteknologi", "Kvalitet og helseteknologi"],
    ["Department of Public Health", "hv-folkehelse", "Department of Public Health",
      "Public Health", "Avdeling for folkehelse", "Folkehelse"],
    ["Department of Caring and Ethics", "hv-oe", "Department of Caring and Ethics",
      "Caring & Ethics", "Avdeling for omsorg og etikk", "Omsorg og etikk"],
  ], ["Health Sciences – dept. not stated", "Helsevitenskap – avdeling ikke oppgitt"]),
  faculty(6, ["Faculty of Social Sciences", "sv", "Faculty of Social Sciences", "Social Sciences",
    "Det samfunnsvitenskapelige fakultet", "Samfunnsvitenskap"], [
    ["Department of Media and Social Sciences", "sv-ims", "Department of Media and Social Sciences",
      "Media & Social Sciences", "Institutt for medie- og samfunnsfag", "Medie- og samfunnsfag"],
    ["Department of Social Studies", "sv-isf", "Department of Social Studies",
      "Social Studies", "Institutt for sosialfag", "Sosialfag"],
    ["Department of Psychology", "sv-psyk", "Department of Psychology",
      "Psychology", "Institutt for psykologi", "Psykologi"],
    ["NHS – Department of Leadership and Service Innovation", "sv-nhs", "NHS – Department of Leadership and Service Innovation",
      "NHS – Leadership & Service Innov.", "Norsk hotellhøgskole – Institutt for ledelse og serviceinnovasjon", "Norsk hotellhøgskole"],
  ], ["Social Sciences – dept. not stated", "Samfunnsvitenskap – institutt ikke oppgitt"]),
];

export const DEPARTMENTS: Dept[] = FACULTIES.flatMap((f) => f.depts);

const deptByKey = new Map(DEPARTMENTS.map((d) => [d.key, d]));
const facByKey = new Map(FACULTIES.map((f) => [f.key, f]));
const byCode = new Map<string, Unit>([...FACULTIES, ...DEPARTMENTS].map((u) => [u.code, u]));

const UNKNOWN = (key: string): Dept => ({ key, code: key, color: "var(--dept-none)", ownColor: "var(--dept-none)",
  faculty: "", notStated: true, en: key, enShort: key, nb: key, nbShort: key });

export function dept(key: string): Dept {
  return deptByKey.get(key) ?? UNKNOWN(key);
}

export function fac(key: string): Faculty | undefined {
  return facByKey.get(key);
}

export function facultyOf(deptKey: string): Faculty | undefined {
  return facByKey.get(deptByKey.get(deptKey)?.faculty ?? "");
}

/** A faculty or a department by key (for charts that work at either level). */
export function unit(key: string): Unit {
  return facByKey.get(key) ?? dept(key);
}

export function unitByCode(code: string): Unit | undefined {
  return byCode.get(code);
}

/** True for a faculty's "department not stated" bucket (false for faculties). */
export function isNotStated(key: string) {
  return deptByKey.get(key)?.notStated ?? false;
}

/** Departments in fixed display order, keeping only those present. */
export function orderedDepts(present: Iterable<string>): Dept[] {
  const set = new Set(present);
  return DEPARTMENTS.filter((d) => set.has(d.key));
}

/** Faculties in fixed display order, keeping only those present. */
export function orderedFaculties(present: Iterable<string>): Faculty[] {
  const set = new Set(present);
  return FACULTIES.filter((f) => set.has(f.key));
}
