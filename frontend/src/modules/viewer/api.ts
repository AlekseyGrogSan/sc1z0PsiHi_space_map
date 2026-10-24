import { apiClient } from '../../api/client'
import type { Space, RoutePoint, RouteResponse, Floor, POI } from './types'
import { mockSpace, mockFloors, mockPois } from './mocks'

/**
 * Расчет тестовой прямой линии (фоллбек навигации при недоступности бэкенда)
 */
export function generateStraightLineRoute(
  origin: RoutePoint,
  destination: RoutePoint
): RouteResponse {
  const isSameFloor = origin.floor_id === destination.floor_id
  const dx = destination.x - origin.x
  const dy = destination.y - origin.y
  const distancePx = Math.sqrt(dx * dx + dy * dy)

  // При масштабе по умолчанию ~25 ppm (пикселей на метр)
  const distanceMeters = Math.round((distancePx / 25) * 10) / 10
  // Средняя скорость шага ~ 1.2 м/с
  const estimatedSeconds = Math.max(5, Math.round(distanceMeters / 1.2))

  if (isSameFloor) {
    // Формируем прямую линию с несколькими промежуточными точками для плавной анимации и отрисовки
    const stepsCount = 5
    const points: RoutePoint[] = []
    for (let i = 0; i <= stepsCount; i++) {
      const t = i / stepsCount
      points.push({
        x: Math.round(origin.x + dx * t),
        y: Math.round(origin.y + dy * t),
        floor_id: origin.floor_id,
      })
    }

    return {
      points,
      distance_meters: distanceMeters,
      estimated_seconds: estimatedSeconds,
      steps: [
        { instruction: 'Двигайтесь по прямой к точке назначения' },
        { instruction: 'Вы прибыли в пункт назначения' },
      ],
    }
  }

  // Маршрут между разными этажами
  const points: RoutePoint[] = [
    { ...origin },
    {
      x: Math.round((origin.x + destination.x) / 2),
      y: Math.round((origin.y + destination.y) / 2),
      floor_id: origin.floor_id,
    },
    {
      x: Math.round((origin.x + destination.x) / 2),
      y: Math.round((origin.y + destination.y) / 2),
      floor_id: destination.floor_id,
    },
    { ...destination },
  ]

  return {
    points,
    distance_meters: distanceMeters + 25,
    estimated_seconds: estimatedSeconds + 40,
    steps: [
      { instruction: 'Следуйте к лифту или межэтажной лестнице' },
      { instruction: 'Перейдите на целевой этаж', target_floor: 2 },
      { instruction: 'Продолжайте движение к точке назначения' },
      { instruction: 'Вы прибыли в пункт назначения' },
    ],
  }
}

/**
 * Получение пространства по его slug с бэкенда (GET /public/spaces/${slug})
 * С автоматическим возвратом мок-данных при ошибке/отсутствии бэка.
 */
export async function getSpaceBySlug(slug: string): Promise<Space> {
  try {
    const { data } = await apiClient.get<any>(`/public/spaces/${slug}`)

    if (!data) {
      throw new Error('Пустой ответ от сервера')
    }

    // Приведение структуры этажей с бэкенда к интерфейсу Floor
    const floors: Floor[] = Array.isArray(data.floors) && data.floors.length > 0
      ? data.floors.map((f: any, idx: number) => ({
          id: String(f.id || `floor-${idx + 1}`),
          number: typeof f.number === 'number' ? f.number : (f.floor_number ?? (idx + 1)),
          title: f.title || `Этаж ${idx + 1}`,
          plan_image_url: f.plan_image_url || mockFloors[idx % mockFloors.length]?.plan_image_url || '',
          width: f.width ?? f.width_px ?? 2000,
          height: f.height ?? f.height_px ?? 1500,
          ppm: f.ppm ?? 25.0,
        }))
      : mockFloors

    // Приведение точек интереса
    let rawPois: any[] = Array.isArray(data.pois) && data.pois.length > 0 ? data.pois : []
    if (rawPois.length === 0 && Array.isArray(data.floors)) {
      rawPois = data.floors.flatMap((f: any) => f.pois || [])
    }

    const pois: POI[] = rawPois.length > 0
      ? rawPois.map((p: any) => ({
          id: String(p.id),
          floor_id: String(p.floor_id),
          title: p.title,
          category: p.category || 'stand',
          description: p.description || '',
          x: Number(p.x ?? p.x_coord ?? 0),
          y: Number(p.y ?? p.y_coord ?? 0),
          logo_url: p.logo_url ?? null,
          panorama_id: p.panorama_id ?? null,
        }))
      : (floors.length > 0
          ? mockPois.map((p, idx) => ({
              ...p,
              floor_id: floors[idx % floors.length].id,
            }))
          : mockPois)

    return {
      id: String(data.id || mockSpace.id),
      slug: data.slug || slug,
      title: data.title || mockSpace.title,
      description: data.description || mockSpace.description,
      is_published: data.is_published ?? true,
      floors,
      pois,
    }
  } catch (error) {
    console.warn(
      `[getSpaceBySlug] Не удалось загрузить пространство "${slug}" с бэкенда. Используются мок-данные.`,
      error
    )
    return {
      ...mockSpace,
      slug: slug || mockSpace.slug,
    }
  }
}

/**
 * Построение маршрута (POST /spaces/{space_id}/navigation/route)
 * С фоллбеком на тестовую прямую линию при ошибке/отсутствии бэка.
 */
export async function getRoute(body: {
  origin: RoutePoint
  destination: RoutePoint
  spaceId?: string
  to_poi_id?: string
}): Promise<RouteResponse> {
  try {
    if (body.spaceId && (body.to_poi_id || (body.destination as any)?.id)) {
      const payload = {
        floor_id: body.origin.floor_id,
        x: body.origin.x,
        y: body.origin.y,
        to_poi_id: body.to_poi_id || (body.destination as any)?.id,
      }
      const { data } = await apiClient.post<RouteResponse>(`/spaces/${body.spaceId}/navigation/route`, payload)
      if (data && Array.isArray(data.points) && data.points.length > 0) {
        return data
      }
    }
    const { data } = await apiClient.post<RouteResponse>('/navigation/route', body)
    if (data && Array.isArray(data.points) && data.points.length > 0) {
      return data
    }
    throw new Error('Маршрут от сервера пуст или имеет некорректный формат')
  } catch (error) {
    console.warn(
      '[getRoute] Не удалось построить маршрут через бэкенд. Применен фоллбек на прямую линию.',
      error
    )
    return generateStraightLineRoute(body.origin, body.destination)
  }
}
