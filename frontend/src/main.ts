import { createApp } from 'vue'
import 'leaflet/dist/leaflet.css'
import './style.css'
import App from './App.vue'
import router from './routes'

const app = createApp(App)
app.use(router)
app.mount('#app')