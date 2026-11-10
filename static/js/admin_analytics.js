(() => {
  const read = (id) => {
    const node = document.getElementById(id);
    if (!node) return null;
    try { return JSON.parse(node.textContent); } catch { return null; }
  };
  const green = "#1e5b3d";
  const gold = "#d8ad45";
  const blue = "#6d9bc2";
  const colors = [green, gold, blue, "#72a17c", "#bd7559", "#9679b2", "#63a8a0"];
  const money = (value) => `RM ${Number(value || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  const baseOptions = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { intersect: false, mode: "index" },
    plugins: {
      legend: { position: "bottom", labels: { usePointStyle: true, boxWidth: 8, padding: 16, color: "#65746a", font: { family: "DM Sans, sans-serif", size: 11 } } },
      tooltip: { backgroundColor: "#173d2d", padding: 11, titleFont: { weight: "700" }, bodyFont: { size: 11 }, cornerRadius: 8 },
    },
    scales: {
      x: { grid: { display: false }, ticks: { color: "#849188", maxRotation: 0, autoSkip: true, maxTicksLimit: 8 } },
      y: { beginAtZero: true, grid: { color: "#edf1ed" }, ticks: { color: "#849188" } },
    },
  };
  const make = (id, config) => {
    const canvas = document.getElementById(id);
    if (canvas && window.Chart) new Chart(canvas, config);
  };

  const revenue = read("revenue-chart-data");
  if (revenue) make("revenue-chart", {
    type: "line",
    data: { labels: revenue.labels, datasets: [{ label: "2.2% fee revenue", data: revenue.values, borderColor: green, backgroundColor: "rgba(30,91,61,.12)", fill: true, tension: .34, pointRadius: 2.5, pointHoverRadius: 5, borderWidth: 2.5 }] },
    options: { ...baseOptions, plugins: { ...baseOptions.plugins, tooltip: { ...baseOptions.plugins.tooltip, callbacks: { label: (context) => ` ${money(context.raw)}` } } }, scales: { ...baseOptions.scales, y: { ...baseOptions.scales.y, ticks: { ...baseOptions.scales.y.ticks, callback: money } } } },
  });

  const transfers = read("supplier-transfer-chart-data");
  if (transfers) {
    const canvas = document.getElementById("supplier-transfer-chart");
    if (!transfers.values.length && canvas) {
      const empty = document.createElement("div");
      empty.className = "analytics-chart-empty";
      empty.innerHTML = "<span aria-hidden='true'>↗</span><strong>No paid supplier transfers yet</strong><small>Completed payouts will appear here.</small>";
      canvas.replaceWith(empty);
    } else make("supplier-transfer-chart", {
      type: "bar",
      data: { labels: transfers.labels, datasets: [{ label: "Transferred", data: transfers.values, backgroundColor: green, borderRadius: 7, maxBarThickness: 42 }] },
      options: { ...baseOptions, plugins: { ...baseOptions.plugins, legend: { display: false }, tooltip: { ...baseOptions.plugins.tooltip, callbacks: { label: (context) => ` ${money(context.raw)}` } } }, scales: { x: { ...baseOptions.scales.x, grid: { display: false }, ticks: { ...baseOptions.scales.x.ticks, minRotation: 25, maxRotation: 45 } }, y: { ...baseOptions.scales.y, ticks: { ...baseOptions.scales.y.ticks, callback: money } } } },
    });
  }

  const weekday = read("needy-weekday-chart-data");
  if (weekday) {
    const busiestDay = weekday.values.indexOf(Math.max(...weekday.values));
    make("needy-weekday-chart", {
    type: "bar",
    data: { labels: weekday.labels, datasets: [{ label: "Completed collection reports", data: weekday.values, backgroundColor: weekday.labels.map((_, index) => index === busiestDay && weekday.values[index] > 0 ? gold : green), borderRadius: 7, maxBarThickness: 42 }] },
    options: { ...baseOptions, plugins: { ...baseOptions.plugins, legend: { display: false }, tooltip: { ...baseOptions.plugins.tooltip, callbacks: { label: (context) => ` ${context.raw} completed collection report${context.raw === 1 ? "" : "s"} in the past year` } } }, scales: { ...baseOptions.scales, x: { ...baseOptions.scales.x, autoSkip: false, maxRotation: 0, minRotation: 0 }, y: { ...baseOptions.scales.y, ticks: { ...baseOptions.scales.y.ticks, precision: 0 } } } },
    });
  }

  const states = read("provider-state-chart-data");
  if (states) make("provider-state-chart", {
    type: "bar",
    data: { labels: states.labels, datasets: [{ label: "Provider registrations", data: states.values, backgroundColor: states.labels.map((label) => label === "Unspecified" ? gold : green), borderRadius: 5, maxBarThickness: 20 }] },
    options: { ...baseOptions, indexAxis: "y", plugins: { ...baseOptions.plugins, legend: { display: false }, tooltip: { ...baseOptions.plugins.tooltip, callbacks: { label: (context) => ` ${context.raw} provider${context.raw === 1 ? "" : "s"}` } } }, scales: { x: { ...baseOptions.scales.x, beginAtZero: true, ticks: { ...baseOptions.scales.x.ticks, precision: 0 } }, y: { ...baseOptions.scales.y, grid: { display: false }, ticks: { color: "#69766e", font: { size: 10 } } } } },
  });

  const growth = read("growth-chart-data");
  if (growth) make("growth-chart", {
    type: "line",
    data: { labels: growth.labels, datasets: growth.series.map((series, index) => ({ label: series.label, data: series.data, borderColor: colors[index], backgroundColor: colors[index], tension: .3, pointRadius: 2.5, borderWidth: 2 })) },
    options: { ...baseOptions },
  });
})();
