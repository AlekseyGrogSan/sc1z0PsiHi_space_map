import client from './client'

export { default } from './client'
export { panoramaApi } from './panoramaApi'

// Auth
export const authApi = {
  login: (data: any) => client.post('/auth/login', data),
  register: (data: any) => client.post('/auth/register', data),
}

// Spaces
export const spacesApi = {
  list: () => client.get('/spaces'),
  create: (data: any) => client.post('/spaces', data),
  get: (id: string | number) => client.get(`/spaces/${id}`),
  update: (id: string | number, data: any) => client.patch(`/spaces/${id}`, data),
  publish: (id: string | number) => client.patch(`/spaces/${id}/publish`, { is_published: true }),
  unpublish: (id: string | number) => client.patch(`/spaces/${id}/publish`, { is_published: false }),
  delete: (id: string | number) => client.delete(`/spaces/${id}`),
}

// Floors
export const floorsApi = {
  list: async (spaceId: string | number) => {
    const res = await spacesApi.get(spaceId)
    return { data: res.data?.floors || [] }
  },
  create: (spaceId: string | number, data: any) => {
    const payload = {
      title: data.title || data.name || 'Этаж',
      floor_number: Number(data.floor_number ?? data.level ?? 1),
      ppm: data.ppm ? Number(data.ppm) : 25.0,
    }
    return client.post(`/spaces/${spaceId}/floors`, payload)
  },
  get: (floorId: string | number) => client.get(`/floors/${floorId}`),
  update: (floorId: string | number, data: any) => client.patch(`/floors/${floorId}`, data),
  delete: (floorId: string | number) => client.delete(`/floors/${floorId}`),
  uploadPlan: (floorId: string | number, formData: FormData) =>
    client.post(`/media/floors/${floorId}/plan/upload`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }),
  deletePlan: (floorId: string | number) =>
    client.delete(`/media/floors/${floorId}/plan`),
  saveLayout: (floorId: string | number, layout_data: any) =>
    client.patch(`/floors/${floorId}`, { layout_data }),
}

// POIs
export const poisApi = {
  list: (floorId: string | number) => client.get(`/floors/${floorId}/pois`),
  create: (floorId: string | number, data: any) => {
    const payload = {
      title: data.title || data.name,
      category: data.category,
      description: data.description || '',
      x_coord: Number(data.x_coord ?? data.x),
      y_coord: Number(data.y_coord ?? data.y),
      panorama_id: data.panorama_id || undefined,
      yaw_in_panorama: data.yaw_in_panorama,
      pitch_in_panorama: data.pitch_in_panorama,
    }
    return client.post(`/floors/${floorId}/pois`, payload)
  },
  update: (poiId: string | number, data: any) => client.patch(`/pois/${poiId}`, data),
  delete: (poiId: string | number) => client.delete(`/pois/${poiId}`),
}

// Navigation graph
export const navApi = {
  getGraph: (floorId: string | number) => client.get(`/floors/${floorId}/navigation/graph`),
  saveGraph: (floorId: string | number, data: any) => client.put(`/floors/${floorId}/navigation/graph`, data),
  autoGraph: (floorId: string | number) => client.post(`/floors/${floorId}/navigation/auto-graph`),
  listTransitions: (spaceId: string | number) => client.get(`/spaces/${spaceId}/navigation/transitions`),
  createTransition: (spaceId: string | number, data: any) => client.post(`/spaces/${spaceId}/navigation/transitions`, data),
  deleteTransition: (spaceId: string | number, edgeId: string | number) =>
    client.delete(`/spaces/${spaceId}/navigation/transitions/${edgeId}`),
}