import { BandIndicator } from "../theme/BandIndicator";
import type { BandId } from "../theme/palette";
import { BANDS } from "../theme/palette";
import type { ReactNode } from "react";
import type { LatestLeg, Leg, Site } from "./api";
import { formatDelay, formatSlot, formatSpeed, legBand, legContext, legLabel } from "./bands";
import type { SiteState } from "./severity";
import "./LegPopup.css";

/** What the popup shows, as plain strings so it can be tested without rendering. */
export interface LegPopupModel {
  /** Small line above the title: which leg, and which way it runs relative to the SPBU. */
  overline: string;
  title: string;
  band: BandId;
  bandLabel: string;
  delay: string;
  speed: string;
  /** Slot time in the site's local time; null when the leg has no reading. */
  slot: string | null;
  /** Why the band is what it is, when that is not the usual congestion index; else null. */
  basis: string | null;
}

export function buildLegPopup(site: Site, leg: Leg, row: LatestLeg | undefined): LegPopupModel {
  const { band, basis } = legBand(row, { roadClass: site.road_class, expectedDistanceM: leg.expected_distance_m });
  return {
    overline: `${legLabel(leg.leg)} · ${leg.leg === "approach" ? "toward the SPBU" : "away from the SPBU"}`,
    title: site.name,
    band,
    bandLabel: BANDS[band].label,
    delay: formatDelay(row?.delay_s),
    speed: formatSpeed(row?.speed_kmh),
    slot: row ? formatSlot(row.slot_time, site.timezone) : null,
    basis: basis === "speed" ? "Provisional until the usual travel time is known" : null,
  };
}

/** Site card (overview marker): one reading per leg, with the newest slot in the site's local time. */
export interface SitePopupModel {
  /** "City · road"; null when the site has neither. */
  overline: string | null;
  title: string;
  legs: { name: string; band: BandId; bandLabel: string; delay: string }[];
  slot: string | null;
}

export function buildSitePopup(site: Site, latest: Map<string, LatestLeg>): SitePopupModel {
  const rows = site.legs.map((leg) => ({ leg, row: latest.get(leg.selected_route_id) }));
  const slots = rows.flatMap(({ row }) => (row ? [row.slot_time] : [])).sort();
  return {
    overline: [site.city, site.road_name].filter(Boolean).join(" · ") || null,
    title: site.name,
    legs: rows.map(({ leg, row }) => {
      const { band } = legBand(row, legContext(site, leg.selected_route_id));
      return { name: legLabel(leg.leg), band, bandLabel: BANDS[band].label, delay: formatDelay(row?.delay_s) };
    }),
    slot: slots.length ? formatSlot(slots[slots.length - 1], site.timezone) : null,
  };
}

/** Group card (overlapping markers): the grouped sites worst first, each with its worst band and delay. */
export interface GroupPopupModel {
  overline: string;
  title: string;
  sites: { name: string; band: BandId; bandLabel: string; delay: string }[];
  /** Sites beyond the first GROUP_POPUP_MAX that are not listed. */
  more: number;
  hint: string;
}

export const GROUP_POPUP_MAX = 5;

/** `members` is in ranked order (worst first), as the marker code has it. */
export function buildGroupPopup(members: SiteState[]): GroupPopupModel {
  return {
    overline: "Nearby sites",
    title: `${members.length} sites`,
    sites: members.slice(0, GROUP_POPUP_MAX).map((m) => ({
      name: m.site.name,
      band: m.band,
      bandLabel: BANDS[m.band].label,
      delay: formatDelay(m.worstDelay),
    })),
    more: Math.max(0, members.length - GROUP_POPUP_MAX),
    hint: "Click to zoom in",
  };
}

/** Shared card frame: overline row (with the close button when pinned, so no empty header), then the content. */
function PopupFrame({
  overline,
  title,
  onClose,
  wide = false,
  children,
}: {
  overline: string | null;
  /** Names the card when it is pinned (a dialog). */
  title: string;
  onClose?: () => void;
  wide?: boolean;
  children: ReactNode;
}) {
  return (
    <div
      className={wide ? "leg-popup leg-popup-wide" : "leg-popup"}
      role={onClose ? "dialog" : "tooltip"}
      aria-label={onClose ? title : undefined}
      data-pinned={onClose ? "" : undefined}
    >
      {(overline || onClose) && (
        <div className="leg-popup-head">
          <p className="leg-popup-overline">{overline}</p>
          {onClose && (
            <button type="button" className="leg-popup-close" aria-label="Close" onClick={onClose}>
              <svg viewBox="0 0 12 12" aria-hidden="true" focusable="false">
                <path d="M2 2l8 8M10 2l-8 8" />
              </svg>
            </button>
          )}
        </div>
      )}
      {children}
    </div>
  );
}

/**
 * Card shown over a hovered or tapped leg. Hover cards pass pointer events through to the map;
 * a pinned card (touch, or a click on the site map) takes them and carries a close button.
 */
export function LegPopup({ model, onClose }: { model: LegPopupModel; onClose?: () => void }) {
  return (
    <PopupFrame overline={model.overline} title={model.title} onClose={onClose}>
      <p className="leg-popup-title" title={model.title}>
        {model.title}
      </p>
      <div className="leg-popup-reading">
        <BandIndicator band={model.band} />
        <span className="leg-popup-delay">{model.delay}</span>
      </div>
      <p className="leg-popup-meta">
        <span>Speed {model.speed}</span>
        {model.slot && <span>Slot {model.slot}</span>}
      </p>
      {model.basis && <p className="leg-popup-basis">{model.basis}</p>}
    </PopupFrame>
  );
}

export function SitePopup({ model, onClose }: { model: SitePopupModel; onClose?: () => void }) {
  return (
    <PopupFrame overline={model.overline} title={model.title} onClose={onClose}>
      <p className="leg-popup-title" title={model.title}>
        {model.title}
      </p>
      <ul className="leg-popup-rows">
        {model.legs.map((l) => (
          <li key={l.name}>
            <span className="leg-popup-row-name">{l.name}</span>
            <BandIndicator band={l.band} />
            <span className="leg-popup-row-delay">{l.delay}</span>
          </li>
        ))}
      </ul>
      {model.slot && <p className="leg-popup-meta">Slot {model.slot}</p>}
    </PopupFrame>
  );
}

export function GroupPopup({ model }: { model: GroupPopupModel }) {
  return (
    <PopupFrame overline={model.overline} title={model.title} wide>
      <p className="leg-popup-title">{model.title}</p>
      <ul className="leg-popup-rows leg-popup-rows-group">
        {model.sites.map((m) => (
          <li key={m.name}>
            <span className="leg-popup-row-name" title={m.name}>
              {m.name}
            </span>
            <BandIndicator band={m.band} compact />
            <span className="leg-popup-row-delay">{m.delay}</span>
          </li>
        ))}
      </ul>
      {model.more > 0 && <p className="leg-popup-meta">and {model.more} more</p>}
      <p className="leg-popup-basis">{model.hint}</p>
    </PopupFrame>
  );
}
