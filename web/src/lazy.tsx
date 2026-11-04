import type { ComponentType } from "preact";
import { useEffect, useState } from "preact/hooks";
import { useI18n } from "./i18n";

/** A view whose code is downloaded the first time it is opened (Search and Profile,
 *  where most visits start, are in the main bundle). */
export function lazyView<P extends object>(load: () => Promise<ComponentType<P>>): ComponentType<P> {
  let View: ComponentType<P> | null = null;
  let pending: Promise<void> | null = null;
  return function LazyView(props: P) {
    const { t } = useI18n();
    const [, setLoaded] = useState(!!View);
    const [error, setError] = useState<string | null>(null);
    useEffect(() => {
      if (View) return;
      pending ??= load().then((v) => { View = v; });
      pending.then(() => setLoaded(true), (e) => { pending = null; setError(String(e)); });
    }, []);
    if (error) return <p class="loading">{t("app.loadError")} ({error})</p>;
    if (!View) return <p class="loading" role="status">{t("app.loading")}</p>;
    return <View {...props} />;
  };
}
