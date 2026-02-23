<template>
  <div class="station-select" ref="rootEl">
    <input
      ref="inputEl"
      v-model="searchTerm"
      type="text"
      class="station-input"
      :placeholder="placeholder || 'Название станции'"
      @focus="openDropdown"
      @input="onInput"
      @keydown.down.prevent="moveActive(1)"
      @keydown.up.prevent="moveActive(-1)"
      @keydown.enter.prevent="selectActive"
    />
    <Transition name="fade-down">
      <ul
        v-if="isOpen && filteredStations.length > 0"
        class="station-dropdown"
      >
        <li
          v-for="(station, index) in filteredStations"
          :key="station.id"
          :class="[
            'station-option',
            index === activeIndex ? 'station-option--active' : ''
          ]"
          @mousedown.prevent="selectStation(station)"
        >
          <span
            class="station-option-dot"
            :style="{ backgroundColor: station.line_color || '#6b7280' }"
          ></span>
          <span class="station-option-name">{{ station.name }}</span>
          <span class="station-option-line">{{ station.line_name }}</span>
        </li>
      </ul>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import type { Station } from "../types/api";

const props = defineProps<{
  label: string;
  stations: Station[];
  modelValue: string | null;
  placeholder?: string;
}>();

const emit = defineEmits<{
  (e: "update:modelValue", value: string | null): void;
}>();

const searchTerm = ref("");
const isOpen = ref(false);
const activeIndex = ref(-1);
const inputEl = ref<HTMLInputElement | null>(null);
const rootEl = ref<HTMLDivElement | null>(null);

const filteredStations = computed(() => {
  const term = searchTerm.value.trim().toLowerCase();
  if (!term) return props.stations.slice(0, 30);
  return props.stations
    .filter((s) => {
      const n = s.name.toLowerCase();
      const l = s.line_name.toLowerCase();
      return n.includes(term) || l.includes(term);
    })
    .slice(0, 30);
});

watch(
  () => props.modelValue,
  (newId) => {
    if (!newId) {
      searchTerm.value = "";
      return;
    }
    const st = props.stations.find((s) => s.id === newId);
    if (st) searchTerm.value = st.name;
  },
  { immediate: true }
);

function openDropdown() {
  isOpen.value = true;
  activeIndex.value = -1;
}

function closeDropdown() {
  isOpen.value = false;
  activeIndex.value = -1;
}

function onInput() {
  if (!isOpen.value) isOpen.value = true;
  emit("update:modelValue", null);
}

function selectStation(station: Station) {
  searchTerm.value = station.name;
  emit("update:modelValue", station.id);
  closeDropdown();
}

function moveActive(delta: number) {
  if (!isOpen.value) isOpen.value = true;
  const len = filteredStations.value.length;
  if (!len) return;
  const next = activeIndex.value + delta;
  if (next < 0) activeIndex.value = len - 1;
  else if (next >= len) activeIndex.value = 0;
  else activeIndex.value = next;
}

function selectActive() {
  if (activeIndex.value < 0 || activeIndex.value >= filteredStations.value.length) return;
  selectStation(filteredStations.value[activeIndex.value]);
}

function onDocumentClick(event: MouseEvent) {
  if (!rootEl.value) return;
  if (!rootEl.value.contains(event.target as Node)) closeDropdown();
}

onMounted(() => document.addEventListener("click", onDocumentClick));
onBeforeUnmount(() => document.removeEventListener("click", onDocumentClick));
</script>
