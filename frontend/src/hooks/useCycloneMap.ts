import { useMemo } from "react";
import { sceneFromPrediction, sceneFromTrack } from "@/lib/mapScene";
import { useCycloneTrack } from "./useCyclone";
import { usePrediction } from "./usePrediction";
import { useCoastalDistricts } from "./useRegions";
import type { CoastalDistrict } from "@/types/track";

const NO_DISTRICTS: CoastalDistrict[] = [];

/**
 * What the map needs for the selected cyclone, fetched through the service layer: the observed track
 * (GET /api/cyclones/{id}/track), the prediction's forecast when one exists, and coastal districts for
 * impact popups. Without a prediction the scene carries no forecast.
 */
export function useCycloneMapData(cycloneId: string | undefined) {
  const track = useCycloneTrack(cycloneId);
  const prediction = usePrediction(cycloneId);
  const districts = useCoastalDistricts();
  const trackData = track.data;
  const predictionData = prediction.data;
  const scene = useMemo(
    () => (predictionData ? sceneFromPrediction(predictionData, trackData) : trackData ? sceneFromTrack(trackData) : null),
    [predictionData, trackData],
  );
  return {
    scene,
    districts: districts.data ?? NO_DISTRICTS,
    trackFixes: trackData?.history.length ?? 0,
    hasPrediction: Boolean(predictionData),
    forecastSource: prediction.source,
    // Track request state. A failed prediction only means "no forecast"; the prediction page reports it.
    loading: track.loading,
    error: track.error,
    refetch: track.refetch,
  };
}
