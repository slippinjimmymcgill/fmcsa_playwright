const API_BASE = "https://fmcsa-playwright.onrender.com";

// US state positions on the SVG viewBox (x, y) mapped from lat/lng
const STATE_SVG = {
  AL:[670,380],AK:[130,480],AZ:[195,360],AR:[600,360],CA:[105,310],
  CO:[300,290],CT:[810,195],DE:[790,225],FL:[700,440],GA:[680,380],
  HI:[230,520],ID:[185,210],IL:[620,270],IN:[655,265],IA:[565,235],
  KS:[480,305],KY:[665,305],LA:[590,415],ME:[850,145],MD:[785,245],
  MA:[830,185],MI:[650,210],MN:[545,175],MS:[620,385],MO:[580,305],
  MT:[255,165],NE:[455,260],NV:[160,275],NH:[825,170],NJ:[800,225],
  NM:[280,360],NY:[780,195],NC:[730,330],ND:[450,165],OH:[695,255],
  OK:[490,355],OR:[130,200],PA:[760,230],RI:[830,195],SC:[715,360],
  SD:[450,215],TN:[655,340],TX:[450,415],UT:[220,290],VT:[815,165],
  VA:[750,285],WA:[145,155],WV:[730,270],WI:[610,200],WY:[285,225],
  DC:[785,255],
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
  // Clear existing dots but keep state paths
  svg.querySelectorAll(".map-dot, .map-label").forEach(e => e.remove());

  if (!mapData || !mapData.length) return;

  const maxCount = Math.max(...mapData.map(d => d.count), 1);
  const tooltip = document.getElementById("mapTooltip");

  mapData.forEach(d => {
    const pos = STATE_SVG[d.state];
    if (!pos) return;
    const r = 8 + (d.count / maxCount) * 28;
    const oosRatio = d.oos_count / d.count;
    const color = oosRatio > 0.5 ? "#c0392b" : oosRatio > 0.2 ? "#e67e22" : "#2980b9";

    const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    circle.setAttribute("cx", pos[0]);
    circle.setAttribute("cy", pos[1]);
    circle.setAttribute("r", r);
    circle.setAttribute("fill", color);
    circle.setAttribute("opacity", "0.75");
    circle.setAttribute("class", "map-dot");
    circle.style.cursor = "pointer";

    circle.addEventListener("mousemove", (e) => {
      tooltip.style.display = "block";
      tooltip.style.left = (e.clientX + 12) + "px";
      tooltip.style.top = (e.clientY - 10) + "px";
      tooltip.innerHTML = `<b>${d.state}</b><br>${d.count} inspection(s)<br>${d.oos_count} OOS`;
    });
    circle.addEventListener("mouseleave", () => { tooltip.style.display = "none"; });

    svg.appendChild(circle);

    // State label
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