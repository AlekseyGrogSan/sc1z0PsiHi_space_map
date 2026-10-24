<script setup lang="ts">
import { RouterView } from 'vue-router'
</script>

<template>
  <div class="w-full h-full min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans select-none overflow-hidden">
    <RouterView />
  </div>
</template>

<style>
/* Запрет системного оверскролла на мобильных устройствах */
html,
body,
#app {
  width: 100%;
  height: 100%;
  margin: 0;
  padding: 0;
  overflow: hidden;
  background-color: #020617;
}
</style>
