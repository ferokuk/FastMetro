<template>
  <Transition name="fade-up">
    <section class="route-summary">
      <div class="route-summary-header">
        <h3 class="route-summary-title">
          Маршрут: {{ path.from_station.name }} → {{ path.to_station.name }}
        </h3>
      </div>

      <div class="route-summary-grid">
        <div class="route-summary-chip">
          <span class="route-summary-chip-label">Время в пути</span>
          <span class="route-summary-chip-value">
            {{ path.total_time_minutes.toFixed(0) }} мин
            <span
              v-if="hasFactors"
              class="route-summary-chip-base"
              :title="`Базовое время без факторов: ${path.base_total_minutes.toFixed(0)} мин`"
            >
              ({{ path.base_total_minutes.toFixed(0) }})
            </span>
          </span>
        </div>
        <div class="route-summary-chip">
          <span class="route-summary-chip-label">Пересадок</span>
          <span class="route-summary-chip-value">{{ path.transfers_count }}</span>
        </div>
        <button
          type="button"
          class="route-summary-info-btn"
          :aria-expanded="showDetails"
          :title="showDetails ? 'Скрыть детали' : 'Показать детали'"
          @click="showDetails = !showDetails"
        >
          i
        </button>
      </div>

      <Transition name="fade-up">
        <div v-if="showDetails" class="route-summary-details">
          <div class="route-summary-details-row">
            <span class="route-summary-details-label">Станций</span>
            <span class="route-summary-details-value">{{ path.stations_count }}</span>
          </div>
          <div class="route-summary-details-row">
            <span class="route-summary-details-label">Перегонов</span>
            <span class="route-summary-details-value">{{ path.total_steps }}</span>
          </div>

          <div class="route-summary-details-row">
            <span class="route-summary-details-label">Расчёт для</span>
            <span class="route-summary-details-value">{{ contextLabel }}</span>
          </div>

          <div v-if="hasFactors" class="route-summary-factors">
            <div class="route-summary-factors-label">Действующие факторы:</div>
            <div class="route-summary-factors-list">
              <span
                v-for="f in path.applied_factors_summary"
                :key="f.name"
                class="route-summary-factor-chip"
                :title="`${f.segments_affected} сегментов`"
              >
                {{ f.name }} ×{{ f.multiplier.toFixed(2) }}
              </span>
            </div>
          </div>

          <div v-if="hasBreakdown" class="route-summary-segments">
            <div class="route-summary-factors-label">Разбор по сегментам:</div>
            <ol class="route-summary-segments-list">
              <li
                v-for="(step, i) in path.path.slice(1)"
                :key="step.station_id + '-' + i"
                class="route-summary-segment"
              >
                <span class="route-summary-segment-name">
                  {{ step.is_transfer ? "↪" : "→" }} {{ step.station_name }}
                </span>
                <span class="route-summary-segment-time">
                  <template v-if="step.base_minutes != null && step.final_minutes != null">
                    {{ step.base_minutes.toFixed(1) }}
                    <template v-if="step.multiplier != null && step.multiplier !== 1">
                      × {{ step.multiplier.toFixed(2) }} = {{ step.final_minutes.toFixed(1) }}
                    </template>
                    мин
                  </template>
                </span>
                <span
                  v-if="step.factors_applied.length"
                  class="route-summary-segment-factors"
                >
                  {{ step.factors_applied.join(", ") }}
                </span>
              </li>
            </ol>
          </div>
        </div>
      </Transition>
    </section>
  </Transition>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import type { PathResponse } from "../types/api";

const props = defineProps<{
  path: PathResponse;
}>();

const showDetails = ref(false);

const hasFactors = computed(() => props.path.applied_factors_summary.length > 0);
const hasBreakdown = computed(() => props.path.path.length > 1);

const WEEKDAY_NAMES = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];
const WEATHER_LABELS: Record<string, string> = {
  clear: "ясно",
  rain: "дождь",
  snow: "снег",
  fog: "туман",
};

const contextLabel = computed(() => {
  const ctx = props.path.context;
  const day = WEEKDAY_NAMES[ctx.weekday] ?? "?";
  const hour = String(ctx.hour).padStart(2, "0");
  const weather = WEATHER_LABELS[ctx.weather] ?? ctx.weather;
  return `${day} ${hour}:00, ${weather}`;
});
</script>

<style scoped>
.route-summary-chip-base {
  font-size: 0.85em;
  opacity: 0.6;
  text-decoration: line-through;
  margin-left: 4px;
}
.route-summary-info-btn {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: 1px solid rgba(160, 180, 220, 0.4);
  background: rgba(120, 140, 200, 0.15);
  color: #e5e7eb;
  font-family: Georgia, "Times New Roman", serif;
  font-style: italic;
  font-weight: 700;
  font-size: 1rem;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
  align-self: center;
  justify-self: end;
}
.route-summary-info-btn:hover {
  background: rgba(140, 160, 220, 0.28);
  border-color: rgba(180, 200, 240, 0.65);
}
.route-summary-info-btn[aria-expanded="true"] {
  background: rgba(140, 160, 220, 0.35);
  border-color: rgba(200, 220, 255, 0.8);
}

.route-summary-details {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
}
.route-summary-details-row {
  display: flex;
  justify-content: space-between;
  padding: 3px 0;
  font-size: 0.9em;
}
.route-summary-details-label {
  opacity: 0.75;
}
.route-summary-details-value {
  font-variant-numeric: tabular-nums;
}

.route-summary-factors {
  margin-top: 12px;
}
.route-summary-factors-label {
  font-size: 0.85em;
  opacity: 0.75;
  margin-bottom: 6px;
}
.route-summary-factors-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.route-summary-factor-chip {
  background: rgba(120, 140, 200, 0.2);
  border: 1px solid rgba(160, 180, 220, 0.3);
  border-radius: 999px;
  padding: 3px 10px;
  font-size: 0.8em;
  white-space: nowrap;
}

.route-summary-segments {
  margin-top: 12px;
  font-size: 0.85em;
}
.route-summary-segments-list {
  list-style: none;
  padding-left: 0;
  margin: 0;
  max-height: 280px;
  overflow-y: auto;
}
.route-summary-segment {
  display: grid;
  grid-template-columns: 1fr auto;
  column-gap: 8px;
  padding: 4px 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}
.route-summary-segment-name {
  font-weight: 500;
}
.route-summary-segment-time {
  opacity: 0.85;
  font-variant-numeric: tabular-nums;
}
.route-summary-segment-factors {
  grid-column: 1 / -1;
  font-size: 0.85em;
  opacity: 0.6;
  font-style: italic;
}
</style>
