function initSidebarMenu() {
  const triggers = document.querySelectorAll("[data-menu-trigger]");
  triggers.forEach((trigger) => {
    trigger.addEventListener("click", () => {
      const group = trigger.closest("[data-menu-group]");
      const submenu = group ? group.querySelector(":scope > [data-submenu]") : null;
      if (!group || !submenu) return;

      const isOpen = group.classList.contains("open");
      group.classList.toggle("open", !isOpen);
      submenu.classList.toggle("open", !isOpen);
    });
  });
}

function initTopbarPopups() {
  const quickLinksBtn = document.getElementById("quickLinksBtn");
  const quickLinksPopup = document.getElementById("quickLinksPopup");
  const profileMenuBtn = document.getElementById("profileMenuBtn");
  const profilePopup = document.getElementById("profilePopup");

  const closeAll = () => {
    if (quickLinksPopup) quickLinksPopup.classList.remove("open");
    if (profilePopup) profilePopup.classList.remove("open");
  };

  if (quickLinksBtn && quickLinksPopup) {
    quickLinksBtn.addEventListener("click", (event) => {
      event.stopPropagation();
      const isOpen = quickLinksPopup.classList.contains("open");
      closeAll();
      quickLinksPopup.classList.toggle("open", !isOpen);
    });
  }

  if (profileMenuBtn && profilePopup) {
    profileMenuBtn.addEventListener("click", (event) => {
      event.stopPropagation();
      const isOpen = profilePopup.classList.contains("open");
      closeAll();
      profilePopup.classList.toggle("open", !isOpen);
    });
  }

  document.addEventListener("click", closeAll);
}

function initDashboardFilters() {
  const tabWrap = document.getElementById("dashboardTabs");
  if (!tabWrap) return;

  const tabs = tabWrap.querySelectorAll("[data-dash-tab]");
  const cards = document.querySelectorAll("[data-dash-card]");
  const sections = document.querySelectorAll("[data-dash-section]");

  const applyFilter = (key) => {
    cards.forEach((card) => {
      const cardType = card.getAttribute("data-dash-card");
      card.classList.toggle("dash-hidden", key !== "all" && cardType !== key);
    });

    sections.forEach((section) => {
      const sectionType = section.getAttribute("data-dash-section");
      section.classList.toggle("dash-hidden", key !== "all" && sectionType !== key);
    });
  };

  tabs.forEach((tab) => {
    tab.addEventListener("click", (event) => {
      event.preventDefault();
      const key = tab.getAttribute("data-dash-tab") || "all";
      tabs.forEach((item) => item.classList.remove("active"));
      tab.classList.add("active");
      applyFilter(key);
    });
  });
}

function getSelectableTable(scopeNode) {
  if (!scopeNode) return null;
  const tables = Array.from(scopeNode.querySelectorAll("table"));
  for (const table of tables) {
    if (table.closest("[hidden]")) continue;
    const headSelect = table.querySelector("thead input[type='checkbox']");
    const rowSelect = table.querySelector("tbody input[type='checkbox']");
    if (headSelect && rowSelect) return table;
  }
  return null;
}

function getSelectionFromTable(table) {
  if (!table) return { allRows: [], selectedRows: [], headerCheckbox: null };
  const bodyRows = Array.from(table.querySelectorAll("tbody tr")).filter(
    (row) => !row.classList.contains("gr-empty-row")
  );
  const selectedRows = bodyRows.filter((row) => {
    const cb = row.querySelector("input[type='checkbox']");
    return !!(cb && cb.checked);
  });
  return {
    allRows: bodyRows,
    selectedRows: selectedRows,
    headerCheckbox: table.querySelector("thead input[type='checkbox']"),
  };
}

function syncHeaderCheckboxState(table) {
  if (!table) return;
  const selection = getSelectionFromTable(table);
  if (!selection.headerCheckbox) return;
  const total = selection.allRows.length;
  const checked = selection.selectedRows.length;
  selection.headerCheckbox.checked = total > 0 && checked === total;
  selection.headerCheckbox.indeterminate = checked > 0 && checked < total;
}

function ensureEmptyRow(table) {
  if (!table) return;
  const tbody = table.querySelector("tbody");
  const headCols = table.querySelectorAll("thead th").length || 1;
  if (!tbody) return;
  const hasRows = Array.from(tbody.querySelectorAll("tr")).some(
    (row) => !row.classList.contains("gr-empty-row")
  );
  if (hasRows) {
    const oldEmpty = tbody.querySelector(".gr-empty-row");
    if (oldEmpty) oldEmpty.remove();
    return;
  }
  if (!tbody.querySelector(".gr-empty-row")) {
    const row = document.createElement("tr");
    row.className = "gr-empty-row";
    row.innerHTML = `<td colspan="${headCols}">No data available in table</td>`;
    tbody.appendChild(row);
  }
}

function getCurrentPrintTitle(table) {
  const section = table ? table.closest("section") : null;
  const candidates = [
    section ? section.querySelector(".po-heading-bar h1") : null,
    document.querySelector(".po-heading-bar h1"),
    document.querySelector(".content-wrap > h1"),
    document.querySelector(".erp-topbar-title"),
  ];
  for (const el of candidates) {
    const text = (el && el.textContent ? el.textContent : "").trim();
    if (text) return text;
  }

  const activeMenuCandidates = [
    document.querySelector(".submenu-link.active"),
    document.querySelector(".submenu-trigger.active span"),
    document.querySelector(".menu-link.active .menu-label"),
    document.querySelector(".menu-trigger.active .menu-label"),
  ];
  for (const el of activeMenuCandidates) {
    const text = (el && el.textContent ? el.textContent : "").trim();
    if (text) return text;
  }

  const pageTitle = (document.title || "").replace(/\s*-\s*Smart ERP\s*$/i, "").trim();
  return pageTitle || "Report";
}

function printSelectedRows(table) {
  const selection = getSelectionFromTable(table);
  if (!selection.selectedRows.length) {
    window.alert("Select at least one row to print.");
    return;
  }
  const headers = Array.from(table.querySelectorAll("thead th"))
    .slice(1)
    .map((th) => (th.textContent || "").trim());
  const rowsHtml = selection.selectedRows
    .map((row) => {
      const cols = Array.from(row.cells)
        .slice(1)
        .map((td) => `<td>${(td.textContent || "").trim()}</td>`)
        .join("");
      return `<tr>${cols}</tr>`;
    })
    .join("");
  const docTitle = getCurrentPrintTitle(table);
  const html = `<!doctype html><html><head><meta charset="utf-8"><title>${docTitle}</title>
    <style>
      body{font-family:Arial,sans-serif;padding:20px;color:#222}
      h2{margin:0 0 12px;font-size:18px}
      table{border-collapse:collapse;width:100%}
      th,td{border:1px solid #bfc6ce;padding:8px;font-size:12px;text-align:left}
      th{background:#173940;color:#fff}
      @page{size:auto;margin:12mm}
    </style></head><body>
    <h2>${docTitle}</h2>
    <table><thead><tr>${headers.map((h) => `<th>${h}</th>`).join("")}</tr></thead>
    <tbody>${rowsHtml}</tbody></table></body></html>`;
  // Print via hidden iframe to avoid blank about:blank tabs in Edge.
  const frame = document.createElement("iframe");
  frame.style.position = "fixed";
  frame.style.right = "0";
  frame.style.bottom = "0";
  frame.style.width = "0";
  frame.style.height = "0";
  frame.style.border = "0";
  document.body.appendChild(frame);

  try {
    const frameDoc = frame.contentDocument || frame.contentWindow.document;
    frameDoc.open();
    frameDoc.write(html);
    frameDoc.close();
    setTimeout(() => {
      frame.contentWindow.focus();
      frame.contentWindow.print();
      setTimeout(() => {
        frame.remove();
      }, 1200);
    }, 250);
  } catch (_error) {
    frame.remove();
    window.alert("Unable to open print preview.");
  }
}

function deleteSelectedRows(table) {
  const selection = getSelectionFromTable(table);
  if (!selection.selectedRows.length) {
    window.alert("Select at least one row to delete.");
    return;
  }
  const ok = window.confirm(`Delete ${selection.selectedRows.length} selected row(s)?`);
  if (!ok) return;
  selection.selectedRows.forEach((row) => row.remove());
  if (selection.headerCheckbox) {
    selection.headerCheckbox.checked = false;
    selection.headerCheckbox.indeterminate = false;
  }
  ensureEmptyRow(table);
}

function initListPrintDeleteActions() {
  document.addEventListener("change", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLInputElement)) return;
    if (target.type !== "checkbox") return;
    const table = target.closest("table");
    if (!table) return;

    const headerCb = table.querySelector("thead input[type='checkbox']");
    if (headerCb && target === headerCb) {
      const rowCbs = table.querySelectorAll("tbody tr:not(.gr-empty-row) input[type='checkbox']");
      rowCbs.forEach((cb) => {
        cb.checked = headerCb.checked;
      });
      headerCb.indeterminate = false;
      return;
    }
    syncHeaderCheckboxState(table);
  });

  document.addEventListener("click", (event) => {
    const btn = event.target.closest(".gr-icon-btn");
    if (!btn) return;
    if (btn.hasAttribute("data-transfer-action")) return;

    const title = ((btn.getAttribute("title") || btn.getAttribute("aria-label") || "") + "").trim().toLowerCase();
    const isPrint = title === "print" || (!title && !btn.classList.contains("gr-delete-btn"));
    const isDelete = title === "delete" || btn.classList.contains("gr-delete-btn");
    if (!isPrint && !isDelete) return;

    const scope =
      btn.closest("section") ||
      btn.closest(".doc-body") ||
      btn.parentElement;
    const table = getSelectableTable(scope);
    if (!table) return;

    if (isPrint) {
      printSelectedRows(table);
      return;
    }
    if (isDelete) {
      deleteSelectedRows(table);
    }
  });
}

window.addEventListener("DOMContentLoaded", () => {
  initSidebarMenu();
  initTopbarPopups();
  initDashboardFilters();
  initListPrintDeleteActions();
});

function deleteSelectedRows() {
    const selected = document.querySelectorAll('.stock-checkbox:checked');
    
    if (selected.length === 0) {
        alert("Please select at least one item to delete.");
        return;
    }

    if (confirm("Are you sure you want to delete the selected items from the database?")) {
        const itemsToDelete = [];
        selected.forEach(cb => {
            itemsToDelete.push({
                name: cb.getAttribute('data-name'),
                location: cb.getAttribute('data-location')
            });
        });

        // Sending the delete request to the server
        fetch('/stock-analysis-delete/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': '{{ csrf_token }}'
            },
            body: JSON.stringify({ items: itemsToDelete })
        })
        .then(response => response.json())
        .then(data => {
            if (data.ok) {
                alert("Items deleted successfully.");
                location.reload(); // Refresh page to show updated list
            } else {
                alert("Error: " + data.error);
            }
        });
    }
}