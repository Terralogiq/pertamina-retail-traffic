import type { CSSProperties, ReactNode } from "react";
import { useEffect, useState } from "react";
import { errorText } from "../api";
import { Block, Notice, Section, Skeleton } from "../site/Section";
import type { Load } from "../site/useSiteData";
import { DemoNote } from "../weather/DemoBadge";
import { ReviewThemesResponse, ThemeCount, getReviewThemes } from "./api";
import { categoryName, labelList, maxTotal, monthLabel, nLine } from "./model";
import "./ReviewThemesPanel.css";

/** Height of the loaded section, so the skeleton matches what loads into it. */
const THEMES_HEIGHT = 360;

/** One category: stacked recent and older segments, scaled to the largest category. The counts are written out beside the bar. */
function ThemeBar({ theme, max }: { theme: ThemeCount; max: number }) {
  const style = { "--recent": theme.recent, "--older": theme.older, "--max": max } as CSSProperties;
  return (
    <li className="theme-row">
      <span className="theme-name">{categoryName(theme.category)}</span>
      <span className="theme-bar" style={style} aria-hidden="true">
        <span className="theme-seg theme-seg-recent" />
        <span className="theme-seg theme-seg-older" />
      </span>
      <span className="theme-counts num">
        {theme.recent} recent · {theme.older} older
      </span>
    </li>
  );
}

/** The content of the panel for a loaded response. Counts and n only: no rates, no ranking across sites. */
export function ReviewThemes({ data }: { data: ReviewThemesResponse }) {
  const max = maxTotal(data.categories);
  return (
    <>
      <DemoNote>sampled, ≤15 reviews per window</DemoNote>
      <p className="themes-n">{nLine(data)}</p>
      {data.n_labelled === 0 ? (
        <Notice>No reviews labelled for this site yet.</Notice>
      ) : (
        <>
          <Block title="Complaint topics" aside="negative or mixed reviews">
            {data.categories.length === 0 ? (
              <Notice>No negative or mixed review in the labelled sample.</Notice>
            ) : (
              <>
                <ul className="theme-legend" aria-label="Legend">
                  <li>
                    <span className="theme-swatch theme-seg-recent" aria-hidden="true" />
                    Last 12 months
                  </li>
                  <li>
                    <span className="theme-swatch theme-seg-older" aria-hidden="true" />
                    Older
                  </li>
                </ul>
                <ul className="theme-rows">
                  {data.categories.map((t) => (
                    <ThemeBar key={t.category} theme={t} max={max} />
                  ))}
                </ul>
              </>
            )}
          </Block>
          {data.gists.length > 0 && (
            <Block title="Recent complaints" aside="paraphrased, no author">
              <ul className="theme-gists">
                {data.gists.map((g, i) => (
                  <li key={i}>
                    <p className="theme-gist-meta">
                      <time dateTime={g.month}>{monthLabel(g.month)}</time>
                      {g.labels.length > 0 && <span>{labelList(g.labels)}</span>}
                    </p>
                    <p className="theme-gist">{g.gist}</p>
                  </li>
                ))}
              </ul>
            </Block>
          )}
        </>
      )}
    </>
  );
}

/** Review themes section of the site page: fetches its own data once the page has mounted it for a known site. `summary` is the AI card shown first. */
export function ReviewThemesPanel({ siteId, summary }: { siteId: string; summary?: ReactNode }) {
  const [state, setState] = useState<{ siteId: string; data: Load<ReviewThemesResponse> }>({ siteId, data: undefined });
  useEffect(() => {
    let live = true;
    setState({ siteId, data: undefined });
    getReviewThemes(siteId)
      .then((data) => live && setState({ siteId, data }))
      .catch((e) => live && setState({ siteId, data: e instanceof Error ? e : new Error(errorText(e)) }));
    return () => {
      live = false;
    };
  }, [siteId]);
  const data = state.siteId === siteId ? state.data : undefined; // never the previous site's counts under the new heading
  return (
    <Section id="review-themes" title="Review themes" note="From Google reviews of this station">
      {summary}
      {data === undefined && <Skeleton height={THEMES_HEIGHT} label="Loading review themes" />}
      {data instanceof Error && <Notice tone="error">Couldn't load review themes. {data.message}</Notice>}
      {data === null && <Notice>No review themes for this site yet.</Notice>}
      {data && !(data instanceof Error) && <ReviewThemes data={data} />}
    </Section>
  );
}
