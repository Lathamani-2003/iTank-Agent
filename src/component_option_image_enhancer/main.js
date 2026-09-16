(() => {
"use strict";

let imageMap = {};
let componentNames = new Set();
let observer = null;

function post(type, extra={}) {
  try {
    window.parent.postMessage(
      Object.assign({isStreamlitMessage:true, type}, extra),
      "*"
    );
  } catch (_) {}
}

function exactOptionName(el) {
  const text = String(el.innerText || el.textContent || "").replace(/\s+/g, " ").trim();
  if (componentNames.has(text)) return text;

  // Some BaseWeb/Streamlit versions add visually-hidden helper text.
  // Match only when one exact catalog component name is present.
  for (const name of componentNames) {
    if (text === name || text.startsWith(name + " ")) return name;
  }
  return "";
}

function enhanceOption(option) {
  if (!option || option.nodeType !== 1) return;

  const name = exactOptionName(option);
  if (!name || !imageMap[name]) return;

  // Never duplicate.
  if (option.querySelector(':scope > img[data-rts-component-option-image="1"]')) return;

  const img = document.createElement("img");
  img.src = imageMap[name];
  img.alt = "";
  img.setAttribute("data-rts-component-option-image", "1");
  img.style.width = "34px";
  img.style.height = "34px";
  img.style.objectFit = "contain";
  img.style.flex = "0 0 34px";
  img.style.marginLeft = "auto";
  img.style.marginRight = "8px";
  img.style.pointerEvents = "none";
  img.style.userSelect = "none";

  // Keep Streamlit's existing option layout, selection, hover and click behavior.
  option.style.display = "flex";
  option.style.alignItems = "center";
  option.appendChild(img);
}

function scan() {
  let doc;
  try {
    doc = window.parent.document;
  } catch (_) {
    return;
  }
  if (!doc) return;

  // Streamlit/BaseWeb dropdown rows use role=option. Exact-name filtering means
  // only the component selector rows receive images; Select all and connection
  // dropdown rows remain untouched.
  doc.querySelectorAll('[role="option"]').forEach(enhanceOption);
}

function startObserver() {
  let doc;
  try {
    doc = window.parent.document;
  } catch (_) {
    return;
  }
  if (!doc || !doc.body) return;

  if (observer) observer.disconnect();
  observer = new MutationObserver(() => scan());
  observer.observe(doc.body, {childList:true, subtree:true});
  scan();
}

window.addEventListener("message", event => {
  const data = event.data || {};
  if (!data.isStreamlitMessage || data.type !== "streamlit:render") return;

  const args = data.args || {};
  imageMap = (args.image_map && typeof args.image_map === "object") ? args.image_map : {};
  componentNames = new Set(
    Array.isArray(args.component_names) ? args.component_names.map(String) : []
  );

  startObserver();
  post("streamlit:setFrameHeight", {height:0});
});

post("streamlit:componentReady", {apiVersion:1});
post("streamlit:setFrameHeight", {height:0});
})();