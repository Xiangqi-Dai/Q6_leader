/** Local Dashboard 图表（对齐 frontend_dashboard 风格） */
(function (global) {
  "use strict";

  const TEXT = "#94a3b8";
  const SPLIT = "#334155";
  const WIFI_RSSI_MIN = -95;
  const WIFI_RSSI_MAX = 0;
  const LATENCY_MAX = 460;
  const JITTER_MAX = 100;
  const Y_OFFSET = 36;

  const OCC_COLORS = {
    empty: "#2c3e50",
    excellent: "#2ecc71",
    fair: "#f39c12",
    poor: "#e74c3c",
    good: "#3498db",
  };

  const BAND_META = {
    "2_4_ghz": { title: "2.4 GHz 频段通道占用", fallback: Array.from({ length: 14 }, (_, i) => i + 1) },
    "5_ghz": {
      title: "5 GHz 频段通道占用",
      fallback: [36, 40, 44, 48, 52, 56, 60, 64, 100, 104, 108, 112, 116, 120, 124, 128, 132, 136, 140, 144, 149, 153, 157, 161, 165],
    },
  };

  const chartRegistry = new WeakMap();

  function signalStrengthColor(percent) {
    const p = Number(percent) || 0;
    if (p >= 70) return OCC_COLORS.excellent;
    if (p >= 50) return OCC_COLORS.good;
    if (p >= 30) return OCC_COLORS.fair;
    return OCC_COLORS.poor;
  }

  function occupancyBarColor(count) {
    if (count <= 0) return OCC_COLORS.empty;
    if (count <= 2) return OCC_COLORS.excellent;
    if (count <= 4) return OCC_COLORS.fair;
    return OCC_COLORS.poor;
  }

  function occupancyBarAlpha(count) {
    if (count <= 0) return 0.3;
    if (count <= 2) return 0.3 + count * 0.15;
    if (count <= 4) return 0.6;
    return 0.8;
  }

  function parseJson(el) {
    if (!el) return null;
    try {
      return JSON.parse(el.textContent || "null");
    } catch (_) {
      return null;
    }
  }

  function pairData(points, key, scaleLoss) {
    return points.map((p) => {
      const v = p[key];
      const y = v === null || v === undefined ? null : scaleLoss ? v * 100 : v;
      return [p.t, y];
    });
  }

  function timeExtent(points) {
    if (!points.length) return {};
    const now = Date.now();
    const ts = points.map((p) => p.t);
    return { min: Math.min(...ts) - 5000, max: Math.max(Math.max(...ts) + 5000, now) };
  }

  function disposeCharts(root) {
    const list = chartRegistry.get(root);
    if (!list) return;
    for (const c of list) {
      try {
        c.dispose();
      } catch (_) {}
    }
    chartRegistry.delete(root);
  }

  function registerChart(root, chart) {
    if (!chartRegistry.has(root)) chartRegistry.set(root, []);
    chartRegistry.get(root).push(chart);
  }

  function mountHeartbeat(root) {
    const host = root.querySelector('[data-chart="heartbeat-line"]');
    const dataEl = root.querySelector('[data-chart-data="heartbeat-line"]');
    if (!host || !global.echarts) return;
    const payload = parseJson(dataEl);
    const points = (payload && payload.points) || [];
    const extent = timeExtent(points);
    const chart = global.echarts.init(host, undefined, { renderer: "canvas" });
    chart.setOption({
      backgroundColor: "transparent",
      textStyle: { color: TEXT },
      tooltip: { trigger: "axis", axisPointer: { type: "cross" }, confine: true },
      legend: {
        data: ["延迟 (ms)", "信号强度 (dBm)", "丢包率 (%)", "抖动 (ms)"],
        bottom: 0,
        textStyle: { color: TEXT, fontSize: 10 },
      },
      grid: { left: 52, right: 52, top: 28, bottom: 56 },
      xAxis: {
        type: "time",
        min: extent.min,
        max: extent.max,
        axisLine: { lineStyle: { color: SPLIT } },
        splitLine: { show: true, lineStyle: { color: SPLIT, type: "dashed" } },
        axisLabel: { color: TEXT, fontSize: 10 },
      },
      yAxis: [
        { type: "value", name: "延迟\n(ms)", position: "left", min: 0, max: LATENCY_MAX, axisLine: { show: true, lineStyle: { color: "#38bdf8" } }, axisLabel: { color: TEXT, fontSize: 10 }, splitLine: { lineStyle: { color: SPLIT, type: "dashed" } } },
        { type: "value", name: "抖动\n(ms)", position: "left", offset: Y_OFFSET, min: 0, max: JITTER_MAX, axisLine: { show: true, lineStyle: { color: "#34d399" } }, axisLabel: { color: TEXT, fontSize: 10 }, splitLine: { show: false } },
        { type: "value", name: "dBm", position: "right", min: WIFI_RSSI_MIN, max: WIFI_RSSI_MAX, axisLine: { show: true, lineStyle: { color: "#a78bfa" } }, axisLabel: { color: TEXT, fontSize: 10 }, splitLine: { show: false } },
        { type: "value", name: "丢包\n(%)", position: "right", offset: Y_OFFSET, min: 0, max: 100, axisLine: { show: true, lineStyle: { color: "#fb923c" } }, axisLabel: { color: TEXT, fontSize: 10 }, splitLine: { show: false } },
      ],
      series: [
        { name: "延迟 (ms)", type: "line", yAxisIndex: 0, showSymbol: false, smooth: true, lineStyle: { width: 2, color: "#38bdf8" }, data: pairData(points, "latency", false) },
        { name: "信号强度 (dBm)", type: "line", yAxisIndex: 2, showSymbol: false, smooth: true, lineStyle: { width: 2, color: "#a78bfa" }, data: pairData(points, "rssi", false) },
        { name: "丢包率 (%)", type: "line", yAxisIndex: 3, showSymbol: false, smooth: true, lineStyle: { width: 2, color: "#fb923c" }, data: pairData(points, "loss", true) },
        { name: "抖动 (ms)", type: "line", yAxisIndex: 1, showSymbol: false, smooth: true, lineStyle: { width: 2, color: "#34d399" }, data: pairData(points, "jitter", false) },
      ],
    });
    registerChart(root, chart);
  }

  function mountAir(root) {
    const pollHost = root.querySelector('[data-chart="air-pollutant"]');
    const comfortHost = root.querySelector('[data-chart="air-comfort"]');
    const dataEl = root.querySelector('[data-chart-data="air-history"]');
    if (!global.echarts || !dataEl) return;
    const payload = parseJson(dataEl) || {};
    const pollutant = payload.pollutant || [];
    const comfort = payload.comfort || [];
    const extentP = timeExtent(pollutant);
    const extentC = timeExtent(comfort);

    if (pollHost && pollutant.length) {
      const chart = global.echarts.init(pollHost, undefined, { renderer: "canvas" });
      chart.setOption({
        backgroundColor: "transparent",
        textStyle: { color: TEXT },
        tooltip: { trigger: "axis", confine: true },
        legend: { data: ["CO₂", "甲醛", "VOC", "PM2.5"], bottom: 0, textStyle: { color: TEXT, fontSize: 10 } },
        grid: { left: 48, right: 48, top: 24, bottom: 48 },
        xAxis: { type: "time", min: extentP.min, max: extentP.max, axisLabel: { color: TEXT, fontSize: 10 }, splitLine: { lineStyle: { color: SPLIT, type: "dashed" } } },
        yAxis: { type: "value", axisLabel: { color: TEXT, fontSize: 10 }, splitLine: { lineStyle: { color: SPLIT, type: "dashed" } } },
        series: [
          { name: "CO₂", type: "line", smooth: true, showSymbol: false, lineStyle: { color: "#38bdf8", width: 2 }, data: pairData(pollutant, "co2", false) },
          { name: "甲醛", type: "line", smooth: true, showSymbol: false, lineStyle: { color: "#f87171", width: 2 }, data: pairData(pollutant, "hcho", false) },
          { name: "VOC", type: "line", smooth: true, showSymbol: false, lineStyle: { color: "#a78bfa", width: 2 }, data: pairData(pollutant, "voc", false) },
          { name: "PM2.5", type: "line", smooth: true, showSymbol: false, lineStyle: { color: "#fb923c", width: 2 }, data: pairData(pollutant, "pm25", false) },
        ],
      });
      registerChart(root, chart);
    }

    if (comfortHost && comfort.length) {
      const chart = global.echarts.init(comfortHost, undefined, { renderer: "canvas" });
      chart.setOption({
        backgroundColor: "transparent",
        textStyle: { color: TEXT },
        tooltip: { trigger: "axis", confine: true },
        legend: { data: ["温度", "湿度"], bottom: 0, textStyle: { color: TEXT, fontSize: 10 } },
        grid: { left: 48, right: 32, top: 24, bottom: 48 },
        xAxis: { type: "time", min: extentC.min, max: extentC.max, axisLabel: { color: TEXT, fontSize: 10 }, splitLine: { lineStyle: { color: SPLIT, type: "dashed" } } },
        yAxis: { type: "value", axisLabel: { color: TEXT, fontSize: 10 }, splitLine: { lineStyle: { color: SPLIT, type: "dashed" } } },
        series: [
          { name: "温度", type: "line", smooth: true, showSymbol: false, lineStyle: { color: "#f59e0b", width: 2 }, data: pairData(comfort, "temperature", false) },
          { name: "湿度", type: "line", smooth: true, showSymbol: false, lineStyle: { color: "#22d3ee", width: 2 }, data: pairData(comfort, "humidity", false) },
        ],
      });
      registerChart(root, chart);
    }
  }

  function bandOccupancy(data, key) {
    const occ = data.channel_occupancy && data.channel_occupancy[key];
    const meta = BAND_META[key];
    if (occ && occ.channels && occ.channels.length) {
      return {
        channels: occ.channels.map(Number),
        ap_counts: (occ.ap_counts || []).map(Number),
      };
    }
    const chs = meta.fallback;
    return { channels: chs, ap_counts: chs.map(() => 0) };
  }

  function networksForBand(networks, bandKey) {
    const chSet = new Set(BAND_META[bandKey].fallback);
    return networks.filter((n) => {
      const ch = Number(n.channel);
      if (bandKey === "2_4_ghz") return ch >= 1 && ch <= 14;
      return chSet.has(ch) || ch >= 36;
    });
  }

  function formatBandTooltip(info) {
    if (!info) return "";
    const lines = [
      `<b style="font-size:13px">Ch${info.ch}</b> <span style="color:#94a3b8;font-size:11px">${info.count} AP</span>`,
    ];
    if (info.ssids.length > 0) {
      lines.push('<hr style="border:none;border-top:1px solid #334155;margin:4px 0"/>');
      const sorted = info.ssids.slice().sort((a, b) => b.pct - a.pct);
      for (const s of sorted) {
        const bar = signalStrengthColor(s.pct);
        lines.push(
          `<div style="display:flex;align-items:center;gap:4px;margin:2px 0">`
            + `<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${bar};flex-shrink:0"></span>`
            + `<span style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${s.ssid}</span>`
            + `<span style="color:#94a3b8;font-size:10px;flex-shrink:0;white-space:nowrap">${s.pct}%&nbsp;${s.rssi}dBm</span>`
            + `</div>`
        );
      }
    } else {
      lines.push('<div style="color:#64748b;font-size:11px;padding:2px 0">无 AP</div>');
    }
    return `<div style="max-width:260px">${lines.join("")}</div>`;
  }

  function buildBandSeries(gridIndex, bandKey, data, networks, axisFs, is5G) {
    const meta = BAND_META[bandKey];
    const occ = bandOccupancy(data, bandKey);
    const channels = occ.channels;
    const chToNets = new Map();
    for (const n of networksForBand(networks, bandKey)) {
      const ch = Number(n.channel);
      if (!chToNets.has(ch)) chToNets.set(ch, []);
      chToNets.get(ch).push(n);
    }
    const occApCounts = occ.ap_counts || [];
    const counts =
      occApCounts.length === channels.length
        ? occApCounts.map(Number)
        : channels.map((ch) => (chToNets.get(ch) || []).length);
    const channelSsids = channels.map((ch) =>
      (chToNets.get(ch) || []).map((n) => ({
        ssid: String(n.ssid || "Hidden"),
        rssi: Number(n.rssi_dbm) || 0,
        pct: Number(n.signal_percent) || 0,
      }))
    );
    const labelFs = Math.max(7, Math.min(axisFs - 1, 9));
    return {
      title: meta.title,
      series: {
        type: "bar",
        xAxisIndex: gridIndex,
        yAxisIndex: gridIndex,
        data: counts.map((c, i) => ({
          value: 1,
          itemStyle: {
            color: occupancyBarColor(c),
            opacity: occupancyBarAlpha(c),
            borderColor: "rgba(255,255,255,0.3)",
            borderWidth: 0.5,
          },
          label: {
            show: true,
            position: "inside",
            formatter: is5G ? `${channels[i]}\n(${c})` : `Ch${channels[i]}\n(${c})`,
            color: c > 2 ? "#fff" : "#aaa",
            fontSize: labelFs,
            fontWeight: c > 0 ? "bold" : "normal",
            lineHeight: Math.max(10, labelFs + 2),
          },
          _chInfo: { ch: channels[i], count: c, ssids: channelSsids[i] },
        })),
        barWidth: "92%",
        silent: false,
        tooltip: {
          show: true,
          formatter: (params) => {
            const info =
              params.data && params.data._chInfo
                ? params.data._chInfo
                : typeof params.dataIndex === "number"
                  ? {
                      ch: channels[params.dataIndex],
                      count: counts[params.dataIndex] || 0,
                      ssids: channelSsids[params.dataIndex] || [],
                    }
                  : null;
            return formatBandTooltip(info);
          },
        },
      },
      channels,
    };
  }

  function mountRadio(root) {
    const bandHost = root.querySelector('[data-chart="radio-band"]');
    const dataEl = root.querySelector('[data-chart-data="radio-sniffer"]');
    if (!bandHost || !global.echarts || !dataEl) return;
    const data = parseJson(dataEl);
    if (!data) return;
    const axisFs = 9;
    const networks = Array.isArray(data.networks) ? data.networks : [];
    const band24 = buildBandSeries(0, "2_4_ghz", data, networks, axisFs, false);
    const band5 = buildBandSeries(1, "5_ghz", data, networks, axisFs, true);
    const statusLabel =
      data.status === "ok"
        ? `已发现 ${data.network_count || networks.length} 个 AP`
        : data.status === "empty"
          ? "扫描完成，未发现 AP"
          : `扫描异常${data.error ? "：" + data.error : ""}`;

    const chart = global.echarts.init(bandHost, undefined, { renderer: "canvas" });
    chart.setOption({
      backgroundColor: "transparent",
      textStyle: { color: TEXT },
      title: [
        { text: statusLabel + (data.interface ? ` · ${data.interface}` : ""), left: "center", top: 0, textStyle: { color: TEXT, fontSize: axisFs } },
        { text: band24.title, left: "center", top: "6%", textStyle: { color: "#e2e8f0", fontSize: axisFs + 1, fontWeight: "bold" } },
        { text: band5.title, left: "center", top: "52%", textStyle: { color: "#e2e8f0", fontSize: axisFs + 1, fontWeight: "bold" } },
      ],
      tooltip: { trigger: "item", confine: true },
      grid: [
        { left: 8, right: 8, top: "10%", height: "40%" },
        { left: 8, right: 8, top: "56%", height: "38%" },
      ],
      xAxis: [
        { type: "category", gridIndex: 0, data: band24.channels.map(String), axisLabel: { show: false }, axisTick: { show: false }, axisLine: { lineStyle: { color: SPLIT } } },
        { type: "category", gridIndex: 1, data: band5.channels.map(String), axisLabel: { show: false }, axisTick: { show: false }, axisLine: { lineStyle: { color: SPLIT } } },
      ],
      yAxis: [
        { type: "value", gridIndex: 0, min: 0, max: 1, show: false },
        { type: "value", gridIndex: 1, min: 0, max: 1, show: false },
      ],
      series: [band24.series, band5.series],
    });
    registerChart(root, chart);

    // 信号强度条颜色（模板已渲染 DOM，此处仅补色）
    root.querySelectorAll(".signal-row-bar[data-pct]").forEach((bar) => {
      const pct = Number(bar.getAttribute("data-pct")) || 0;
      bar.style.width = `${Math.min(100, Math.max(0, pct))}%`;
      bar.style.backgroundColor = signalStrengthColor(pct);
    });
  }

  function panelKind(root) {
    return root.getAttribute("data-panel-kind") || root.dataset.panelKind || null;
  }

  function mountPanelRoot(root) {
    if (!root) return;
    disposeCharts(root);
    const kind = panelKind(root);
    if (kind === "heartbeat") mountHeartbeat(root);
    else if (kind === "air_sniffer") mountAir(root);
    else if (kind === "radio_sniffer") mountRadio(root);
    requestAnimationFrame(() => {
      const list = chartRegistry.get(root) || [];
      for (const c of list) c.resize();
    });
  }

  function mountAll(container) {
    const scope = container || document;
    scope.querySelectorAll(".panel-root").forEach((root) => mountPanelRoot(root));
  }

  global.LocalDashboardCharts = { mountAll, mountPanelRoot, signalStrengthColor };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => mountAll());
  } else {
    mountAll();
  }

  global.addEventListener("resize", () => {
    document.querySelectorAll(".panel-root").forEach((root) => {
      const list = chartRegistry.get(root) || [];
      for (const c of list) c.resize();
    });
  });
})(window);
