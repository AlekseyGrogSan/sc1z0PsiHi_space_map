export type PoiCategory =
  | 'stand'
  | 'food'
  | 'wc'
  | 'stage'
  | 'wifi'
  | 'entrance'
  | 'info'

export interface Floor {
  id: string
  number: number
  title: string
  plan_image_url: string
  width: number
  height: number
  ppm: number
}

export interface POI {
  id: string
  floor_id: string
  title: string
  category: PoiCategory
  description: string
  x: number
  y: number
  logo_url?: string | null
  panorama_id?: string | null
}

export interface Space {
  id: string
  slug: string
  title: string
  description: string
  floors: Floor[]
  pois: POI[]
}

export interface RoutePoint {
  x: number
  y: number
  floor_id: string
}

export interface RouteStep {
  instruction: string
  target_floor?: number
}

export interface RouteResponse {
  points: RoutePoint[]
  distance_meters: number
  estimated_seconds: number
  steps: {
    instruction: string
    target_floor?: number
  }[]
}
