(function () {
  const cfg = window.__LOCAL_DASHBOARD__ || {};
  const wsPath = cfg.wsPath || "/ws/live";
  const wsUrl = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}${wsPath}`;
  const wsStatus = document.getElementById("ws-status");
  const mqttBadge = document.getElementById("mqtt-badge");

  function setWsStatus(text) {
    if (wsStatus) wsStatus.textContent = text;
  }

  function updateMqttBadge(connected, message) {
    if (!mqttBadge) return;
    mqttBadge.classList.toggle("mqtt-ok", !!connected);
    mqttBadge.classList.toggle("mqtt-bad", !connected);
    mqttBadge.textContent = connected ? "公网 MQTT：已连接" : `公网 MQTT：断联${message ? " · " + message : ""}`;
  }

  function mountChartsIn(slot) {
    const root = slot && slot.querySelector(".panel-root");
    if (root && window.LocalDashboardCharts) {
      window.LocalDashboardCharts.mountPanelRoot(root);
    }
  }

  function renderGlobalMockBanner(types) {
    const host = document.getElementById("mock-global-banner");
    if (!host) return;
    if (!types || types.length === 0) {
      host.hidden = true;
      host.textContent = "";
      return;
    }
    host.hidden = false;
    host.innerHTML =
      '<span class="data-mode-badge">模拟</span>' +
      `<span>部分体征为模拟采集（${types.join("、")}）</span>`;
  }

  async function refreshGlobalMockBanner() {
    try {
      const res = await fetch("/api/meta");
      if (!res.ok) return;
      const meta = await res.json();
      renderGlobalMockBanner(meta.mock_vita_types || []);
    } catch (_) {
      /* ignore */
    }
  }

  async function refreshPanel(vitaType) {
    const slot = document.getElementById(`panel-${vitaType}`);
    if (!slot) return;
    try {
      const res = await fetch(`/api/panel/${encodeURIComponent(vitaType)}`);
      if (!res.ok) return;
      slot.innerHTML = await res.text();
      mountChartsIn(slot);
    } catch (_) {
      /* ignore transient fetch errors */
    }
  }

  function connect() {
    const ws = new WebSocket(wsUrl);
    ws.onopen = () => setWsStatus("WebSocket 已连接");
    ws.onclose = () => {
      setWsStatus("WebSocket 断开，3 秒后重连…");
      setTimeout(connect, 3000);
    };
    ws.onerror = () => setWsStatus("WebSocket 错误");
    ws.onmessage = (ev) => {
      let msg;
      try {
        msg = JSON.parse(ev.data);
      } catch (_) {
        return;
      }
      if (msg.event === "vital.updated" && msg.vita_type) {
        refreshPanel(msg.vita_type);
        refreshGlobalMockBanner();
      }
      if (msg.event === "mqtt.status") {
        updateMqttBadge(msg.connected, msg.message || "");
      }
    };

    setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ action: "ping" }));
      }
    }, 25000);
  }

  connect();
  refreshGlobalMockBanner();
})();
