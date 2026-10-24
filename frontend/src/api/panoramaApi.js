import axios from 'axios';

const api = axios.create({
    baseURL: 'http://localhost:8000/api/v1'
});

export const panoramaApi = {
    getPanorama: (id) => api.get(`/panoramas/${id}`),

    getUploadUrl: (id) => api.post(`/panoramas/${id}/upload-ready-url`),

    uploadStitchFrame: (id, formData) => api.post(`/panoramas/${id}/stitch-session`, formData),

    createConnection: (data) => api.post(`/panoramas/connections`, data)
};