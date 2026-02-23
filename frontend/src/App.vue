<template>
  <div class="app-root">
    <RouteGraph
      class="app-map"
      :graph="graph"
      :path="currentPath"
    />

    <section class="control-panel">
      <header class="control-panel-header">
        <h1 class="control-panel-title">FastMetro</h1>
        <p class="control-panel-subtitle">Кратчайший маршрут</p>
      </header>

      <Transition name="fade-down">
        <ErrorBanner
          v-if="errorMessage"
          :message="errorMessage"
        />
      </Transition>

      <form class="route-form" @submit.prevent="onSubmitRoute">
        <StationSelect
          label="Откуда"
          placeholder="Станция отправления"
          :stations="stations"
          v-model="fromStationId"
        />

        <div class="route-arrow">
          <span class="route-arrow-icon route-arrow-vertical">↓</span>
          <span class="route-arrow-icon route-arrow-horizontal">→</span>
        </div>

        <StationSelect
          label="Куда"
          placeholder="Станция назначения"
          :stations="stations"
          v-model="toStationId"
        />

        <button
          class="btn-primary"
          type="submit"
          :disabled="!canSubmit || isLoadingPath"
        >
          <span v-if="isLoadingPath" class="spinner"></span>
          <span v-else>Построить маршрут</span>
        </button>
        <button
          class="btn-secondary"
          type="button"
          :disabled="!currentPath"
          @click="onClearRoute"
        >
          Очистить маршрут
        </button>
      </form>

      <Transition name="fade-up">
        <RouteSummary
          v-if="currentPath"
          :path="currentPath"
        />
      </Transition>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { fetchStations, fetchPath, fetchGraph } from "./api/client";
import type { GraphResponse, PathResponse, Station } from "./types/api";
import StationSelect from "./components/StationSelect.vue";
import RouteGraph from "./components/RouteGraph.vue";
import RouteSummary from "./components/RouteSummary.vue";
import ErrorBanner from "./components/ErrorBanner.vue";

const stations = ref<Station[]>([]);
const fromStationId = ref<string | null>(null);
const toStationId = ref<string | null>(null);
const currentPath = ref<PathResponse | null>(null);
const graph = ref<GraphResponse | null>(null);
const isLoadingStations = ref(false);
const isLoadingPath = ref(false);
const isLoadingGraph = ref(false);
const errorMessage = ref<string | null>(null);
const graphLoadAttempts = ref(0);

const canSubmit = computed(
  () => !!fromStationId.value && !!toStationId.value && fromStationId.value !== toStationId.value
);

async function loadStations() {
  try {
    isLoadingStations.value = true;
    errorMessage.value = null;
    stations.value = await fetchStations();
  } catch (e) {
    console.error(e);
    errorMessage.value =
      "Не удалось загрузить список станций. Попробуйте обновить страницу.";
  } finally {
    isLoadingStations.value = false;
  }
}

async function loadGraph() {
  try {
    graphLoadAttempts.value += 1;
    isLoadingGraph.value = true;
    graph.value = await fetchGraph();
    errorMessage.value = null;
  } catch (e) {
    console.error(e);
    if (!errorMessage.value) {
      errorMessage.value =
        "Не удалось загрузить карту метро. Попробуйте обновить страницу.";
    }
  } finally {
    isLoadingGraph.value = false;
  }

  if (!graph.value && graphLoadAttempts.value < 5) {
    setTimeout(() => loadGraph(), 2000);
  }
}

async function onSubmitRoute() {
  if (!canSubmit.value || !fromStationId.value || !toStationId.value) return;

  try {
    isLoadingPath.value = true;
    errorMessage.value = null;
    currentPath.value = await fetchPath(fromStationId.value, toStationId.value);
  } catch (e) {
    console.error(e);
    errorMessage.value =
      "Не удалось построить маршрут. Проверьте станции и попробуйте ещё раз.";
  } finally {
    isLoadingPath.value = false;
  }
}

function onClearRoute() {
  currentPath.value = null;
}

onMounted(() => {
  loadStations();
  loadGraph();
});
</script>
