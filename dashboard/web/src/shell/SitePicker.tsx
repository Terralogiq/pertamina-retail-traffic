import { FormEvent, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Site, getSites } from "../map/api";

/** "<name> · <city>": the full option text, kept as the option's tooltip. */
export const siteOptionLabel = (s: Site) => [s.name, s.city].filter(Boolean).join(" · ");

/**
 * "<code or short name> · <city>" for the picker: drops a leading "SPBU Pertamina" / "SPBU" and a trailing
 * repeat of the city, which Google display names carry ("SPBU Pertamina 61.761.03 - MT Haryono Balikpapan").
 */
export function shortSiteLabel(s: Site): string {
  let name = s.name.replace(/^\s*SPBU(\s+Pertamina)?\b[\s:-]*/i, "").trim();
  const city = s.city?.trim();
  if (city && name.toLowerCase().endsWith(city.toLowerCase())) {
    name = name.slice(0, name.length - city.length).replace(/[\s,-]+$/, "");
  }
  return [name || s.name, city].filter(Boolean).join(" · ");
}

/** City, then name; sites without a city last. */
export function sortSites(sites: Site[]): Site[] {
  return [...sites].sort(
    (a, b) => (a.city ?? "￿").localeCompare(b.city ?? "￿") || a.name.localeCompare(b.name),
  );
}

/**
 * `undefined` = loading, `null` = failed (the picker hides; the shell never waits on it).
 * A failed load is retried when the path changes, so one bad request does not hide the picker for the session.
 */
export function useSiteList(pathname: string): Site[] | null | undefined {
  const [sites, setSites] = useState<Site[] | null | undefined>(undefined);
  useEffect(() => {
    if (sites) return;
    let live = true;
    getSites()
      .then((s) => live && setSites(sortSites(s)))
      .catch(() => live && setSites(null));
    return () => {
      live = false;
    };
  }, [pathname]);
  return sites;
}

/** A form (WCAG 3.2.2): choosing an option changes nothing until "Go" is pressed, which opens /site/:id. */
export function SitePicker({ sites, currentId }: { sites: Site[] | null | undefined; currentId: string }) {
  const navigate = useNavigate();
  const [choice, setChoice] = useState(currentId);
  useEffect(() => setChoice(currentId), [currentId]);
  if (sites === null) return null;
  const loading = sites === undefined;
  const known = !loading && sites.some((s) => s.site_id === choice);
  const go = (e: FormEvent) => {
    e.preventDefault();
    if (known) navigate(`/site/${encodeURIComponent(choice)}`);
  };
  return (
    <form className="shell-picker" onSubmit={go}>
      <label htmlFor="site-picker" className="shell-picker-label">
        Site
      </label>
      <select
        id="site-picker"
        className="shell-picker-select"
        disabled={loading}
        value={known ? choice : ""}
        onChange={(e) => setChoice(e.target.value)}
      >
        <option value="" disabled>
          {loading ? "Loading sites…" : "Go to site…"}
        </option>
        {!loading &&
          sites.map((s) => (
            <option key={s.site_id} value={s.site_id} title={siteOptionLabel(s)}>
              {shortSiteLabel(s)}
            </option>
          ))}
      </select>
      <button type="submit" className="button button-primary shell-picker-go" disabled={loading}>
        Go
      </button>
    </form>
  );
}
