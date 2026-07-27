const API_BASE = "https://fmcsa-playwright.onrender.com";

// ================================================================
// PAGE NAVIGATION
// ================================================================
function showPage(name) {
  document.querySelectorAll(".page").forEach(p => p.classList.remove("active"));
  document.querySelectorAll(".nav-tab").forEach(t => t.classList.remove("active"));
  document.getElementById("page-" + name).classList.add("active");
  document.getElementById("tab-" + name).classList.add("active");
  if (name === "market" && !mktLoaded) doSearch(0);
}

// ================================================================
// MARKET EXPLORER
// ================================================================
let mktOffset = 0;
let mktTotal = 0;
let mktLimit = 50;
let mktLoaded = false;
let acTimer = null;

async function doSearch(offset) {
  mktOffset = offset;
  const btn = document.getElementById("mktBtn");
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner"></span> Loading...`;
  document.getElementById("mktBody").innerHTML =
    `<tr><td colspan="8" class="empty-msg"><span class="spinner"></span> Loading carriers...</td></tr>`;

  const params = new URLSearchParams({
    q:                document.getElementById("mktQuery").value.trim(),
    state:            document.getElementById("fState").value,
    status:           document.getElementById("fStatus").value,
    carrier_operation:document.getElementById("fOperation").value,
    hm_ind:           document.getElementById("fHazmat").value,
    bipd_only:        document.getElementById("fBipd").value === "1" ? "true" : "false",
    min_units:        document.getElementById("fMinUnits").value,
    max_units:        document.getElementById("fMaxUnits").value,
    order_by:         document.getElementById("fOrder").value,
    limit:            mktLimit,
    offset:           offset,
  });

  try {
    const res = await fetch(`${API_BASE}/market/search?${params}`);
    const data = await res.json();
    mktTotal = data.total || 0;
    mktLoaded = true;
    renderMarketTable(data.carriers || []);
    updatePagination();
  } catch (e) {
    document.getElementById("mktBody").innerHTML =
      `<tr><td colspan="8" class="empty-msg" style="color:#c0392b">Error: ${e.message}</td></tr>`;
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<i class="fas fa-sync-alt"></i> Refresh`;
  }
}

function renderMarketTable(carriers) {
  const body = document.getElementById("mktBody");
  document.getElementById("mktMeta").textContent =
    `${mktTotal.toLocaleString()} carrier${mktTotal !== 1 ? "s" : ""} found`;

  if (!carriers.length) {
    body.innerHTML = `<tr><td colspan="8" class="empty-msg">No carriers match your filters.</td></tr>`;
    return;
  }

  const opMap = { A: "Auth. For-Hire", B: "Exempt For-Hire", C: "Private", D: "Lease/Rental" };

  body.innerHTML = carriers.map(c => {
    const statusBadge = c.status === "A"
      ? `<span class="badge-active">Active</span>`
      : `<span class="badge-inactive">${c.status || "?"}</span>`;
    const hmBadge = c.hm_ind === "Y" ? `<span class="hm-badge">HM</span>` : "—";
    const bipdBadge = c.bipd_file === "Y"
      ? `<span class="badge-ins">BIPD on file</span>` : "—";
    const location = [c.city, c.state, c.zip].filter(Boolean).join(", ");
    const name = c.legal_name || "—";
    const dba = c.dba_name ? `<br><span style="font-size:0.75rem;color:#888">${c.dba_name}</span>` : "";
    const mcsDate = c.mcs150_date ? c.mcs150_date.split("T")[0] : "—";
    const fleet = c.power_units ? `PU ${c.power_units}${c.total_drivers ? " | DR " + c.total_drivers : ""}` : "—";

    return `<tr onclick="openCarrierProfile('${c.dot_number}')">
      <td><a class="dot-link" onclick="event.stopPropagation();openCarrierProfile('${c.dot_number}')">${c.dot_number}</a></td>
      <td>${name}${dba}</td>
      <td style="font-size:0.8rem">${location || "—"}</td>
      <td>${statusBadge}<br><span style="font-size:0.72rem;color:#777">${opMap[c.carrier_operation] || c.carrier_operation || ""}</span></td>
      <td style="white-space:nowrap">${fleet}</td>
      <td>${hmBadge}</td>
      <td>${bipdBadge}</td>
      <td style="font-size:0.8rem">${mcsDate}</td>
    </tr>`;
  }).join("");
}

function updatePagination() {
  const start = mktOffset + 1;
  const end = Math.min(mktOffset + mktLimit, mktTotal);
  document.getElementById("mktPageInfo").textContent =
    mktTotal ? `Showing ${start}–${end} of ${mktTotal.toLocaleString()}` : "";
  document.getElementById("btnPrev").disabled = mktOffset === 0;
  document.getElementById("btnNext").disabled = mktOffset + mktLimit >= mktTotal;
}

function changePage(dir) {
  doSearch(mktOffset + dir * mktLimit);
}

function openCarrierProfile(dot) {
  document.getElementById("profileDotInput").value = dot;
  showPage("profile");
  loadProfile();
}

// Autocomplete for market explorer
function onQueryInput() {
  clearTimeout(acTimer);
  const q = document.getElementById("mktQuery").value.trim();
  if (q.length < 2) {
    document.getElementById("acDropdown").classList.add("hidden");
    return;
  }
  acTimer = setTimeout(() => fetchAC(q, "acDropdown", (dot) => {
    document.getElementById("mktQuery").value = dot;
    document.getElementById("acDropdown").classList.add("hidden");
    doSearch(0);
  }), 280);
}

function onQueryKey(e) {
  if (e.key === "Enter") {
    document.getElementById("acDropdown").classList.add("hidden");
    doSearch(0);
  }
  if (e.key === "Escape") document.getElementById("acDropdown").classList.add("hidden");
}

async function fetchAC(q, dropdownId, onSelect) {
  try {
    const res = await fetch(`${API_BASE}/market/autocomplete?q=${encodeURIComponent(q)}`);
    const data = await res.json();
    const items = data.results || [];
    const dd = document.getElementById(dropdownId);
    if (!items.length) { dd.classList.add("hidden"); return; }
    dd.innerHTML = items.map(r => `
      <div class="ac-item" onclick='(${onSelect.toString()})("${r.dot_number}")'>
        <div>
          <div class="ac-name">${r.legal_name}</div>
          <div class="ac-meta">${r.location || ""}</div>
        </div>
        <div>
          <span class="ac-dot">${r.dot_number}</span>
        </div>
      </div>`).join("");
    dd.classList.remove("hidden");
  } catch(e) { /* ignore */ }
}

// Close dropdowns on outside click
document.addEventListener("click", e => {
  if (!e.target.closest("#acWrap")) document.getElementById("acDropdown")?.classList.add("hidden");
  if (!e.target.closest("#profileAcWrap")) document.getElementById("profileAcDropdown")?.classList.add("hidden");
});

// ================================================================
// CARRIER PROFILE
// ================================================================
let profileAcTimer = null;
let mapInitialized = false;
let usTopoData = null;
let currentMapData = { points: [], home: null };

function setProfileStatus(msg, isError = false) {
  const bar = document.getElementById("profileStatus");
  bar.textContent = msg;
  bar.style.display = msg ? "block" : "none";
  bar.className = "status-bar" + (isError ? " error" : "");
}

function onProfileInput() {
  clearTimeout(profileAcTimer);
  const q = document.getElementById("profileDotInput").value.trim();
  if (q.length < 2) {
    document.getElementById("profileAcDropdown").classList.add("hidden");
    return;
  }
  profileAcTimer = setTimeout(() => fetchAC(q, "profileAcDropdown", (dot) => {
    document.getElementById("profileDotInput").value = dot;
    document.getElementById("profileAcDropdown").classList.add("hidden");
    loadProfile();
  }), 280);
}

function onProfileKey(e) {
  if (e.key === "Enter") {
    document.getElementById("profileAcDropdown").classList.add("hidden");
    loadProfile();
  }
  if (e.key === "Escape") document.getElementById("profileAcDropdown").classList.add("hidden");
}

async function loadProfile() {
  const dot = document.getElementById("profileDotInput").value.trim();
  if (!dot) { setProfileStatus("Please enter a USDOT number.", true); return; }

  const btn = document.getElementById("profileSearchBtn");
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner"></span> Loading...`;
  document.getElementById("profileContent").classList.add("hidden");
  document.getElementById("companyCard").classList.add("hidden");
  document.getElementById("dataCard").classList.add("hidden");
  setProfileStatus("Fetching carrier details, inspections, insurance and authority history — may take 30–60 seconds...");

  try {
    const res = await fetch(`${API_BASE}/full/${dot}`);
    if (!res.ok) { const e = await res.json(); throw new Error(e.detail || "Request failed"); }
    const data = await res.json();

    renderCarrier(data.carrier);
    renderInspections(data.inspections || []);
    renderCrashes(data.crashes || []);
    renderInsurance(data.insurance_history || []);
    renderAuthority(data.authority_history || []);
    currentMapData = { points: data.inspection_points || [], home: data.home_location || null };

    document.getElementById("profileContent").classList.remove("hidden");
    document.getElementById("companyCard").classList.remove("hidden");
    document.getElementById("dataCard").classList.remove("hidden");

    // Switch to first tab
    switchTab("inspections");

    const warns = data.warnings?.length ? ` ⚠ ${data.warnings.join("; ")}` : "";
    setProfileStatus(`✓ Loaded "${data.carrier?.legal_name || dot}" — ${(data.inspections||[]).length} inspection(s), ${(data.insurance_history||[]).length} insurance record(s).${warns}`);
  } catch (e) {
    setProfileStatus(`Error: ${e.message}`, true);
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<i class="fas fa-search"></i> Search`;
    initMap();
  }
}

function switchTab(name) {
  document.querySelectorAll(".tab-btn").forEach((b, i) => {
    const tabs = ["inspections","crashes","insurance","authority","map"];
    b.classList.toggle("active", tabs[i] === name);
  });
  document.querySelectorAll(".tab-content").forEach(c => c.classList.remove("active"));
  document.getElementById("tab-" + name).classList.add("active");
  if (name === "map") initMap().then(() => renderMap(currentMapData.points, currentMapData.home));
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
}

function renderInspections(inspections) {
  document.getElementById("inspTabCount").textContent = inspections.length;
  const tbody = document.getElementById("inspBody");
  if (!inspections.length) {
    tbody.innerHTML = `<tr><td colspan="11" class="empty-msg">No inspection records found.</td></tr>`;
    return;
  }
  tbody.innerHTML = inspections.map((r, i) => {
    const oos = r.out_of_service === "Yes"
      ? `<span class="oos-yes">Yes</span>`
      : `<span class="oos-no">${r.out_of_service||"No"}</span>`;
    return `<tr>
      <td>${i+1}</td><td>${r.inspection_date||"—"}</td><td>${r.state||"—"}</td>
      <td style="white-space:nowrap">${r.report_number||"—"}</td>
      <td>${r.level||"—"}</td><td>${r.basic||"—"}</td>
      <td style="max-width:200px;font-size:0.8rem">${r.violation_description||"—"}</td>
      <td>${oos}</td><td>${r.violation_severity_weight||"—"}</td>
      <td style="font-size:0.76rem">${r.VIN||"—"}</td>
      <td style="font-size:0.76rem">${r["VIN.1"]||"—"}</td>
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
    <td>${(r.crash_date||r.date||"—").split("T")[0]}</td>
    <td>${r.state||r.report_state||"—"}</td>
    <td>${r.report_number||"—"}</td>
    <td>${r.fatalities||"0"}</td><td>${r.injuries||"0"}</td>
    <td>${r.tow_away||r.tow||"—"}</td>
    <td>${r.hm_released||r.haz_mat||"—"}</td>
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
    <td>${i+1}</td><td>${r.effective||"—"}</td><td>${r.cancel_effective||"—"}</td>
    <td>${r.insurer||"—"}</td><td>${r.policy||"—"}</td>
    <td>${r.coverage||"—"}</td><td>${r.cancel_method||"—"}</td>
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
    <td>${i+1}</td><td>${r.served||"—"}</td><td>${r.decided||"—"}</td>
    <td>${r.docket||"—"}</td><td>${r.authority||"—"}</td><td>${r.action||"—"}</td>
  </tr>`).join("");
}

// ================================================================
// MAP
// ================================================================
async function initMap() {
  if (mapInitialized) return;
  try {
    usTopoData = await d3.json("https://cdn.jsdelivr.net/npm/us-atlas@3/states-10m.json");
    mapInitialized = true;
  } catch(e) { console.error("Map load failed:", e); }
}

function renderMap(points, home) {
  const container = document.getElementById("mapContainer");
  const svg = d3.select("#usMap");
  svg.selectAll("*").remove();

  const width = container.clientWidth || 860;
  const height = Math.round(width * 0.58);
  svg.attr("viewBox", `0 0 ${width} ${height}`).attr("height", height);

  const projection = d3.geoAlbersUsa().scale(width * 1.25).translate([width/2, height/2]);
  const path = d3.geoPath().projection(projection);

  svg.append("rect").attr("width",width).attr("height",height).attr("fill","#eaf4fb");

  if (!usTopoData) {
    svg.append("text").attr("x",width/2).attr("y",height/2)
      .attr("text-anchor","middle").attr("fill","#777").text("Map data unavailable");
    return;
  }

  const states = topojson.feature(usTopoData, usTopoData.objects.states);
  svg.append("g").selectAll("path").data(states.features).join("path")
    .attr("d",path).attr("fill","#c8ddf0").attr("stroke","white").attr("stroke-width",1);
  svg.append("path")
    .datum(topojson.mesh(usTopoData, usTopoData.objects.states, (a,b)=>a!==b))
    .attr("d",path).attr("fill","none").attr("stroke","white").attr("stroke-width",1);

  const tooltip = document.getElementById("mapTooltip");

  if (points && points.length) {
    points.forEach(p => {
      const coords = projection([p.lng, p.lat]);
      if (!coords) return;
      const isOos = p.out_of_service === "Yes";
      const g = svg.append("g").style("cursor","pointer");
      g.append("circle")
        .attr("cx",coords[0]).attr("cy",coords[1]).attr("r",5)
        .attr("fill", isOos ? "#c0392b" : "#2980b9")
        .attr("opacity",0.75).attr("stroke","white").attr("stroke-width",0.8);
      g.on("mousemove", e => {
        tooltip.style.display = "block";
        tooltip.style.left = (e.clientX+14)+"px";
        tooltip.style.top  = (e.clientY-10)+"px";
        tooltip.innerHTML = `<b>${p.state} — ${p.inspection_date||"?"}</b><br>
          Report: ${p.report_number||"—"}<br>
          Lvl ${p.level||"?"} | ${p.basic||"No violation"}<br>
          OOS: ${isOos?"<span style='color:#ff8080'>Yes</span>":"No"}`;
      }).on("mouseleave", ()=>{ tooltip.style.display="none"; });
    });
  }

  if (home) {
    const coords = projection([home.lng, home.lat]);
    if (coords) {
      const g = svg.append("g").style("cursor","pointer");
      g.append("circle").attr("cx",coords[0]).attr("cy",coords[1]).attr("r",10)
        .attr("fill","#f39c12").attr("stroke","white").attr("stroke-width",2);
      g.append("text").attr("x",coords[0]).attr("y",coords[1]+4)
        .attr("text-anchor","middle").attr("font-size",10).attr("font-weight","bold")
        .attr("fill","white").attr("pointer-events","none").text("H");
      g.on("mousemove", e => {
        tooltip.style.display="block";
        tooltip.style.left=(e.clientX+14)+"px";
        tooltip.style.top=(e.clientY-10)+"px";
        tooltip.innerHTML=`<b>🏠 Carrier Home</b><br>${home.label||""}<br>${home.address||""}`;
      }).on("mouseleave",()=>{tooltip.style.display="none";});
    }
  }
}