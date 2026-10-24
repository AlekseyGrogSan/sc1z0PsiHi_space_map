export type PoiCategory =
  | 'stand'
  | 'food'
  | 'wc'
  | 'stage'
  | 'wifi'
  | 'entrance'
  | 'exit'
  | 'bench'
  | 'trash'
  | 'retail'
  | 'entertainment'
  | 'custom'
  | 'info'

export interface FloorLayout {
  rooms?: { id: string; title: string; x: number; y: number; width: number; height: number; color?: string }[]
  walls?: { id: string; x1: number; y1: number; x2: number; y2: number; thickness?: number }[]
  corridors?: { id: string; x1: number; y1: number; x2: number; y2: number; width?: number }[]
  obstacles?: { id: string; type: 'circle' | 'rect'; x: number; y: number; radius?: number; width?: number; height?: number; title?: string }[]
}

export interface Floor {
  id: string
  number: number
  title: string
  plan_image_url: string
  width: number
  height: number
  ppm: number
  layout_data?: FloorLayout | null
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
  is_published?: boolean
  floors: Floor[]
  pois: POI[]
}

export interface RoutePoint {
  x: number
  y: number
  floor_id: string
}

export interface RouteStep {
  kind?: string
  text?: string
  instruction?: string
  distance_meters?: number
  floor_id?: string
  target_floor?: number
}

export interface RouteResponse {
  points: RoutePoint[]
  distance_meters: number
  estimated_seconds: number
  steps: RouteStep[]
  total_distance_meters?: number
  estimated_time_seconds?: number
}
