(() => {
"use strict";

const root = document.getElementById("root");
let args = {
  options: [],
  selected: [],
  placeholder: "Search and select components..."
};
let selected = [];
let isOpen = false;
let query = "";

function send(type, payload = {}) {
  try {
    window.parent.postMessage(
      Object.assign({isStreamlitMessage:true, type}, payload),
      "*"
    );
  } catch (_) {}
}

function setFrameHeight() {
  send("streamlit:setFrameHeight", {height: isOpen ? 390 : 50});
}

function setValue() {
  send("streamlit:setComponentValue", {value: selected.slice()});
}

function allOptions() {
  return Array.isArray(args.options) ? args.options : [];
}

function values() {
  return allOptions().map(x => String(x.value || "")).filter(Boolean);
}

function filteredOptions() {
  const q = String(query || "").trim().toLowerCase();
  if (!q) return allOptions();
  return allOptions().filter(x =>
    String(x.label || x.value || "").toLowerCase().includes(q)
  );
}

function toggleOne(value) {
  value = String(value || "");
  if (!value) return;
  if (selected.includes(value)) selected = selected.filter(x => x !== value);
  else selected = selected.concat(value);
  setValue();
  render();
}

function toggleAll() {
  const vals = values();
  const every = vals.length > 0 && vals.every(v => selected.includes(v));
  selected = every ? [] : vals.slice();
  setValue();
  render();
}

function makeThumb(row) {
  const b64 = String(row && row.image_b64 || "");
  if (b64) {
    const img = document.createElement("img");
    img.className = "thumb";
    img.alt = "";
    img.src = "data:image/png;base64," + b64;
    return img;
  }
  const empty = document.createElement("div");
  empty.className = "thumb-empty";
  return empty;
}

function render() {
  root.innerHTML = "";

  const wrap = document.createElement("div");
  wrap.className = "wrap";

  const control = document.createElement("div");
  control.className = "control" + (isOpen ? " open" : "");

  if (selected.length > 0) {
    const summary = document.createElement("div");
    summary.className = "summary";

    const chip = document.createElement("span");
    chip.className = "chip";
    chip.textContent = selected[0];
    summary.appendChild(chip);

    if (selected.length > 1) {
      const more = document.createElement("span");
      more.className = "more";
      more.textContent = "+" + (selected.length - 1);
      summary.appendChild(more);
    }
    control.appendChild(summary);
  }

  const input = document.createElement("input");
  input.className = "input";
  input.type = "text";
  input.value = query;
  input.placeholder = selected.length ? "" : String(args.placeholder || "Search and select components...");
  input.setAttribute("aria-label", "Search and select components");
  input.addEventListener("focus", () => {
    if (!isOpen) {
      isOpen = true;
      render();
    }
  });
  input.addEventListener("input", e => {
    query = e.target.value;
    isOpen = true;
    render();
  });
  input.addEventListener("keydown", e => {
    if (e.key === "Escape") {
      isOpen = false;
      query = "";
      render();
    }
  });
  input.addEventListener("click", e => {
    e.stopPropagation();
    if (!isOpen) {
      isOpen = true;
      render();
    }
  });
  control.appendChild(input);

  const arrow = document.createElement("div");
  arrow.className = "arrow";
  arrow.textContent = isOpen ? "⌃" : "⌄";
  arrow.addEventListener("click", e => {
    e.stopPropagation();
    isOpen = !isOpen;
    if (!isOpen) query = "";
    render();
  });
  control.appendChild(arrow);

  control.addEventListener("click", () => {
    if (!isOpen) {
      isOpen = true;
      render();
    }
  });

  wrap.appendChild(control);

  if (isOpen) {
    const menu = document.createElement("div");
    menu.className = "menu";

    const vals = values();
    const allSelected = vals.length > 0 && vals.every(v => selected.includes(v));

    const allRow = document.createElement("div");
    allRow.className = "row select-all" + (allSelected ? " selected" : "");

    const allName = document.createElement("div");
    allName.className = "name";
    allName.textContent = "Select all";
    allRow.appendChild(allName);

    const spacer = document.createElement("div");
    spacer.className = "thumb-empty";
    allRow.appendChild(spacer);

    const allCheck = document.createElement("div");
    allCheck.className = "check";
    allCheck.textContent = allSelected ? "✓" : "";
    allRow.appendChild(allCheck);

    allRow.addEventListener("click", e => {
      e.stopPropagation();
      toggleAll();
    });
    menu.appendChild(allRow);

    const rows = filteredOptions();
    if (!rows.length) {
      const empty = document.createElement("div");
      empty.className = "empty";
      empty.textContent = "No components found";
      menu.appendChild(empty);
    } else {
      rows.forEach(row => {
        const value = String(row.value || "");
        const item = document.createElement("div");
        item.className = "row" + (selected.includes(value) ? " selected" : "");

        const name = document.createElement("div");
        name.className = "name";
        name.textContent = String(row.label || value);
        item.appendChild(name);

        item.appendChild(makeThumb(row));

        const check = document.createElement("div");
        check.className = "check";
        check.textContent = selected.includes(value) ? "✓" : "";
        item.appendChild(check);

        item.addEventListener("click", e => {
          e.stopPropagation();
          toggleOne(value);
        });
        menu.appendChild(item);
      });
    }

    wrap.appendChild(menu);
  }

  root.appendChild(wrap);
  setFrameHeight();

  if (isOpen) {
    requestAnimationFrame(() => {
      const field = root.querySelector(".input");
      if (field) {
        field.focus({preventScroll:true});
        try {
          const n = field.value.length;
          field.setSelectionRange(n, n);
        } catch (_) {}
      }
    });
  }
}

// IMPORTANT: render the visible search box immediately, before Streamlit sends args.
// This prevents the blank white component area shown in the user's screenshot.
render();

window.addEventListener("message", event => {
  const data = event.data || {};
  if (!data.isStreamlitMessage || data.type !== "streamlit:render") return;

  args = data.args || args;
  const incoming = Array.isArray(args.selected) ? args.selected.map(String) : [];
  const valid = new Set(values());
  selected = incoming.filter(v => valid.has(v));
  render();
});

send("streamlit:componentReady", {apiVersion:1});
setFrameHeight();
})();