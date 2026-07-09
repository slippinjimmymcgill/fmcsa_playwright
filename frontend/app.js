const API_BASE = "https://fmcsa-playwright.onrender.com";

// State centroids (lat/lng) for bubble placement - D3 projects these
const STATE_CENTROIDS = {
  AL:[86.9023,32.3182],AK:[153.3696,56.1326],AZ:[111.0937,34.0489],
  AR:[91.8318,34.7465],CA:[119.4179,36.7783],CO:[105.7821,39.5501],
  CT:[72.7554,41.6032],DE:[75.5277,38.9108],FL:[81.5158,27.6648],
  GA:[83.6431,32.1656],HI:[155.5828,19.8968],ID:[114.7420,44.0682],
  IL:[89.1965,40.6331],IN:[86.1349,40.2672],IA:[93.0977,41.8780],
  KS:[98.4842,38.5266],KY:[84.6701,37.8393],LA:[91.9623,30.9843],
  ME:[69.4455,45.2538],MD:[76.6413,39.0458],MA:[71.5301,42.4072],
  MI:[84.5603,44.3148],MN:[94.6859,46.7296],MS:[89.6787,32.3547],
  MO:[91.8318,37.9643],MT:[110.3626,46.8797],NE:[99.9018,41.4925],
  NV:[116.4194,38.8026],NH:[71.5724,43.1939],NJ:[74.4057,40.0583],
  NM:[105.8701,34.5199],NY:[74.9481,43.2994],NC:[79.0193,35.7596],
  ND:[101.0020,47.5515],OH:[82.9071,40.4173],OK:[97.0929,35.4676],
  OR:[120.5542,43.8041],PA:[77.1945,41.2033],RI:[71.4774,41.5801],
  SC:[81.1637,33.8361],SD:[99.9018,43.9695],TN:[86.5804,35.5175],
  TX:[97.5635,31.9686],UT:[111.0937,39.3210],VT:[72.5778,44.5588],
  VA:[78.6569,37.4316],WA:[120.7401,47.7511],WV:[80.4549,38.5976],
  WI:[89.6165,43.7844],WY:[107.2903,43.0760],DC:[77.0369,38.9072],
};

let currentMapData = [];
let mapInitialized = false;
let usTopoData = null;

function setStatus(msg, isError = false) {
  const bar = document.getElementById("statusBar");
  bar.textContent = msg;
  bar.style.display = msg ? "block" : "none";
  bar.className = "status-bar" + (isError ? " error" : "");
}

function switchTab(name) {
  document.querySelectorAll(".tab-btn").forEach((b, i) => {
    const tabs = ["inspections","crashes","insurance","authority","map"];
    b.classList.toggle("active", tabs[i] === name);
  });
  document.querySelectorAll(".tab-content").forEach(c => c.classList.remove("active"));
  document.getElementById("tab-" + name).classList.add("active");
  if (name === "map") renderMap(currentMapData);
}

function renderCarrier(carrier) {
  const statusClass = (carrier.usdot_status||"").toLowerCase().includes("active") ? "active" : "inactive";
  const ratingVal = (carrier.safety_rating && carrier.safety_rating !== "None") ? carrier.safety_rating : "Not Rated";
  const ratingClass = ratingVal.toLowerCase().includes("satisfactory") ? "satisfactory"
    : ratingVal.toLowerCase().includes("conditional") ? "conditional"
    : ratingVal.toLowerCase().includes("unsatisfactory") ? "unsatisfactory" : "";

  const fields = [
    {label:"Legal Name", value:carrier.legal_name||"—"},
    {label:"DBA Name", value:carrier.dba_name||"—"},
    {label:"USDOT Number", value:carrier.dot_number||"—"},
    {label:"MC/MX/FF Number", value:carrier.mc_mx_ff_numbers||"—"},
    {label:"Entity Type", value:carrier.entity_type||"—"},
    {label:"USDOT Status", value:carrier.usdot_status||"—", badge:true, badgeClass:statusClass},
    {label:"Operating Authority", value:carrier.operating_authority_status||"—"},
    {label:"Out of Service Date", value:carrier.out_of_service_date||"—"},
    {label:"Phone", value:carrier.phone||"—"},
    {label:"Physical Address", value:carrier.physical_address||"—"},
    {label:"Mailing Address", value:carrier.mailing_address||"—"},
    {label:"Power Units", value:carrier.power_units||"—"},
    {label:"Drivers", value:carrier.drivers||"—"},
    {label:"DUNS Number", value:carrier.duns_number||"—"},
    {label:"MCS-150 Form Date", value:carrier.mcs150_form_date||"—"},
    {label:"MCS-150 Mileage (Year)", value:carrier.mcs150_mileage_year||"—"},
    {label:"Safety Rating", value:ratingVal, badge:!!ratingClass, badgeClass:ratingClass},
  ];

  document.getElementById("companyGrid").innerHTML = fields.map(f => `
    <div class="info-item">
      <label>${f.label}</label>
      <p>${f.badge ? `<span class="badge ${f.badgeClass}">${f.value}</span>` : f.value}</p>
    </div>`).join("");
  document.getElementById("companyCard").classList.remove("hidden");
}

function renderInspections(inspections) {
  document.getElementById("inspTabCount").textContent = inspections.length;
  const tbody = document.getElementById("inspBody");
  if (!inspections.length) {
    tbody.innerHTML = `<tr><td colspan="12" class="empty-msg">No inspection records found.</td></tr>`;
    return;
  }
  tbody.innerHTML = inspections.map((r, i) => {
    const oos = r.out_of_service === "Yes"
      ? `<span class="oos-yes">Yes</span>`
      : `<span class="oos-no">${r.out_of_service||"No"}</span>`;
    return `<tr>
      <td>${i+1}</td>
      <td>${r.inspection_date||"—"}</td>
      <td>${r.state||"—"}</td>
      <td style="white-space:nowrap">${r.report_number||"—"}</td>
      <td>${r.level||"—"}</td>
      <td>${r.basic||"—"}</td>
      <td style="max-width:220px">${r.violation_description||"—"}</td>
      <td>${oos}</td>
      <td>${r.violation_severity_weight||"—"}</td>
      <td>${r.unit||"—"}</td>
      <td style="font-size:0.78rem">${r.VIN||"—"}</td>
      <td style="font-size:0.78rem">${r["VIN.1"]||"—"}</td>
    </tr>`;
  }).join("");
}

function renderCrashes(crashes) {
  document.getElementById("crashTabCount").textContent = crashes.length;
  const tbody = document.getElementById("crashBody");
  if (!crashes.length) {
    tbody.innerHTML = `<tr><td colspan="9" class="empty-msg">No crash records found.</td></tr>`;
    return;
  }
  tbody.innerHTML = crashes.map((r, i) => `<tr>
    <td>${i+1}</td>
    <td>${r.crash_date||"—"}</td>
    <td>${r.state||"—"}</td>
    <td>${r.report_number||"—"}</td>
    <td>${r.fatalities||"0"}</td>
    <td>${r.injuries||"0"}</td>
    <td>${r.tow_away||"—"}</td>
    <td>${r.hm_released||"—"}</td>
    <td>${r.not_preventable||"—"}</td>
  </tr>`).join("");
}

function renderInsurance(insurance) {
  document.getElementById("insTabCount").textContent = insurance.length;
  const tbody = document.getElementById("insBody");
  if (!insurance.length) {
    tbody.innerHTML = `<tr><td colspan="7" class="empty-msg">No insurance history found.</td></tr>`;
    return;
  }
  tbody.innerHTML = insurance.map((r, i) => `<tr>
    <td>${i+1}</td>
    <td>${r.effective||"—"}</td>
    <td>${r.cancel_effective||"—"}</td>
    <td>${r.insurer||"—"}</td>
    <td>${r.policy||"—"}</td>
    <td>${r.coverage||"—"}</td>
    <td>${r.cancel_method||"—"}</td>
  </tr>`).join("");
}

function renderAuthority(authority) {
  document.getElementById("authTabCount").textContent = authority.length;
  const tbody = document.getElementById("authBody");
  if (!authority.length) {
    tbody.innerHTML = `<tr><td colspan="6" class="empty-msg">No authority history found.</td></tr>`;
    return;
  }
  tbody.innerHTML = authority.map((r, i) => `<tr>
    <td>${i+1}</td>
    <td>${r.served||"—"}</td>
    <td>${r.decided||"—"}</td>
    <td>${r.docket||"—"}</td>
    <td>${r.authority||"—"}</td>
    <td>${r.action||"—"}</td>
  </tr>`).join("");
}

async function initMap() {
  if (mapInitialized) return;
  try {
    // Load US TopoJSON from CDN
    const topo = await d3.json("https://cdn.jsdelivr.net/npm/us-atlas@3/states-10m.json");
    usTopoData = topo;
    mapInitialized = true;
  } catch(e) {
    console.error("Failed to load US map data:", e);
  }
}

function renderMap(mapData) {
  currentMapData = mapData;
  const container = document.getElementById("mapContainer");
  const svg = d3.select("#usMap");
  svg.selectAll("*").remove();

  const width = container.clientWidth || 900;
  const height = Math.round(width * 0.6);
  svg.attr("viewBox", `0 0 ${width} ${height}`)
     .attr("height", height);

  const projection = d3.geoAlbersUsa()
    .scale(width * 1.25)
    .translate([width / 2, height / 2]);

  const path = d3.geoPath().projection(projection);

  // Draw background
  svg.append("rect")
    .attr("width", width).attr("height", height)
    .attr("fill", "#eaf4fb");

  if (!usTopoData) {
    svg.append("text")
      .attr("x", width/2).attr("y", height/2)
      .attr("text-anchor", "middle").attr("fill", "#777")
      .text("Map data unavailable");
    return;
  }

  const states = topojson.feature(usTopoData, usTopoData.objects.states);

  // Draw states
  svg.append("g")
    .selectAll("path")
    .data(states.features)
    .join("path")
    .attr("d", path)
    .attr("fill", "#c8ddf0")
    .attr("stroke", "white")
    .attr("stroke-width", 1);

  // Draw state borders
  svg.append("path")
    .datum(topojson.mesh(usTopoData, usTopoData.objects.states, (a, b) => a !== b))
    .attr("d", path)
    .attr("fill", "none")
    .attr("stroke", "white")
    .attr("stroke-width", 1);

  if (!mapData || !mapData.length) return;

  const maxCount = Math.max(...mapData.map(d => d.count), 1);
  const tooltip = document.getElementById("mapTooltip");

  mapData.forEach(d => {
    const centroid = STATE_CENTROIDS[d.state];
    if (!centroid) return;

    // Project [lng, lat] to SVG coords
    const coords = projection([-centroid[0], centroid[1]]);
    if (!coords) return;

    const r = 8 + (d.count / maxCount) * 28;
    const oosRatio = d.oos_count / Math.max(d.count, 1);
    const color = oosRatio > 0.5 ? "#c0392b" : oosRatio > 0.2 ? "#e67e22" : "#2980b9";

    const g = svg.append("g").style("cursor", "pointer");

    g.append("circle")
      .attr("cx", coords[0]).attr("cy", coords[1])
      .attr("r", r)
      .attr("fill", color)
      .attr("opacity", 0.82)
      .attr("stroke", "white")
      .attr("stroke-width", 1.5);

    g.append("text")
      .attr("x", coords[0]).attr("y", coords[1] + 4)
      .attr("text-anchor", "middle")
      .attr("font-size", 9).attr("fill", "white")
      .attr("font-weight", "bold")
      .attr("pointer-events", "none")
      .text(d.state);

    g.on("mousemove", (event) => {
      tooltip.style.display = "block";
      tooltip.style.left = (event.clientX + 14) + "px";
      tooltip.style.top = (event.clientY - 10) + "px";
      tooltip.innerHTML = `<b>${d.state}</b><br>${d.count} inspection(s)<br>${d.oos_count} OOS (${Math.round(oosRatio*100)}%)`;
    }).on("mouseleave", () => { tooltip.style.display = "none"; });
  });
}

function switchTab(name) {
  document.querySelectorAll(".tab-btn").forEach((b, i) => {
    const tabs = ["inspections","crashes","insurance","authority","map"];
    b.classList.toggle("active", tabs[i] === name);
  });
  document.querySelectorAll(".tab-content").forEach(c => c.classList.remove("active"));
  document.getElementById("tab-" + name).classList.add("active");
  if (name === "map") {
    initMap().then(() => renderMap(currentMapData));
  }
}

async function fetchAll() {
  const dot = document.getElementById("dotInput").value.trim();
  if (!dot) { setStatus("Please enter a USDOT number.", true); return; }

  const btn = document.getElementById("searchBtn");
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner"></span> Loading...`;
  document.getElementById("companyCard").classList.add("hidden");
  document.getElementById("dataCard").classList.add("hidden");
  setStatus("Fetching carrier details, inspections, insurance and authority history — this may take 30–60 seconds...");

  try {
    const res = await fetch(`${API_BASE}/full/${dot}`);
    if (!res.ok) { const e = await res.json(); throw new Error(e.detail || "Request failed"); }
    const data = await res.json();

    renderCarrier(data.carrier);
    renderInspections(data.inspections || []);
    renderCrashes(data.crashes || []);
    renderInsurance(data.insurance_history || []);
    renderAuthority(data.authority_history || []);
    currentMapData = data.inspection_map || [];

    document.getElementById("dataCard").classList.remove("hidden");

    const warns = data.warnings?.length ? ` ⚠ ${data.warnings.join("; ")}` : "";
    setStatus(`✓ Loaded "${data.carrier?.legal_name || dot}" — ${(data.inspections||[]).length} inspection(s), ${(data.insurance_history||[]).length} insurance record(s).${warns}`);
  } catch (e) {
    setStatus(`Error: ${e.message}`, true);
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<i class="fas fa-search"></i> Search`;
    initMap();
  }
}

document.getElementById("dotInput").addEventListener("keydown", e => {
  if (e.key === "Enter") fetchAll();
});