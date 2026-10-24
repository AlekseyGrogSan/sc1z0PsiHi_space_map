import client from './client'

// Auth
export const authApi = {
  login: (data) => client.post('/auth/login', data),
  register: (data) => client.post('/auth/register', data),
}

// Spaces
export const spacesApi = {
  list: () => client.get('/spaces'),
  create: (data) => client.post('/spaces', data),
  get: (id) => client.get(`/spaces/${id}`),
  update: (id, data) => client.patch(`/spaces/${id}`, data),
  publish: (id) => client.patch(`/spaces/${id}/publish`),
  unpublish: (id) => client.patch(`/spaces/${id}/unpublish`),
  delete: (id) => client.delete(`/spaces/${id}`),
}

// Floors
export const floorsApi = {
  list: (spaceId) => client.get(`/spaces/${spaceId}/floors`),
  create: (spaceId, data) => client.post(`/spaces/${spaceId}/floors`, data),
  get: (floorId) => client.get(`/floors/${floorId}`),
  update: (floorId, data) => client.patch(`/floors/${floorId}`, data),
  delete: (floorId) => client.delete(`/floors/${floorId}`),
  uploadPlan: (floorId, formData) =>
    client.post(`/media/floors/${floorId}/plan/upload`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }),
}

// POIs
export const poisApi = {
  list: (floorId) => client.get(`/floors/${floorId}/pois`),
  create: (floorId, data) => client.post(`/floors/${floorId}/pois`, data),
  update: (poiId, data) => client.patch(`/pois/${poiId}`, data),
  delete: (poiId) => client.delete(`/pois/${poiId}`),
}

// Navigation graph
export const navApi = {
  listNodes: (floorId) => client.get(`/floors/${floorId}/nav-nodes`),
  createNode: (floorId, data) => client.post(`/floors/${floorId}/nav-nodes`, data),
  updateNode: (nodeId, data) => client.patch(`/nav-nodes/${nodeId}`, data),
  deleteNode: (nodeId) => client.delete(`/nav-nodes/${nodeId}`),
  listEdges: (floorId) => client.get(`/floors/${floorId}/nav-edges`),
  createEdge: (data) => client.post('/nav-edges', data),
  deleteEdge: (edgeId) => client.delete(`/nav-edges/${edgeId}`),
}
