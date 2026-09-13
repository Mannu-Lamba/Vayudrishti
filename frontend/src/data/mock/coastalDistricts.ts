import type { CoastalDistrict } from "@/types/track";

// Mock coastal district gazetteer for Phase 2 impact preview. Phase 3: replace with a real
// administrative-boundary service (district centroid or polygon) behind getCoastalDistricts().
export const coastalDistricts: CoastalDistrict[] = [
  // Odisha
  { id: "or-ganjam", name: "Ganjam", state: "Odisha", latitude: 19.39, longitude: 84.87 },
  { id: "or-puri", name: "Puri", state: "Odisha", latitude: 19.81, longitude: 85.83 },
  { id: "or-jagatsinghpur", name: "Jagatsinghpur", state: "Odisha", latitude: 20.25, longitude: 86.17 },
  { id: "or-kendrapara", name: "Kendrapara", state: "Odisha", latitude: 20.5, longitude: 86.68 },
  { id: "or-balasore", name: "Balasore", state: "Odisha", latitude: 21.49, longitude: 86.93 },
  // Andhra Pradesh
  { id: "ap-srikakulam", name: "Srikakulam", state: "Andhra Pradesh", latitude: 18.3, longitude: 83.9 },
  { id: "ap-visakhapatnam", name: "Visakhapatnam", state: "Andhra Pradesh", latitude: 17.69, longitude: 83.22 },
  { id: "ap-kakinada", name: "Kakinada", state: "Andhra Pradesh", latitude: 16.99, longitude: 82.25 },
  { id: "ap-nellore", name: "Nellore", state: "Andhra Pradesh", latitude: 14.44, longitude: 79.98 },
  // West Bengal
  { id: "wb-south24pgs", name: "South 24 Parganas", state: "West Bengal", latitude: 21.93, longitude: 88.4 },
  { id: "wb-eastmidnapore", name: "East Midnapore", state: "West Bengal", latitude: 22.0, longitude: 87.9 },
  // Tamil Nadu
  { id: "tn-nagapattinam", name: "Nagapattinam", state: "Tamil Nadu", latitude: 10.77, longitude: 79.84 },
  { id: "tn-cuddalore", name: "Cuddalore", state: "Tamil Nadu", latitude: 11.75, longitude: 79.77 },
  { id: "tn-chennai", name: "Chennai", state: "Tamil Nadu", latitude: 13.08, longitude: 80.27 },
  { id: "tn-thoothukudi", name: "Thoothukudi", state: "Tamil Nadu", latitude: 8.76, longitude: 78.13 },
  // Gujarat (Arabian Sea)
  { id: "gj-kutch", name: "Kutch", state: "Gujarat", latitude: 22.8, longitude: 69.65 },
  { id: "gj-devbhumidwarka", name: "Devbhumi Dwarka", state: "Gujarat", latitude: 22.24, longitude: 69.0 },
  { id: "gj-porbandar", name: "Porbandar", state: "Gujarat", latitude: 21.64, longitude: 69.61 },
  { id: "gj-junagadh", name: "Junagadh", state: "Gujarat", latitude: 21.28, longitude: 70.47 },
  { id: "gj-bhavnagar", name: "Bhavnagar", state: "Gujarat", latitude: 21.76, longitude: 72.15 },
  // Maharashtra (Arabian Sea)
  { id: "mh-raigad", name: "Raigad", state: "Maharashtra", latitude: 18.24, longitude: 73.13 },
  { id: "mh-ratnagiri", name: "Ratnagiri", state: "Maharashtra", latitude: 16.99, longitude: 73.31 },
  { id: "mh-sindhudurg", name: "Sindhudurg", state: "Maharashtra", latitude: 16.36, longitude: 73.5 },
  { id: "mh-mumbaisuburban", name: "Mumbai Suburban", state: "Maharashtra", latitude: 19.09, longitude: 72.87 },
];
