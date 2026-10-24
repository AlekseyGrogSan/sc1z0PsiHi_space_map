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
  publish: (id: string | number) => client.patch(`/spaces/${id}/publish`),
  unpublish: (id: string | number) => client.patch(`/spaces/${id}/unpublish`),
  delete: (id: string | number) => client.delete(`/spaces/${id}`),
}

// Floors
export const floorsApi = {
  list: (spaceId: string | number) => client.get(`/spaces/${spaceId}/floors`),
  create: (spaceId: string | number, data: any) => client.post(`/spaces/${spaceId}/floors`, data),
  get: (floorId: string | number) => client.get(`/floors/${floorId}`),
  update: (floorId: string | number, data: any) => client.patch(`/floors/${floorId}`, data),
  delete: (floorId: string | number) => client.delete(`/floors/${floorId}`),
  uploadPlan: (floorId: string | number, formData: FormData) =>
    client.post(`/media/floors/${floorId}/plan/upload`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }),
}

// POIs
export const poisApi = {
  list: (floorId: string | number) => client.get(`/floors/${floorId}/pois`),
  create: (floorId: string | number, data: any) => client.post(`/floors/${floorId}/pois`, data),
  update: (poiId: string | number, data: any) => client.patch(`/pois/${poiId}`, data),
  delete: (poiId: string | number) => client.delete(`/pois/${poiId}`),
}

// Navigation graph
export const navApi = {
  listNodes: (floorId: string | number) => client.get(`/floors/${floorId}/nav-nodes`),
  createNode: (floorId: string | number, data: any) => client.post(`/floors/${floorId}/nav-nodes`, data),
  updateNode: (nodeId: string | number, data: any) => client.patch(`/nav-nodes/${nodeId}`, data),
  deleteNode: (nodeId: string | number) => client.delete(`/nav-nodes/${nodeId}`),
  listEdges: (floorId: string | number) => client.get(`/floors/${floorId}/nav-edges`),
  createEdge: (data: any) => client.post('/nav-edges', data),
  deleteEdge: (edgeId: string | number) => client.delete(`/nav-edges/${edgeId}`),
}