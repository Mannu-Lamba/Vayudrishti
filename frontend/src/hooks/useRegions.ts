import { getCoastalDistricts, getRegions } from "@/services/regionApi";
import { useServiceQuery } from "./useServiceQuery";

export function useRegions() {
  return useServiceQuery(["regions"], getRegions);
}

export function useCoastalDistricts() {
  return useServiceQuery(["coastal-districts"], getCoastalDistricts);
}
