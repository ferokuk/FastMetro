<template>
  <div class="factors-panel-wrapper">
    <button
      type="button"
      class="factors-toggle"
      :class="{ 'factors-toggle-active': isOpen }"
      :aria-expanded="isOpen"
      :title="isOpen ? 'Скрыть коэффициенты' : 'Коэффициенты времени'"
      @click="toggle"
    >
      <span class="factors-toggle-icon">⚙</span>
      <span class="factors-toggle-label">Коэффициенты</span>
    </button>

    <Transition name="fade-down">
      <div v-if="isOpen" class="factors-panel">
        <header class="factors-panel-header">
          <h3>Коэффициенты времени</h3>
          <button
            type="button"
            class="factors-close"
            title="Закрыть"
            @click="isOpen = false"
          >
            ×
          </button>
        </header>

        <p class="factors-panel-hint">
          Множители применяются к сегментам/пересадкам при расчёте маршрута.
          Чтобы изменить значения, введите admin-ключ.
        </p>

        <label class="factors-apikey-field">
          <span>API-ключ (для редактирования)</span>
          <input
            v-model="apiKey"
            type="password"
            autocomplete="off"
            placeholder="X-API-Key"
          />
        </label>

        <nav class="factors-tabs" role="tablist">
          <button
            v-for="tab in TABS"
            :key="tab.value"
            type="button"
            role="tab"
            :aria-selected="activeTab === tab.value"
            class="factors-tab"
            :class="{ 'factors-tab-active': activeTab === tab.value }"
            @click="activeTab = tab.value"
          >
            {{ tab.label }}
            <span class="factors-tab-count">{{ countByType(tab.value) }}</span>
          </button>
        </nav>

        <div v-if="errorMessage" class="factors-error">{{ errorMessage }}</div>

        <div v-if="isLoading && !factors.length" class="factors-loading">
          Загружаем…
        </div>

        <template v-else>
          <div v-if="activeTab === 'weather'" class="weather-current">
            <div class="weather-current-header">
              <span class="weather-current-title">Текущая погода</span>
              <span v-if="weatherState" class="weather-current-meta">
                {{ sourceLabel(weatherState.source) }}
                <template v-if="updatedAtLabel"> · {{ updatedAtLabel }}</template>
              </span>
            </div>
            <div class="weather-current-options">
              <label
                v-for="opt in WEATHER_OPTIONS"
                :key="opt.value"
                class="weather-option"
                :class="{ 'weather-option-active': weatherState?.condition === opt.value }"
              >
                <input
                  type="radio"
                  name="weather"
                  :value="opt.value"
                  :checked="weatherState?.condition === opt.value"
                  :disabled="!canEdit || weatherSaving"
                  @change="onWeatherChange(opt.value)"
                />
                <span class="weather-option-icon">{{ opt.icon }}</span>
                <span class="weather-option-label">{{ opt.label }}</span>
              </label>
            </div>
            <p v-if="!canEdit" class="weather-current-hint">
              Введите API-ключ выше, чтобы изменить вручную.
            </p>
          </div>

          <ul v-if="filteredFactors.length" class="factors-list">
            <li
              v-for="f in filteredFactors"
              :key="f.id"
              class="factors-row"
              :class="{ 'factors-row-disabled': !f.is_active }"
            >
              <div class="factors-row-main">
                <span class="factors-row-name">{{ f.name }}</span>
                <span class="factors-row-meta">
                  {{ edgeScopeLabel(f) }}
                  <template v-if="f.hour_start != null && f.hour_end != null">
                    · {{ formatHour(f.hour_start) }}–{{ formatHour(f.hour_end) }}
                  </template>
                  <template v-if="f.weekday_mask != null">
                    · {{ weekdayLabel(f.weekday_mask) }}
                  </template>
                  <template v-if="f.line_id">· линия {{ f.line_id }}</template>
                  <template v-if="f.weather_condition">
                    · {{ weatherLabel(f.weather_condition) }}
                  </template>
                </span>
              </div>

              <div class="factors-row-controls">
                <label class="factors-active-toggle" :title="f.is_active ? 'Активен' : 'Выключен'">
                  <input
                    type="checkbox"
                    :checked="editedState(f).is_active"
                    :disabled="!canEdit"
                    @change="onToggleActive(f, $event)"
                  />
                </label>
                <input
                  class="factors-multiplier"
                  type="number"
                  step="0.05"
                  min="1"
                  max="2"
                  :value="editedState(f).multiplier"
                  :disabled="!canEdit"
                  @input="onMultChange(f, $event)"
                />
                <button
                  type="button"
                  class="factors-save"
                  :disabled="!canEdit || !isDirty(f) || savingIds.has(f.id)"
                  @click="saveFactor(f)"
                >
                  {{ savingIds.has(f.id) ? "…" : "Сохранить" }}
                </button>
              </div>
            </li>
          </ul>
          <p v-else class="factors-empty">
            Нет факторов в этой категории.
          </p>
        </template>
      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from "vue";
import { fetchFactors, fetchWeather, setWeather, updateFactor } from "../api/client";
import type { Factor, FactorType, WeatherCondition, WeatherState } from "../types/api";

const isOpen = ref(false);
const factors = ref<Factor[]>([]);
const isLoading = ref(false);
const errorMessage = ref<string | null>(null);
const apiKey = ref("");
const edits = reactive<Record<number, { multiplier: number; is_active: boolean }>>({});
const savingIds = ref(new Set<number>());

const activeTab = ref<FactorType>("rush_hour");
const weatherState = ref<WeatherState | null>(null);
const weatherSaving = ref(false);
const nowTick = ref(Date.now()); // re-render relative timestamp
let weatherTimer: ReturnType<typeof setInterval> | null = null;
let nowTimer: ReturnType<typeof setInterval> | null = null;

const TABS: { value: FactorType; label: string }[] = [
  { value: "rush_hour", label: "Час пик" },
  { value: "line", label: "Линия" },
  { value: "weekend", label: "Выходные" },
  { value: "weather", label: "Погода" }
];

const WEATHER_OPTIONS: { value: WeatherCondition; label: string; icon: string }[] = [
  { value: "clear", label: "Ясно", icon: "☀" },
  { value: "rain", label: "Дождь", icon: "🌧" },
  { value: "snow", label: "Снег", icon: "❄" },
  { value: "fog", label: "Туман", icon: "🌫" }
];

const canEdit = computed(() => apiKey.value.trim().length > 0);

const filteredFactors = computed(() =>
  factors.value.filter((f) => f.factor_type === activeTab.value)
);

function countByType(t: FactorType) {
  return factors.value.filter((f) => f.factor_type === t).length;
}

async function loadFactors() {
  try {
    isLoading.value = true;
    errorMessage.value = null;
    factors.value = await fetchFactors();
    for (const f of factors.value) {
      edits[f.id] = { multiplier: f.multiplier, is_active: f.is_active };
    }
  } catch (e) {
    console.error(e);
    errorMessage.value = "Не удалось загрузить коэффициенты.";
  } finally {
    isLoading.value = false;
  }
}

async function loadWeather() {
  try {
    weatherState.value = await fetchWeather();
  } catch (e) {
    console.error("fetchWeather failed", e);
  }
}

function startWeatherPolling() {
  stopWeatherPolling();
  loadWeather();
  weatherTimer = setInterval(loadWeather, 60_000);
  nowTimer = setInterval(() => {
    nowTick.value = Date.now();
  }, 30_000);
}

function stopWeatherPolling() {
  if (weatherTimer != null) {
    clearInterval(weatherTimer);
    weatherTimer = null;
  }
  if (nowTimer != null) {
    clearInterval(nowTimer);
    nowTimer = null;
  }
}

function toggle() {
  isOpen.value = !isOpen.value;
}

watch(isOpen, (v) => {
  if (v) {
    errorMessage.value = null;
    if (factors.value.length === 0) loadFactors();
    if (activeTab.value === "weather") startWeatherPolling();
  } else {
    stopWeatherPolling();
  }
});

watch(activeTab, (v) => {
  if (!isOpen.value) return;
  if (v === "weather") startWeatherPolling();
  else stopWeatherPolling();
});

onBeforeUnmount(stopWeatherPolling);

async function onWeatherChange(value: WeatherCondition) {
  if (!canEdit.value || weatherSaving.value) return;
  if (weatherState.value?.condition === value) return;
  weatherSaving.value = true;
  try {
    errorMessage.value = null;
    weatherState.value = await setWeather(value, apiKey.value.trim());
  } catch (e) {
    console.error(e);
    errorMessage.value =
      e instanceof Error && e.message.includes("403")
        ? "Неверный API-ключ"
        : "Не удалось сменить погоду";
  } finally {
    weatherSaving.value = false;
  }
}

function editedState(f: Factor) {
  return edits[f.id] ?? { multiplier: f.multiplier, is_active: f.is_active };
}

function isDirty(f: Factor) {
  const s = edits[f.id];
  if (!s) return false;
  return s.multiplier !== f.multiplier || s.is_active !== f.is_active;
}

function onToggleActive(f: Factor, ev: Event) {
  const checked = (ev.target as HTMLInputElement).checked;
  edits[f.id] = { ...editedState(f), is_active: checked };
}

function onMultChange(f: Factor, ev: Event) {
  const raw = (ev.target as HTMLInputElement).value;
  const parsed = parseFloat(raw);
  if (!Number.isFinite(parsed)) return;
  edits[f.id] = { ...editedState(f), multiplier: parsed };
}

async function saveFactor(f: Factor) {
  if (!canEdit.value || !isDirty(f)) return;
  const s = edits[f.id];
  if (s.multiplier < 1 || s.multiplier > 2) {
    errorMessage.value = "Множитель должен быть в диапазоне 1.0–2.0";
    return;
  }
  savingIds.value.add(f.id);
  try {
    errorMessage.value = null;
    const payload = {
      name: f.name,
      factor_type: f.factor_type,
      multiplier: s.multiplier,
      applies_to_segment: f.applies_to_segment,
      applies_to_transfer: f.applies_to_transfer,
      line_id: f.line_id,
      hour_start: f.hour_start,
      hour_end: f.hour_end,
      weekday_mask: f.weekday_mask,
      weather_condition: f.weather_condition,
      is_active: s.is_active,
      priority: f.priority
    };
    const updated = await updateFactor(f.id, payload, apiKey.value.trim());
    const i = factors.value.findIndex((x) => x.id === f.id);
    if (i >= 0) factors.value[i] = updated;
    edits[f.id] = { multiplier: updated.multiplier, is_active: updated.is_active };
  } catch (e) {
    console.error(e);
    errorMessage.value =
      e instanceof Error && e.message.includes("403")
        ? "Неверный API-ключ"
        : "Не удалось сохранить изменения";
  } finally {
    savingIds.value.delete(f.id);
  }
}

function edgeScopeLabel(f: Factor) {
  if (f.applies_to_segment && f.applies_to_transfer) return "перегоны + переходы";
  if (f.applies_to_segment) return "перегоны";
  if (f.applies_to_transfer) return "переходы";
  return "—";
}

function formatHour(h: number) {
  return String(h).padStart(2, "0") + ":00";
}

const WEEKDAY_NAMES = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];

function weekdayLabel(mask: number) {
  const days: string[] = [];
  for (let i = 0; i < 7; i++) {
    if (mask & (1 << i)) days.push(WEEKDAY_NAMES[i]);
  }
  if (days.length === 7) return "ежедневно";
  if (days.length === 5 && mask === 0b0011111) return "будни";
  if (days.length === 2 && mask === 0b1100000) return "выходные";
  return days.join(", ");
}

function weatherLabel(w: string) {
  const map: Record<string, string> = {
    clear: "ясно",
    rain: "дождь",
    snow: "снег",
    fog: "туман"
  };
  return map[w] ?? w;
}

function sourceLabel(src: WeatherState["source"]) {
  return src === "openweather" ? "OpenWeather" : "ручной";
}

const updatedAtLabel = computed(() => {
  const ts = weatherState.value?.updated_at;
  if (!ts) return null;
  // touch nowTick for reactivity
  void nowTick.value;
  const updated = Date.parse(ts);
  if (!Number.isFinite(updated)) return null;
  const diffSec = Math.max(0, Math.round((Date.now() - updated) / 1000));
  if (diffSec < 30) return "только что";
  if (diffSec < 60) return `${diffSec} сек назад`;
  const diffMin = Math.round(diffSec / 60);
  if (diffMin < 60) return `${diffMin} мин назад`;
  const diffH = Math.round(diffMin / 60);
  if (diffH < 24) return `${diffH} ч назад`;
  const diffD = Math.round(diffH / 24);
  return `${diffD} дн назад`;
});
</script>

<style scoped>
.factors-panel-wrapper {
  position: fixed;
  top: 16px;
  right: 16px;
  z-index: 40;
}

.factors-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border-radius: 999px;
  border: 1px solid rgba(160, 180, 220, 0.4);
  background: rgba(15, 23, 42, 0.82);
  backdrop-filter: blur(8px);
  color: #e5e7eb;
  font-size: 0.9em;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.3);
}
.factors-toggle:hover {
  background: rgba(30, 41, 59, 0.9);
  border-color: rgba(180, 200, 240, 0.65);
}
.factors-toggle-active {
  background: rgba(99, 102, 241, 0.35);
  border-color: rgba(165, 180, 252, 0.8);
}
.factors-toggle-icon {
  font-size: 1em;
  opacity: 0.9;
}

.factors-panel {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  width: 460px;
  max-width: calc(100vw - 32px);
  max-height: calc(100vh - 80px);
  overflow-y: auto;
  background: rgba(15, 23, 42, 0.96);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(55, 65, 81, 0.7);
  border-radius: 12px;
  box-shadow: 0 12px 36px rgba(0, 0, 0, 0.5);
  padding: 16px;
  color: #e5e7eb;
}

.factors-panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.factors-panel-header h3 {
  margin: 0;
  font-size: 1rem;
}
.factors-close {
  width: 26px;
  height: 26px;
  border-radius: 6px;
  border: none;
  background: transparent;
  color: #e5e7eb;
  font-size: 1.2rem;
  cursor: pointer;
}
.factors-close:hover {
  background: rgba(255, 255, 255, 0.08);
}

.factors-panel-hint {
  margin: 0 0 12px;
  font-size: 0.8em;
  opacity: 0.7;
  line-height: 1.4;
}

.factors-apikey-field {
  display: block;
  margin-bottom: 12px;
}
.factors-apikey-field span {
  display: block;
  font-size: 0.8em;
  opacity: 0.75;
  margin-bottom: 4px;
}
.factors-apikey-field input {
  width: 100%;
  padding: 6px 10px;
  border-radius: 8px;
  border: 1px solid rgba(55, 65, 81, 0.7);
  background: rgba(0, 0, 0, 0.35);
  color: #e5e7eb;
  font-size: 0.9em;
  box-sizing: border-box;
}
.factors-apikey-field input:focus {
  outline: none;
  border-color: rgba(165, 180, 252, 0.6);
}

.factors-tabs {
  display: flex;
  gap: 4px;
  margin-bottom: 12px;
  background: rgba(0, 0, 0, 0.25);
  padding: 4px;
  border-radius: 10px;
}
.factors-tab {
  flex: 1;
  padding: 6px 8px;
  border-radius: 7px;
  border: none;
  background: transparent;
  color: #cbd5e1;
  font-size: 0.82em;
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  transition: background 0.15s, color 0.15s;
}
.factors-tab:hover {
  color: #ffffff;
  background: rgba(255, 255, 255, 0.05);
}
.factors-tab-active {
  background: rgba(99, 102, 241, 0.35);
  color: #ffffff;
}
.factors-tab-count {
  font-size: 0.85em;
  opacity: 0.65;
  font-variant-numeric: tabular-nums;
}

.factors-error {
  background: rgba(220, 38, 38, 0.18);
  border: 1px solid rgba(248, 113, 113, 0.5);
  padding: 6px 10px;
  border-radius: 8px;
  font-size: 0.85em;
  margin-bottom: 10px;
}

.factors-loading,
.factors-empty {
  text-align: center;
  padding: 20px;
  opacity: 0.7;
  font-size: 0.9em;
}

.weather-current {
  margin-bottom: 14px;
  padding: 12px;
  border-radius: 10px;
  background: rgba(30, 41, 59, 0.55);
  border: 1px solid rgba(55, 65, 81, 0.5);
}
.weather-current-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 10px;
}
.weather-current-title {
  font-weight: 600;
  font-size: 0.9em;
}
.weather-current-meta {
  font-size: 0.75em;
  opacity: 0.7;
}
.weather-current-options {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 6px;
}
.weather-option {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 8px 4px;
  border-radius: 8px;
  border: 1px solid rgba(55, 65, 81, 0.5);
  background: rgba(0, 0, 0, 0.25);
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
  font-size: 0.8em;
}
.weather-option:hover {
  background: rgba(255, 255, 255, 0.05);
}
.weather-option-active {
  background: rgba(99, 102, 241, 0.3);
  border-color: rgba(165, 180, 252, 0.8);
}
.weather-option input {
  display: none;
}
.weather-option-icon {
  font-size: 1.4em;
}
.weather-option-label {
  font-weight: 500;
}
.weather-current-hint {
  margin: 8px 0 0;
  font-size: 0.75em;
  opacity: 0.6;
  font-style: italic;
}
.weather-option input:disabled + .weather-option-icon,
.weather-option:has(input:disabled) {
  cursor: not-allowed;
}

.factors-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.factors-row {
  padding: 8px 10px;
  border-radius: 8px;
  background: rgba(30, 41, 59, 0.55);
  border: 1px solid rgba(55, 65, 81, 0.5);
}
.factors-row-disabled {
  opacity: 0.55;
}

.factors-row-main {
  display: flex;
  flex-direction: column;
  margin-bottom: 6px;
}
.factors-row-name {
  font-weight: 600;
  font-size: 0.9em;
}
.factors-row-meta {
  font-size: 0.75em;
  opacity: 0.7;
  margin-top: 2px;
}

.factors-row-controls {
  display: flex;
  gap: 6px;
  align-items: center;
}
.factors-active-toggle input {
  width: 16px;
  height: 16px;
  cursor: pointer;
}
.factors-active-toggle input:disabled {
  cursor: not-allowed;
}
.factors-multiplier {
  width: 72px;
  padding: 4px 6px;
  border-radius: 6px;
  border: 1px solid rgba(55, 65, 81, 0.7);
  background: rgba(0, 0, 0, 0.35);
  color: #e5e7eb;
  font-size: 0.85em;
  font-variant-numeric: tabular-nums;
}
.factors-multiplier:disabled {
  opacity: 0.6;
}
.factors-save {
  flex: 1;
  padding: 4px 10px;
  border-radius: 6px;
  border: 1px solid rgba(99, 102, 241, 0.6);
  background: rgba(99, 102, 241, 0.25);
  color: #e5e7eb;
  font-size: 0.8em;
  cursor: pointer;
}
.factors-save:hover:not(:disabled) {
  background: rgba(99, 102, 241, 0.45);
}
.factors-save:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
</style>
