const API_BASE = "https://fmcsa-playwright.onrender.com/";

function setStatus(msg, isError = false) {
  const bar = document.getElementById("statusBar");
  bar.textContent = msg;
  bar.style.display = msg ? "block" : "none";
  bar.className = "status-bar" + (isError ? " error" : "");
}

function renderCarrier(carrier) {
  const card = document.getElementById("companyCard");
  const grid = document.getElementById("companyGrid");

  const fields = [
    { label: "Legal Name", value: carrier.legalName || carrier.legal_name || "—" },
    { label: "DBA Name", value: carrier.dbaName || carrier.dba_name || "—" },
    { label: "USDOT Number", value: carrier.dotNumber || carrier.dot_number || "—" },
    { label: "MC Number", value: carrier.mcNumber || carrier.mc_number || "—" },
    { label: "Phone", value: carrier.telephone || "—" },
    { label: "Address", value: carrier.phyStreet ? `${carrier.phyStreet}, ${carrier.phyCity}, ${carrier.phyState} ${carrier.phyZip}` : "—" },
    { label: "Safety Rating", value: carrier.safetyRating || carrier.safety_rating || "Not Rated", badge: true, badgeClass: (carrier.safetyRating || "").toLowerCase() },
    { label: "Power Units", value: carrier.totalPowerUnits || carrier.power_units || "—" },
    { label: "Drivers", value: carrier.totalDrivers || carrier.drivers || "—" },
    { label: "Carrier Operation", value: carrier.carrierOperation?.carrierOperationDesc || carrier.carrier_operation || "—" },
  ];

  grid.innerHTML = fields.map(f => `
    <div class="info-item">
      <label>${f.label}</label>
      <p>${f.badge
        ? `<span class="badge ${f.badgeClass}">${f.value}</span>`
        : f.value}
      </p>
    </div>
  `).join("");

  card.style.display = "block";
}

function renderInspections(inspections) {
  const card = document.getElementById("inspectionsCard");
  const tbody = document.getElementById("inspBody");
  document.getElementById("inspCount").textContent = inspections.length;

  if (!inspections.length) {
    tbody.innerHTML = `<tr><td colspan="9" style="text-align:center;color:#777;padding:20px">No inspection records found in the downloaded file.</td></tr>`;
  } else {
    tbody.innerHTML = inspections.map((r, i) => {
      const oos = (val) => val && val !== "0" && val !== ""
        ? `<span class="oos-yes">${val}</span>`
        : `<span class="oos-no">${val || "0"}</span>`;
      return `
        <tr>
          <td>${i + 1}</td>
          <td>${r.report_number || r["Report Number"] || "—"}</td>
          <td>${r.inspection_date || r["Inspection Date"] || "—"}</td>
          <td>${r.state || r["State"] || "—"}</td>
          <td>${r.level || r["Level"] || "—"}</td>
          <td>${oos(r.vehicle_oos || r["Vehicle OOS"])}</td>
          <td>${oos(r.driver_oos || r["Driver OOS"])}</td>
          <td>${oos(r.hazmat_oos || r["Hazmat OOS"])}</td>
          <td>${r.total_violations || r["Total Violations"] || "0"}</td>
        </tr>`;
    }).join("");
  }

  card.style.display = "block";
}

async function fetchAll() {
  const dot = document.getElementById("dotInput").value.trim();
  if (!dot) { setStatus("Please enter a USDOT number.", true); return; }

  const btn = document.getElementById("searchBtn");
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner"></span> Loading...`;
  document.getElementById("companyCard").style.display = "none";
  document.getElementById("inspectionsCard").style.display = "none";
  setStatus("Fetching carrier details and downloading SMS inspection file...");

  try {
    const res = await fetch(`${API_BASE}/full/${dot}`);
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Request failed");
    }
    const data = await res.json();
    renderCarrier(data.carrier);
    renderInspections(data.inspections);
    setStatus(`✓ Loaded carrier "${data.carrier?.legalName || dot}" with ${data.inspections.length} inspection records.`);
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