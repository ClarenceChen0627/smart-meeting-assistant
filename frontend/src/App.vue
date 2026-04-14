<template>
  <div class="app-container">
    <MeetingRoom />
  </div>
</template>

<script setup lang="ts">
import MeetingRoom from './components/MeetingRoom.vue'
</script>

<style scoped>
.app-container {
  width: 100%;
  height: 100%;
  display: flex;
  background-color: var(--color-bg-primary);
}
</style>
