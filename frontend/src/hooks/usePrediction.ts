import { useMutation } from "@tanstack/react-query";
import { environment } from "@/config/environment";
import {
  getMlAssessment, getModelRegistry, getObservedTrack, getPrediction, getPredictionCases, getPredictionServiceStatus, predictCyclone,
} from "@/services/predictionApi";
import type { PredictionRequest } from "@/types/model";
import { useServiceQuery } from "./useServiceQuery";

/** Held-out storms the trained track model can forecast (always the live backend). */
export function usePredictionCases() {
  return useServiceQuery(["prediction-cases"], getPredictionCases);
}

/** Observed best track of one storm (always the live backend). */
export function useObservedTrack(cycloneId: string | undefined) {
  return useServiceQuery(["observed-track", cycloneId], () => getObservedTrack(cycloneId ?? ""), { enabled: Boolean(cycloneId) });
}

/** Backend reachability + prediction-model state (GET /api/health, GET /api/ml/status), re-checked every 30 s. */
export function usePredictionServiceStatus() {
  return useServiceQuery(["prediction-service-status"], getPredictionServiceStatus, { refetchIntervalMs: environment.healthPollMs });
}

/** POST /api/ml/predict on demand (the Track forecast panel's Run prediction button). */
export function useRunPrediction() {
  return useMutation({ mutationFn: async (payload: PredictionRequest) => (await predictCyclone(payload)).data });
}

/** `data === null` after loading means "no prediction available" for this cyclone. */
export function usePrediction(cycloneId: string | undefined) {
  return useServiceQuery(["prediction", cycloneId], () => getPrediction(cycloneId ?? ""), { enabled: Boolean(cycloneId) });
}

/** Detection/classification of a registry cyclone: null until the backend has an image for it (see getMlAssessment). */
export function useMlAssessment(cycloneId: string | undefined) {
  return useServiceQuery(["ml-assessment", cycloneId], getMlAssessment, { enabled: Boolean(cycloneId) });
}

/** GET /api/ml/status — always the live backend, re-checked every 30 s. */
export function useModelRegistry() {
  return useServiceQuery(["model-registry"], getModelRegistry, { refetchIntervalMs: environment.healthPollMs });
}
