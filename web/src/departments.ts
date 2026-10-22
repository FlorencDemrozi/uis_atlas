// Department identity: fixed colour slot (never by rank) and names in both languages.
// Keys are the department names written by the pipeline (pipeline/config.py).

export interface Dept { key: string; color: string; en: string; enShort: string; nb: string; nbShort: string }

export const NOT_STATED = "Faculty of Science and Technology (department not stated)";

export const DEPARTMENTS: Dept[] = [
  { key: "Computer Science and Electrical Engineering", color: "var(--dept-1)",
    en: "Computer Science and Electrical Engineering", enShort: "Computer Sci. & Electrical Eng.",
    nb: "Institutt for data- og elektroteknologi", nbShort: "Data- og elektroteknologi" },
  { key: "Energy and Petroleum Engineering", color: "var(--dept-2)",
    en: "Energy and Petroleum Engineering", enShort: "Energy & Petroleum Eng.",
    nb: "Institutt for energi- og petroleumsteknologi", nbShort: "Energi- og petroleumsteknologi" },
  { key: "Chemistry, Bioscience and Environmental Engineering", color: "var(--dept-3)",
    en: "Chemistry, Bioscience and Environmental Engineering", enShort: "Chemistry, Bioscience & Env. Eng.",
    nb: "Institutt for kjemi, bioteknologi og miljøteknikk", nbShort: "Kjemi, bioteknologi og miljø" },
  { key: "Energy Resources", color: "var(--dept-4)",
    en: "Energy Resources", enShort: "Energy Resources",
    nb: "Institutt for energiressurser", nbShort: "Energiressurser" },
  { key: "Safety, Economics and Planning", color: "var(--dept-5)",
    en: "Safety, Economics and Planning", enShort: "Safety, Economics & Planning",
    nb: "Institutt for sikkerhet, økonomi og planlegging", nbShort: "Sikkerhet, økonomi og planlegging" },
  { key: "Mathematics and Physics", color: "var(--dept-6)",
    en: "Mathematics and Physics", enShort: "Mathematics & Physics",
    nb: "Institutt for matematikk og fysikk", nbShort: "Matematikk og fysikk" },
  { key: "Mechanical and Structural Engineering and Materials Science", color: "var(--dept-7)",
    en: "Mechanical and Structural Engineering and Materials Science", enShort: "Mech., Structural & Materials",
    nb: "Institutt for maskin, bygg og materialteknologi", nbShort: "Maskin, bygg og materialer" },
  { key: NOT_STATED, color: "var(--dept-none)",
    en: "Faculty (department not stated)", enShort: "Department not stated",
    nb: "Fakultetet (institutt ikke oppgitt)", nbShort: "Institutt ikke oppgitt" },
];

const byKey = new Map(DEPARTMENTS.map((d) => [d.key, d]));

export function dept(key: string): Dept {
  return byKey.get(key) ?? { key, color: "var(--dept-none)", en: key, enShort: key, nb: key, nbShort: key };
}

/** Departments in fixed display order, keeping only those present. */
export function orderedDepts(present: Iterable<string>): Dept[] {
  const set = new Set(present);
  return DEPARTMENTS.filter((d) => set.has(d.key));
}
