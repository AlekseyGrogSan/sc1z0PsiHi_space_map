import type { Floor, POI, Space, RouteResponse } from './types'

// Векторные SVG-планы этажей 2000x1500 с фирменной темной палитрой
const floor1Svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 2000 1500" width="2000" height="1500">
  <defs>
    <pattern id="grid1" width="50" height="50" patternUnits="userSpaceOnUse">
      <path d="M 50 0 L 0 0 0 50" fill="none" stroke="#1e293b" stroke-width="1"/>
    </pattern>
  </defs>
  <!-- Фон -->
  <rect width="2000" height="1500" fill="#020617"/>
  <rect width="2000" height="1500" fill="url(#grid1)"/>
  
  <!-- Внешние стены здания -->
  <rect x="100" y="100" width="1800" height="1300" rx="16" fill="#0b1329" stroke="#334155" stroke-width="6"/>

  <!-- Зона: Главная сцена -->
  <rect x="700" y="150" width="600" height="320" rx="12" fill="#1e1b4b" stroke="#6366f1" stroke-width="3"/>
  <text x="1000" y="320" fill="#a5b4fc" font-family="system-ui, sans-serif" font-size="30" font-weight="bold" text-anchor="middle">Главная сцена (Main Stage)</text>

  <!-- Зона: Стенд ТТК Экспо -->
  <rect x="250" y="550" width="450" height="320" rx="8" fill="#172554" stroke="#e30613" stroke-width="4"/>
  <text x="475" y="705" fill="#ffffff" font-family="system-ui, sans-serif" font-size="28" font-weight="bold" text-anchor="middle">Стенд ТТК Экспо</text>
  <text x="475" y="740" fill="#f87171" font-family="system-ui, sans-serif" font-size="18" text-anchor="middle">Инновации связи и навигации</text>

  <!-- Зона: Стенд AI & Робототехники -->
  <rect x="750" y="550" width="500" height="320" rx="8" fill="#0f172a" stroke="#3b82f6" stroke-width="3"/>
  <text x="1000" y="705" fill="#93c5fd" font-family="system-ui, sans-serif" font-size="28" font-weight="bold" text-anchor="middle">Зона AI &amp; Робототехники</text>

  <!-- Зона: Партнеры и Wi-Fi -->
  <rect x="1300" y="550" width="450" height="320" rx="8" fill="#1e293b" stroke="#475569" stroke-width="3"/>
  <text x="1525" y="705" fill="#cbd5e1" font-family="system-ui, sans-serif" font-size="28" font-weight="bold" text-anchor="middle">Партнерский сектор &amp; Wi-Fi</text>

  <!-- Зона: Санузлы (WC) -->
  <rect x="200" y="1050" width="300" height="250" rx="8" fill="#1e293b" stroke="#0ea5e9" stroke-width="3"/>
  <text x="350" y="1175" fill="#7dd3fc" font-family="system-ui, sans-serif" font-size="26" font-weight="bold" text-anchor="middle">WC (Санузлы)</text>

  <!-- Зона: Кофе & Фудкорт -->
  <rect x="1450" y="1050" width="400" height="250" rx="8" fill="#451a03" stroke="#f97316" stroke-width="3"/>
  <text x="1650" y="1175" fill="#fed7aa" font-family="system-ui, sans-serif" font-size="26" font-weight="bold" text-anchor="middle">Кофе &amp; Фудкорт</text>

  <!-- Зона: Главный вход -->
  <rect x="750" y="1200" width="500" height="150" rx="8" fill="#14532d" stroke="#22c55e" stroke-width="3"/>
  <text x="1000" y="1285" fill="#86efac" font-family="system-ui, sans-serif" font-size="28" font-weight="bold" text-anchor="middle">Вход и Регистрация</text>

  <!-- Лифт / межэтажный переход -->
  <rect x="1650" y="250" width="180" height="150" rx="8" fill="#312e81" stroke="#818cf8" stroke-width="2"/>
  <text x="1740" y="335" fill="#c7d2fe" font-family="system-ui, sans-serif" font-size="20" font-weight="bold" text-anchor="middle">Лифт / 2F</text>

  <!-- Заголовок этажа -->
  <text x="160" y="170" fill="#94a3b8" font-family="system-ui, sans-serif" font-size="34" font-weight="bold">ЭТАЖ 1 (Выставочный зал)</text>
</svg>`

const floor2Svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 2000 1500" width="2000" height="1500">
  <defs>
    <pattern id="grid2" width="50" height="50" patternUnits="userSpaceOnUse">
      <path d="M 50 0 L 0 0 0 50" fill="none" stroke="#1e293b" stroke-width="1"/>
    </pattern>
  </defs>
  <rect width="2000" height="1500" fill="#020617"/>
  <rect width="2000" height="1500" fill="url(#grid2)"/>
  <rect x="100" y="100" width="1800" height="1300" rx="16" fill="#0b1329" stroke="#334155" stroke-width="6"/>

  <!-- Зал 1 -->
  <rect x="250" y="250" width="650" height="550" rx="12" fill="#1e1b4b" stroke="#818cf8" stroke-width="3"/>
  <text x="575" y="520" fill="#c7d2fe" font-family="system-ui, sans-serif" font-size="30" font-weight="bold" text-anchor="middle">Конференц-зал «Восток»</text>

  <!-- Зал 2 -->
  <rect x="1000" y="250" width="650" height="550" rx="12" fill="#1e1b4b" stroke="#818cf8" stroke-width="3"/>
  <text x="1325" y="520" fill="#c7d2fe" font-family="system-ui, sans-serif" font-size="30" font-weight="bold" text-anchor="middle">Конференц-зал «Запад»</text>

  <!-- VIP Lounge -->
  <rect x="350" y="900" width="600" height="350" rx="8" fill="#312e81" stroke="#a855f7" stroke-width="3"/>
  <text x="650" y="1070" fill="#e9d5ff" font-family="system-ui, sans-serif" font-size="28" font-weight="bold" text-anchor="middle">VIP Lounge &amp; Спикеры</text>

  <!-- Зона кофе-брейка -->
  <rect x="1050" y="900" width="600" height="350" rx="8" fill="#451a03" stroke="#f97316" stroke-width="3"/>
  <text x="1350" y="1070" fill="#fed7aa" font-family="system-ui, sans-serif" font-size="28" font-weight="bold" text-anchor="middle">Кофе-брейк зона</text>

  <!-- Лифт -->
  <rect x="1650" y="250" width="180" height="150" rx="8" fill="#312e81" stroke="#818cf8" stroke-width="2"/>
  <text x="1740" y="335" fill="#c7d2fe" font-family="system-ui, sans-serif" font-size="20" font-weight="bold" text-anchor="middle">Лифт / 1F</text>

  <text x="160" y="170" fill="#94a3b8" font-family="system-ui, sans-serif" font-size="34" font-weight="bold">ЭТАЖ 2 (Конференц-залы)</text>
</svg>`

export const floor1PlanUrl = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(floor1Svg)}`
export const floor2PlanUrl = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(floor2Svg)}`

export const mockFloors: Floor[] = [
  {
    id: 'floor-1-uuid',
    number: 1,
    title: '1 Этаж — Главный выставочный зал',
    plan_image_url: floor1PlanUrl,
    width: 2000,
    height: 1500,
    ppm: 25.0,
  },
  {
    id: 'floor-2-uuid',
    number: 2,
    title: '2 Этаж — Конференц-залы и VIP',
    plan_image_url: floor2PlanUrl,
    width: 2000,
    height: 1500,
    ppm: 25.0,
  },
]

export const mockPois: POI[] = [
  // 1. Стенд ТТК
  {
    id: 'poi-stand-ttk',
    floor_id: 'floor-1-uuid',
    title: 'Главный стенд ТТК',
    category: 'stand',
    description: 'Флагманский стенд компании ТТК: цифровые сервисы, индор-навигация, телеком и IoT-решения.',
    x: 475,
    y: 710,
    logo_url: 'https://images.unsplash.com/photo-1516321318423-f06f85e504b3?w=100&auto=format&fit=crop&q=80',
    panorama_id: 'pano-stand-ttk',
  },
  // 2. Стенд AI & Робототехники
  {
    id: 'poi-stand-ai',
    floor_id: 'floor-1-uuid',
    title: 'Стенд AI & Robotics',
    category: 'stand',
    description: 'Демонстрация роботов-помощников, моделей компьютерного зрения и AI-навигации внутри помещений.',
    x: 1000,
    y: 710,
    logo_url: null,
    panorama_id: 'pano-stand-ai',
  },
  // 3. Главная сцена
  {
    id: 'poi-main-stage',
    floor_id: 'floor-1-uuid',
    title: 'Главная сцена (Main Stage)',
    category: 'stage',
    description: 'Ключевые презентации, выступления спикеров, питчи стартапов и финальное награждение хакатона.',
    x: 1000,
    y: 320,
    logo_url: null,
    panorama_id: 'pano-main-stage',
  },
  // 4. Фудкорт & Кофе
  {
    id: 'poi-foodcourt',
    floor_id: 'floor-1-uuid',
    title: 'Кофе-поинт и Фудкорт',
    category: 'food',
    description: 'Авторский кофе, прохладительные напитки, свежие сэндвичи и лаундж-зона для отдыха участников.',
    x: 1650,
    y: 1175,
    logo_url: null,
    panorama_id: null,
  },
  // 5. Санузел
  {
    id: 'poi-wc-1',
    floor_id: 'floor-1-uuid',
    title: 'Санузлы (1 этаж)',
    category: 'wc',
    description: 'Мужской, женский и санузел, оборудованный для маломобильных посетителей.',
    x: 350,
    y: 1175,
    logo_url: null,
    panorama_id: null,
  },
  // Дополнительные важные точки для навигации
  {
    id: 'poi-entrance-1',
    floor_id: 'floor-1-uuid',
    title: 'Главный вход и Регистрация',
    category: 'entrance',
    description: 'Стойка регистрации посетителей, выдача бейджей, инфокиоск и гардероб.',
    x: 1000,
    y: 1285,
    logo_url: null,
    panorama_id: 'pano-entrance',
  },
  {
    id: 'poi-wifi-zone',
    floor_id: 'floor-1-uuid',
    title: 'Зона Wi-Fi и Зарядки',
    category: 'wifi',
    description: 'Высокоскоростная сеть ТТК Free Wi-Fi и стойки с быстрой зарядкой устройств.',
    x: 1525,
    y: 710,
    logo_url: null,
    panorama_id: null,
  },
  // Точки на 2 этаже
  {
    id: 'poi-conf-vostok',
    floor_id: 'floor-2-uuid',
    title: 'Конференц-зал «Восток»',
    category: 'stage',
    description: 'Секция докладов: Frontend архитектура, мобильные веб-приложения и 3D-графика в браузере.',
    x: 575,
    y: 520,
    logo_url: null,
    panorama_id: 'pano-conf-vostok',
  },
  {
    id: 'poi-vip-lounge',
    floor_id: 'floor-2-uuid',
    title: 'VIP Lounge & Менторы',
    category: 'food',
    description: 'Зона консультаций с техническими экспертами, менторские сессии и закрытые переговоры.',
    x: 650,
    y: 1070,
    logo_url: null,
    panorama_id: null,
  },
]

export const mockSpace: Space = {
  id: 'space-ttk-conf-2026',
  slug: 'ttk-conf-2026',
  title: 'IT-Конференция ТТК 2026',
  description: 'Главный выставочный павильон и конференц-залы ТТК. Индор-навигация и виртуальный 360° тур.',
  floors: mockFloors,
  pois: mockPois,
}

export const mockFallbackRoute: RouteResponse = {
  points: [
    { x: 1000, y: 1285, floor_id: 'floor-1-uuid' },
    { x: 1000, y: 1000, floor_id: 'floor-1-uuid' },
    { x: 475, y: 710, floor_id: 'floor-1-uuid' },
  ],
  distance_meters: 32.5,
  estimated_seconds: 28,
  steps: [
    { instruction: 'Начните движение от главного входа' },
    { instruction: 'Поверните налево в сторону выставочного сектора ТТК' },
    { instruction: 'Вы прибыли к Главному стенду ТТК' },
  ],
}
