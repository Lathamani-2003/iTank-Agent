(() => {
  "use strict";

  const READY = "streamlit:componentReady";
  const SET_VALUE = "streamlit:setComponentValue";
  const SET_HEIGHT = "streamlit:setFrameHeight";
  const RENDER = "streamlit:render";

  const root = document.getElementById("root");
  let currentArgs = {};
  let editing = false;
  let commitLocked = false;

  function post(type, extra = {}) {
    if (window.parent === window) return;
    window.parent.postMessage(Object.assign({isStreamlitMessage:true, type}, extra), "*");
  }

  function uid() {
    return `${Date.now().toString(36)}_${Math.random().toString(36).slice(2)}`;
  }

  function emit(type, extra = {}) {
    post(SET_VALUE, {value:Object.assign({type, event_id:uid()}, extra)});
  }

  function setHeight() {
    post(SET_HEIGHT, {height:40});
  }

  function activeWorksheet() {
    const worksheets = Array.isArray(currentArgs.worksheets) ? currentArgs.worksheets : [];
    const activeId = Number(currentArgs.active_id);
    return worksheets.find(item => Number(item.id) === activeId) || worksheets[0] || {id:activeId || 1, name:`Worksheet ${activeId || 1}`};
  }

  function renderRename(row) {
    editing = true;
    commitLocked = false;
    const active = activeWorksheet();
    row.innerHTML = "";

    const input = document.createElement("input");
    input.className = "rename-input";
    input.type = "text";
    input.value = String(active.name || "");
    input.setAttribute("aria-label", "Rename worksheet");

    const add = document.createElement("button");
    add.type = "button";
    add.className = "add-btn";
    add.textContent = "+";
    add.title = "Add a new worksheet";
    add.setAttribute("aria-label", "Add worksheet");
    add.addEventListener("click", () => emit("add"));

    const commit = () => {
      if (commitLocked) return;
      commitLocked = true;
      const name = input.value.trim();
      editing = false;
      if (name && name !== String(active.name || "")) {
        emit("rename", {worksheet_id:Number(active.id), name});
      } else {
        render(currentArgs);
      }
    };

    input.addEventListener("keydown", event => {
      if (event.key === "Enter") {
        event.preventDefault();
        commit();
      } else if (event.key === "Escape") {
        event.preventDefault();
        commitLocked = true;
        editing = false;
        render(currentArgs);
      }
    });
    input.addEventListener("blur", commit);

    row.appendChild(input);
    row.appendChild(add);
    requestAnimationFrame(() => {
      input.focus();
      input.select();
    });
    setHeight();
  }

  function render(args) {
    currentArgs = args || {};
    if (editing) return;

    root.innerHTML = "";
    const row = document.createElement("div");
    row.className = "ws-row";

    const select = document.createElement("select");
    select.setAttribute("aria-label", "Worksheet selection");
    select.title = "Select worksheet. Double-click the current worksheet name to rename it.";

    const worksheets = Array.isArray(currentArgs.worksheets) ? currentArgs.worksheets : [];
    const activeId = Number(currentArgs.active_id);
    worksheets.forEach(item => {
      const option = document.createElement("option");
      option.value = String(item.id);
      option.textContent = String(item.name || `Worksheet ${item.id}`);
      if (Number(item.id) === activeId) option.selected = true;
      select.appendChild(option);
    });

    select.addEventListener("change", () => {
      emit("select", {worksheet_id:Number(select.value)});
    });

    // The native dropdown retains normal single-click selection. A deliberate
    // double-click on the current worksheet control switches that same space to
    // an inline text field for direct renaming.
    select.addEventListener("dblclick", event => {
      event.preventDefault();
      renderRename(row);
    });

    const add = document.createElement("button");
    add.type = "button";
    add.className = "add-btn";
    add.textContent = "+";
    add.title = "Add a new worksheet";
    add.setAttribute("aria-label", "Add worksheet");
    add.addEventListener("click", () => emit("add"));

    row.appendChild(select);
    row.appendChild(add);
    root.appendChild(row);
    setHeight();
  }

  window.addEventListener("message", event => {
    const data = event.data;
    if (data && data.type === RENDER) render(data.args || {});
  });

  post(READY, {apiVersion:1});
  setTimeout(() => post(READY, {apiVersion:1}), 100);
  setHeight();
})();
