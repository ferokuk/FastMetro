<template>
  <Transition name="fade-up">
    <section class="route-summary">
      <div class="route-summary-header">
        <h3 class="route-summary-title">
          Маршрут: {{ path.from_station.name }} → {{ path.to_station.name }}
        </h3>
        <p class="route-summary-subtitle">
          {{ path.stations_count }} станций, {{ path.total_steps }} перегонов, {{ path.transfers_count }} пересадок
        </p>
      </div>

      <div class="route-summary-grid">
        <div class="route-summary-chip">
          <span class="route-summary-chip-label">Время в пути</span>
          <span class="route-summary-chip-value">
            {{ path.total_time_minutes.toFixed(0) }} мин
          </span>
        </div>
        <div class="route-summary-chip">
          <span class="route-summary-chip-label">Перегонов</span>
          <span class="route-summary-chip-value">
            {{ path.total_steps }}
          </span>
        </div>
        <div class="route-summary-chip">
          <span class="route-summary-chip-label">Станций</span>
          <span class="route-summary-chip-value">
            {{ path.stations_count }}
          </span>
        </div>
        <div class="route-summary-chip">
          <span class="route-summary-chip-label">Пересадок</span>
          <span class="route-summary-chip-value">
            {{ path.transfers_count }}
          </span>
        </div>
      </div>
    </section>
  </Transition>
</template>

<script setup lang="ts">
import type { PathResponse } from "../types/api";

defineProps<{
  path: PathResponse;
}>();
</script>

