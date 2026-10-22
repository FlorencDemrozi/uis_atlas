import { createContext } from "preact";
import { useCallback, useContext, useEffect, useMemo, useState } from "preact/hooks";
import en from "./i18n/en.json";
import nb from "./i18n/nb.json";
import { dept } from "./departments";

export type Lang = "en" | "nb";
const STRINGS: Record<Lang, Record<string, string>> = { en, nb };

export interface I18nValue {
  lang: Lang;
  setLang: (l: Lang) => void;
  t: (key: string, vars?: Record<string, string | number>) => string;
  deptName: (key: string, short?: boolean) => string;
  num: (n: number) => string;
}

export const I18n = createContext<I18nValue>(null as unknown as I18nValue);
export const useI18n = () => useContext(I18n);

function initialLang(): Lang {
  try {
    const saved = localStorage.getItem("atlas-lang");
    if (saved === "en" || saved === "nb") return saved;
  } catch { /* storage unavailable */ }
  return /^(nb|no|nn)/i.test(navigator.language) ? "nb" : "en";
}

export function useI18nState(): I18nValue {
  const [lang, setLangState] = useState<Lang>(initialLang);
  useEffect(() => { document.documentElement.lang = lang === "nb" ? "nb" : "en"; }, [lang]);
  const setLang = useCallback((l: Lang) => {
    setLangState(l);
    try { localStorage.setItem("atlas-lang", l); } catch { /* ignore */ }
  }, []);
  return useMemo(() => {
    const fmt = new Intl.NumberFormat(lang === "nb" ? "nb-NO" : "en-GB");
    return {
      lang, setLang,
      t: (key, vars) => {
        let s = STRINGS[lang][key] ?? STRINGS.en[key] ?? key;
        for (const [k, v] of Object.entries(vars ?? {})) {
          s = s.replaceAll(`{${k}}`, typeof v === "number" ? fmt.format(v) : v);
        }
        return s;
      },
      deptName: (key, short) => {
        const d = dept(key);
        return lang === "nb" ? (short ? d.nbShort : d.nb) : (short ? d.enShort : d.en);
      },
      num: (n) => fmt.format(n),
    };
  }, [lang, setLang]);
}
