<template>
  <div class="metro-map-wrapper">
    <div ref="cyContainer" class="metro-map-canvas"></div>
    <Transition name="fade">
      <div v-if="!graph" class="metro-map-loading">
        <div class="spinner"></div>
        <p>Загружаем карту метро…</p>
      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch, nextTick } from "vue";
import cytoscape from "cytoscape";
import type { GraphResponse, PathResponse } from "../types/api";

const props = defineProps<{
  graph: GraphResponse | null;
  path: PathResponse | null;
}>();

const cyContainer = ref<HTMLDivElement | null>(null);
let cy: cytoscape.Core | null = null;
const hadRoute = ref(false);
let savedView: { zoom: number; pan: { x: number; y: number } } | null = null;

/** Круг с сегментами цветов линий (как на официальных картах пересадок). */
function segmentCircleDataUrl(colors: string[], size: number = 64): string {
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d");
  if (!ctx) return "";
  const cx = size / 2;
  const cy = size / 2;
  const r = size / 2 - 2;
  const n = colors.length;
  for (let i = 0; i < n; i++) {
    const start = (i / n) * 2 * Math.PI - Math.PI / 2;
    const end = ((i + 1) / n) * 2 * Math.PI - Math.PI / 2;
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.arc(cx, cy, r, start, end);
    ctx.closePath();
    ctx.fillStyle = colors[i];
    ctx.fill();
  }
  ctx.strokeStyle = "rgba(0,0,0,0.45)";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, 2 * Math.PI);
  ctx.stroke();
  return canvas.toDataURL("image/png");
}

function buildGraph() {
  const container = cyContainer.value;
  const graph = props.graph;
  if (!container || !graph || graph.stations.length === 0) return;

  const hasRouteNow = (props.path?.path?.length ?? 0) > 0;
  if (cy && hadRoute.value && !hasRouteNow) {
    savedView = { zoom: cy.zoom(), pan: cy.pan() };
  } else {
    savedView = null;
  }
  if (cy) { cy.destroy(); cy = null; }

  const COS_LAT = Math.cos((55.75 * Math.PI) / 180);
  const SCALE = 5000;

  let latSum = 0, lngSum = 0;
  graph.stations.forEach(s => { latSum += s.lat; lngSum += s.lng; });
  const cLat = latSum / graph.stations.length;
  const cLng = lngSum / graph.stations.length;

  const stationColor = new Map<string, string>();
  graph.stations.forEach(s => stationColor.set(s.id, s.line_color || "#6b7280"));

  const routeIds = new Set<string>();
  const routeEdges = new Set<string>();
  if (props.path?.path) {
    props.path.path.forEach((step, i) => {
      routeIds.add(step.station_id);
      if (i > 0) routeEdges.add(`${props.path!.path[i - 1].station_id}->${step.station_id}`);
    });
  }
  const hasRoute = routeIds.size > 0;

  // Станции с одним именем на разных линиях без перехода — не объединяем в один кружок
  const NO_HUB_NAMES = new Set(["Новопеределкино", "Люблино"]);

  // Группы одноимённых станций (пересадочные узлы)
  const nameToStations = new Map<string, typeof graph.stations>();
  graph.stations.forEach((s) => {
    const arr = nameToStations.get(s.name);
    if (arr) arr.push(s);
    else nameToStations.set(s.name, [s]);
  });

  const sharedPos = new Map<string, { x: number; y: number }>();
  nameToStations.forEach((stations, name) => {
    if (stations.length > 1 && !NO_HUB_NAMES.has(name)) {
      const ax =
        stations.reduce((sum, s) => sum + (s.lng - cLng) * COS_LAT * SCALE, 0) / stations.length;
      const ay =
        stations.reduce((sum, s) => sum + -(s.lat - cLat) * SCALE, 0) / stations.length;
      sharedPos.set(name, { x: ax, y: ay });
    }
  });

  const nodes: cytoscape.ElementDefinition[] = [];
  graph.stations.forEach((s) => {
    const pos = sharedPos.get(s.name)
      ? { x: sharedPos.get(s.name)!.x, y: sharedPos.get(s.name)!.y }
      : { x: (s.lng - cLng) * COS_LAT * SCALE, y: -(s.lat - cLat) * SCALE };
    const group = nameToStations.get(s.name)!;
    const isHub = group.length > 1 && !NO_HUB_NAMES.has(s.name);

    if (isHub) {
      // Невидимый узел для рёбер (все станции группы в одной точке)
      const cls: string[] = ["grouped"];
      if (hasRoute && routeIds.has(s.id)) cls.push("route");
      if (hasRoute && !routeIds.has(s.id)) cls.push("dimmed");
      nodes.push({
        data: { id: s.id, label: "", color: s.line_color || "#6b7280", lat: s.lat, lng: s.lng },
        position: pos,
        classes: cls.join(" "),
      });
    } else {
      // Обычная станция (одна с таким именем)
      const cls: string[] = [];
      if (hasRoute && routeIds.has(s.id)) cls.push("route");
      if (hasRoute && !routeIds.has(s.id)) cls.push("dimmed");
      const label = s.name?.trim() ? s.name : s.id;
      nodes.push({
        data: { id: s.id, label, color: s.line_color || "#6b7280", lat: s.lat, lng: s.lng },
        position: pos,
        classes: cls.join(" "),
      });
    }
  });

  // Хаб-узлы: один кружок с сегментами цветов линий для каждой группы пересадок
  sharedPos.forEach((pos, name) => {
    const stations = nameToStations.get(name)!;
    if (stations.length < 2) return;
    const colors = stations.map((s) => s.line_color || "#6b7280");
    const hubId = "hub-" + name.replace(/[^a-zA-Zа-яёА-Я0-9]+/g, "_").replace(/^_|_$/g, "");
    const cls: string[] = ["hub"];
    const anyInRoute = stations.some((s) => routeIds.has(s.id));
    if (hasRoute && anyInRoute) cls.push("route");
    if (hasRoute && !anyInRoute) cls.push("dimmed");
    const avgLat = stations.reduce((s, st) => s + st.lat, 0) / stations.length;
    const avgLng = stations.reduce((s, st) => s + st.lng, 0) / stations.length;
    nodes.push({
      data: {
        id: hubId,
        label: name,
        bg: segmentCircleDataUrl(colors),
        stationIds: stations.map((s) => s.id),
        lat: avgLat,
        lng: avgLng,
      },
      position: pos,
      classes: cls.join(" "),
    });
  });

  // Build a lookup: station id -> name for detecting merged transfers
  const idToName = new Map<string, string>();
  graph.stations.forEach(s => idToName.set(s.id, s.name));

  const seen = new Set<string>();
  const edges: cytoscape.ElementDefinition[] = [];
  graph.edges.forEach(e => {
    const key = [e.from_id, e.to_id].sort().join("||");
    if (seen.has(key)) return;
    seen.add(key);

    // Hide transfer edges between merged (same-name) stations — they overlap at the same point
    if (e.is_transfer && idToName.get(e.from_id) === idToName.get(e.to_id)) return;

    const fwd = `${e.from_id}->${e.to_id}`;
    const rev = `${e.to_id}->${e.from_id}`;
    const inRoute = routeEdges.has(fwd) || routeEdges.has(rev);
    const lc = stationColor.get(e.from_id) || "#6b7280";

    const cls: string[] = [];
    if (e.is_transfer) cls.push("transfer");
    if (hasRoute && inRoute) cls.push("route");
    if (hasRoute && !inRoute) cls.push("dimmed");

    edges.push({
      data: {
        id: `e-${e.from_id}-${e.to_id}`,
        source: e.from_id,
        target: e.to_id,
        color: e.is_transfer ? "rgba(156,163,175,0.5)" : lc,
      },
      classes: cls.join(" "),
    });
  });

  console.log(
    `[MetroMap] ${graph.stations.length} stations, ${edges.length} edges | container ${container.clientWidth}x${container.clientHeight}`
  );

  cy = cytoscape({
    container,
    elements: { nodes, edges },
    layout: { name: "preset" },
    style: [
      {
        selector: "node",
        style: {
          "background-color": "data(color)" as any,
          "border-width": 1,
          "border-color": "rgba(0,0,0,0.4)",
          label: "data(label)" as any,
          width: 10,
          height: 10,
          "font-size": 10,
          color: "#e5e7eb",
          "text-outline-color": "#0a0e1a",
          "text-outline-width": 2,
          "text-valign": "center",
          "text-halign": "right",
          "text-margin-x": 5,
          "min-zoomed-font-size": 4,
          "z-index": 6,
        },
      },
      {
        selector: "node.grouped",
        style: {
          width: 2,
          height: 2,
          "border-width": 0,
          label: "",
          "background-opacity": 0,
          "border-opacity": 0,
        },
      },
      {
        selector: "node.hub",
        style: {
          "background-image": (ele: cytoscape.NodeSingular) =>
            ele.data("bg") ? `url(${ele.data("bg")})` : "none",
          "background-color": "transparent",
          "background-fit": "contain",
          "background-opacity": 1,
          width: 14,
          height: 14,
          "border-width": 0,
          label: "data(label)" as any,
          "font-size": 10,
          "text-valign": "center",
          "text-halign": "right",
          "text-margin-x": 6,
          "z-index": 0,
        },
      },
      {
        selector: "node.hub.route",
        style: {
          width: 18,
          height: 18,
          "border-width": 3,
          "border-color": "#ffffff",
          "border-style": "solid",
          "font-size": 12,
          "font-weight": "bold" as any,
          "z-index": 10,
        },
      },
      {
        selector: "node.route",
        style: {
          width: 16,
          height: 16,
          "border-width": 3,
          "border-color": "#ffffff",
          "font-size": 13,
          "font-weight": "bold" as any,
          "z-index": 10,
        },
      },
      {
        selector: "node.dimmed",
        style: { opacity: 0.2 },
      },
      {
        selector: "node.hub.dimmed",
        style: { opacity: 0.35 },
      },
      {
        selector: "edge",
        style: {
          "line-color": "data(color)" as any,
          width: 2.5,
          "curve-style": "straight" as any,
          "z-index": 5,
        },
      },
      {
        selector: "edge.transfer",
        style: {
          "line-style": "dashed" as any,
          width: 1.5,
        },
      },
      {
        selector: "edge.route",
        style: {
          "line-color": "#ffffff",
          width: 5,
          "z-index": 10,
        },
      },
      {
        selector: "edge.dimmed",
        style: { opacity: 0.35 },
      },
    ],
    minZoom: 0.1,
    maxZoom: 5,
    wheelSensitivity: 1.0,
    boxSelectionEnabled: false,
  });

  // При перетаскивании хаба — двигаем все групповые узлы (к ним привязаны рёбра)
  cy.on("drag", "node.hub", (evt) => {
    const node = evt.target;
    const pos = node.position();
    const stationIds: string[] = node.data("stationIds") || [];
    stationIds.forEach((sid) => {
      const n = cy!.getElementById(sid);
      if (n.length) n.position(pos);
    });
  });
  // При перетаскивании группового узла — двигаем хаб и остальные узлы той же группы
  cy.on("drag", "node.grouped", (evt) => {
    const node = evt.target;
    const pos = node.position();
    const name = idToName.get(node.id());
    if (!name) return;
    const hubId = "hub-" + name.replace(/[^a-zA-Zа-яёА-Я0-9]+/g, "_").replace(/^_|_$/g, "");
    const hub = cy!.getElementById(hubId);
    if (hub.length) hub.position(pos);
    const sameNameIds = graph.stations.filter((s) => s.name === name).map((s) => s.id);
    sameNameIds.forEach((sid) => {
      const n = cy!.getElementById(sid);
      if (n.length && n.id() !== node.id()) n.position(pos);
    });
  });

  cy.ready(() => {
    if (hasRoute) {
      hadRoute.value = true;
      const rn = cy!.nodes().filter((n: any) => {
        const id = n.id();
        if (routeIds.has(id)) return true;
        if (id.startsWith("hub-") && n.data("stationIds"))
          return n.data("stationIds").some((sid: string) => routeIds.has(sid));
        return false;
      });
      if (rn.length) {
        cy!.fit(rn, 60);
      } else {
        cy!.fit(undefined as any, 40);
      }
    } else {
      if (savedView) {
        cy!.zoom(savedView.zoom);
        cy!.pan(savedView.pan);
      } else if (!hadRoute.value) {
        const centralNodes = cy!.nodes().filter((n: any) => {
          const lat = n.data("lat");
          const lng = n.data("lng");
          if (lat == null || lng == null) return false;
          return lat > 55.58 && lat < 55.92 && lng > 37.35 && lng < 37.85;
        });
        if (centralNodes.length) {
          cy!.fit(centralNodes, 20);
        } else {
          cy!.fit(undefined as any, 40);
        }
      }
    }
  });
}

function onResize() {
  if (cy) cy.resize();
}

watch(
  () => [props.graph, props.path],
  async () => {
    await nextTick();
    requestAnimationFrame(() => buildGraph());
  },
  { immediate: true },
);

onMounted(() => {
  window.addEventListener("resize", onResize);
});

onBeforeUnmount(() => {
  window.removeEventListener("resize", onResize);
  if (cy) { cy.destroy(); cy = null; }
});
</script>
