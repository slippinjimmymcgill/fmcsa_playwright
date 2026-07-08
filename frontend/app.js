const API_BASE = "https://fmcsa-playwright.onrender.com";

// State label positions matching the new SVG paths (cx, cy of each state)
const STATE_SVG = {
  WA:[130,100], OR:[90,175], CA:[95,320], NV:[170,240], ID:[210,165],
  MT:[270,80],  WY:[295,175],UT:[210,265],CO:[295,245],AZ:[195,360],
  NM:[295,330], ND:[405,85], SD:[405,155],NE:[405,240],KS:[405,300],
  OK:[420,350], TX:[430,430],MN:[510,140],IA:[510,238],MO:[520,300],
  AR:[535,348], LA:[540,415],WI:[580,185],IL:[595,265],MS:[560,385],
  MI:[625,175], IN:[630,228],OH:[660,225],KY:[655,280],TN:[660,318],
  AL:[648,368], GA:[705,368],FL:[680,455],SC:[738,322],NC:[740,283],
  VA:[725,268], WV:[688,272],PA:[760,235],NY:[785,195],VT:[815,170],
  NH:[835,153], ME:[848,140],MA:[832,203],RI:[852,204],CT:[828,218],
  NJ:[788,238], DE:[793,260],MD:[778,258],DC:[782,261],
  AK:[150,525], HI:[300,550],
};

let currentMapData = [];

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

function renderMap(mapData) {
  currentMapData = mapData;
  const svg = document.getElementById("usMap");
  svg.querySelectorAll(".map-dot, .map-label").forEach(e => e.remove());
  if (!mapData || !mapData.length) return;

  const maxCount = Math.max(...mapData.map(d => d.count), 1);
  const tooltip = document.getElementById("mapTooltip");

  mapData.forEach(d => {
    const pos = STATE_SVG[d.state];
    if (!pos) return;
    const r = 10 + (d.count / maxCount) * 30;
    const oosRatio = d.oos_count / Math.max(d.count, 1);
    const color = oosRatio > 0.5 ? "#c0392b" : oosRatio > 0.2 ? "#e67e22" : "#2980b9";

    const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    circle.setAttribute("cx", pos[0]);
    circle.setAttribute("cy", pos[1]);
    circle.setAttribute("r", r);
    circle.setAttribute("fill", color);
    circle.setAttribute("opacity", "0.82");
    circle.setAttribute("class", "map-dot");
    circle.style.cursor = "pointer";
    circle.addEventListener("mousemove", e => {
      tooltip.style.display = "block";
      tooltip.style.left = (e.clientX + 14) + "px";
      tooltip.style.top = (e.clientY - 10) + "px";
      tooltip.innerHTML = `<b>${d.state}</b><br>${d.count} inspection(s)<br>${d.oos_count} OOS (${Math.round(oosRatio*100)}%)`;
    });
    circle.addEventListener("mouseleave", () => { tooltip.style.display = "none"; });
    svg.appendChild(circle);

    const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
    text.setAttribute("x", pos[0]);
    text.setAttribute("y", pos[1] + 4);
    text.setAttribute("text-anchor", "middle");
    text.setAttribute("font-size", "9");
    text.setAttribute("fill", "white");
    text.setAttribute("font-weight", "bold");
    text.setAttribute("class", "map-label");
    text.setAttribute("pointer-events", "none");
    text.textContent = d.state;
    svg.appendChild(text);
  });
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
  }
}

document.getElementById("dotInput").addEventListener("keydown", e => {
  if (e.key === "Enter") fetchAll();
});