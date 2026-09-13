import { buildSearch } from "@/lib/searchParams";

/** Context carried between pages so region/subregion/cyclone selections survive navigation. */
export interface RouteContext {
  region?: string;
  subregion?: string;
  cyclone?: string;
  source?: string;
  /** Selected forecast horizon in hours (prediction page). */
  h?: number;
}

export const routeTo = {
  prediction: (context: RouteContext = {}) =>
    `/prediction${buildSearch({ region: context.region, subregion: context.subregion, cyclone: context.cyclone, h: context.h == null ? undefined : String(context.h) })}`,
  cyclones: (context: RouteContext = {}) =>
    `/cyclones${buildSearch({ region: context.region, subregion: context.subregion, cyclone: context.cyclone, source: context.source })}`,
  satellite: (context: RouteContext = {}) =>
    `/satellite${buildSearch({ region: context.region, subregion: context.subregion, cyclone: context.cyclone, source: context.source })}`,
};
