// Market Radar: tooltips, line-chart crosshair, auto-submitting filters. No framework.
(() => {
  const tip = document.querySelector(".tooltip");

  // Build tooltip content with textContent only (labels come from API data).
  function show(lines, x, y, rows) {
    tip.replaceChildren();
    if (lines) {
      lines.forEach((text, i) => {
        const div = document.createElement("div");
        div.className = i === 0 ? "t-title" : "t-row";
        div.textContent = text;
        tip.appendChild(div);
      });
    }
    (rows || []).forEach(([key, value, isSelf]) => {
      const row = document.createElement("div");
      row.className = "t-row";
      const k = document.createElement("span");
      k.className = "t-key" + (isSelf ? " self" : "");
      const v = document.createElement("strong");
      v.textContent = value;
      const n = document.createElement("span");
      n.textContent = key;
      row.append(k, v, n);
      tip.appendChild(row);
    });
    tip.hidden = false;
    const pad = 14, w = tip.offsetWidth, h = tip.offsetHeight;
    tip.style.left = Math.min(x + pad, innerWidth - w - 8) + "px";
    tip.style.top = Math.max(8, y - h - pad) + "px";
  }
  const hide = () => (tip.hidden = true);

  // Per-mark tooltips (bars, scatter points, meters, flags)
  document.querySelectorAll("[data-tip]").forEach((el) => {
    const lines = JSON.parse(el.dataset.tip);
    const at = (e) => {
      const r = el.getBoundingClientRect();
      show(lines, e.clientX ?? r.right, e.clientY ?? r.top);
    };
    el.addEventListener("pointermove", at);
    el.addEventListener("focus", at);
    el.addEventListener("pointerleave", hide);
    el.addEventListener("blur", hide);
  });

  // Line charts: crosshair snaps to the nearest month, one readout for every series
  document.querySelectorAll("svg.chart.line").forEach((svg) => {
    const data = JSON.parse(svg.dataset.series);
    const x0 = +svg.dataset.x0, dx = +svg.dataset.dx;
    const cross = svg.querySelector(".crosshair");
    const hit = svg.querySelector(".hit");
    const move = (e) => {
      const pt = svg.createSVGPoint();
      pt.x = e.clientX; pt.y = e.clientY;
      const p = pt.matrixTransform(svg.getScreenCTM().inverse());
      const i = Math.max(0, Math.min(data.months.length - 1, Math.round((p.x - x0) / dx)));
      const cx = x0 + i * dx;
      cross.setAttribute("x1", cx); cross.setAttribute("x2", cx);
      cross.setAttribute("visibility", "visible");
      const rows = data.series
        .filter((s) => s.idx[i] != null)
        .sort((a, b) => b.idx[i] - a.idx[i])
        .map((s) => [s.name, String(s.idx[i]), s.self]);
      show([data.months[i]], e.clientX, e.clientY, rows);
    };
    hit.addEventListener("pointermove", move);
    hit.addEventListener("pointerleave", () => { cross.setAttribute("visibility", "hidden"); hide(); });
  });

  // Filters re-render the page on change; charts keep their frame while loading
  document.querySelectorAll("form[data-autosubmit] select").forEach((sel) =>
    sel.addEventListener("change", () => {
      document.querySelector(".layout")?.style.setProperty("opacity", "0.55");
      sel.form.submit();
    })
  );
})();

// Accounts table: whole row selects the client (master-detail)
document.querySelectorAll("tr[data-href]").forEach((tr) =>
  tr.addEventListener("click", (e) => { if (!e.target.closest("a")) location.href = tr.dataset.href; })
);

// Scoreboard row hover highlights that company's line in the chart above
document.querySelectorAll(".panel").forEach((panel) => {
  const svg = panel.querySelector("svg.chart.line");
  if (!svg) return;
  panel.querySelectorAll("tr[data-series]").forEach((tr) => {
    const name = tr.dataset.series;
    const on = () => {
      svg.classList.add("has-hl");
      svg.querySelectorAll(".series").forEach((p) => p.classList.toggle("hl", p.dataset.name === name));
    };
    const off = () => { svg.classList.remove("has-hl"); svg.querySelectorAll(".series.hl").forEach((p) => p.classList.remove("hl")); };
    tr.addEventListener("mouseenter", on);
    tr.addEventListener("mouseleave", off);
  });
});
