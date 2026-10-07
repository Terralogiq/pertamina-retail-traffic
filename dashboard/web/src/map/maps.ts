import { importLibrary, setOptions } from "@googlemaps/js-api-loader";
import { AppConfig, getConfig } from "../api";

/** Google's placeholder Map ID: AdvancedMarkerElement needs one; it allows no cloud styling. */
const DEMO_MAP_ID = "DEMO_MAP_ID";

let loaded: Promise<{
  maps: google.maps.MapsLibrary;
  core: google.maps.CoreLibrary;
  marker: google.maps.MarkerLibrary;
  mapId: string;
}> | null = null;

/**
 * Configure the loader once (key from /api/config, after login) and import the libraries the map needs.
 * `mapId` is the cloud-styled Map ID when the server has one (MAPS_MAP_ID), else DEMO_MAP_ID.
 */
export function loadMaps() {
  if (!loaded) {
    loaded = getConfig()
      .then(async (config: AppConfig & { maps_map_id?: string | null }) => {
        setOptions({ key: config.maps_browser_key, v: "weekly" });
        const [maps, core, marker] = await Promise.all([importLibrary("maps"), importLibrary("core"), importLibrary("marker")]);
        return { maps, core, marker, mapId: config.maps_map_id || DEMO_MAP_ID };
      })
      .catch((e) => {
        loaded = null; // allow a retry after a failed load (e.g. 401, then login)
        throw e;
      });
  }
  return loaded;
}
