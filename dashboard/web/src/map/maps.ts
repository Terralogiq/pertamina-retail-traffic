import { importLibrary, setOptions } from "@googlemaps/js-api-loader";
import { getConfig } from "../api";

let loaded: Promise<{
  maps: google.maps.MapsLibrary;
  core: google.maps.CoreLibrary;
  marker: google.maps.MarkerLibrary;
}> | null = null;

/** Configure the loader once (key from /api/config, after login) and import the libraries the map needs. */
export function loadMaps() {
  if (!loaded) {
    loaded = getConfig()
      .then((config) => {
        setOptions({ key: config.maps_browser_key, v: "weekly" });
        return Promise.all([importLibrary("maps"), importLibrary("core"), importLibrary("marker")]);
      })
      .then(([maps, core, marker]) => ({ maps, core, marker }))
      .catch((e) => {
        loaded = null; // allow a retry after a failed load (e.g. 401, then login)
        throw e;
      });
  }
  return loaded;
}
