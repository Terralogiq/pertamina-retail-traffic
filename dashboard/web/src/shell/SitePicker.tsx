import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Site, getSites } from "../map/api";

/** "<name> · <city>": the option text, so two stations with the same name stay apart. */
export const siteOptionLabel = (s: Site) => [s.name, s.city].filter(Boolean).join(" · ");

/** City, then name; sites without a city last. */
export function sortSites(sites: Site[]): Site[] {
  return [...sites].sort(
    (a, b) => (a.city ?? "￿").localeCompare(b.city ?? "￿") || a.name.localeCompare(b.name),
  );
}

/** `undefined` = loading, `null` = failed (the picker hides; the shell never waits on it). */
export function useSiteList(): Site[] | null | undefined {
  const [sites, setSites] = useState<Site[] | null | undefined>(undefined);
  useEffect(() => {
    let live = true;
    getSites()
      .then((s) => live && setSites(sortSites(s)))
      .catch(() => live && setSites(null));
    return () => {
      live = false;
    };
  }, []);
  return sites;
}

/** The site code in /site/:id, or "" on any other page. */
export const siteIdFromPath = (path: string) => (path.startsWith("/site/") ? decodeURIComponent(path.slice(6).split("/")[0]) : "");

/** Navigation only: a native select that goes to /site/:id. On a site page that site is selected. */
export function SitePicker({ sites, currentId }: { sites: Site[] | null | undefined; currentId: string }) {
  const navigate = useNavigate();
  if (sites === null) return null;
  const loading = sites === undefined;
  const known = !loading && sites.some((s) => s.site_id === currentId);
  return (
    <div className="shell-picker">
      <label htmlFor="site-picker" className="visually-hidden">
        Site
      </label>
      <select
        id="site-picker"
        className="shell-picker-select"
        disabled={loading}
        value={known ? currentId : ""}
        onChange={(e) => e.target.value && navigate(`/site/${encodeURIComponent(e.target.value)}`)}
      >
        <option value="" disabled>
          {loading ? "Loading sites…" : "Go to site…"}
        </option>
        {!loading &&
          sites.map((s) => (
            <option key={s.site_id} value={s.site_id}>
              {siteOptionLabel(s)}
            </option>
          ))}
      </select>
    </div>
  );
}
