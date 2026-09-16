(() => {
"use strict";
const root=document.getElementById("root");
let args={options:[],selected:[],placeholder:"Search and select components..."};
let selected=[],opened=false,query="";

function post(type,payload={}) {
  window.parent.postMessage(Object.assign({isStreamlitMessage:true,type},payload),"*");
}
function setHeight() {
  post("streamlit:setFrameHeight",{height:opened?405:50});
}
function emit() {
  post("streamlit:setComponentValue",{value:selected.slice()});
}
function options() {
  return Array.isArray(args.options)?args.options:[];
}
function values() {
  return options().map(o=>String(o.value||"")).filter(Boolean);
}
function filtered() {
  const q=String(query||"").trim().toLowerCase();
  if(!q) return options();
  return options().filter(o=>String(o.label||o.value||"").toLowerCase().includes(q));
}
function toggle(v) {
  v=String(v||"");
  if(!v) return;
  selected=selected.includes(v)?selected.filter(x=>x!==v):selected.concat(v);
  emit(); draw();
}
function toggleAll() {
  const vals=values();
  const all=vals.length>0&&vals.every(v=>selected.includes(v));
  selected=all?[]:vals.slice();
  emit(); draw();
}
function draw() {
  root.innerHTML="";
  const control=document.createElement("div");
  control.className="control"+(opened?" open":"");

  if(selected.length){
    const chips=document.createElement("div"); chips.className="chips";
    selected.slice(0,3).forEach(v=>{
      const chip=document.createElement("div"); chip.className="chip"; chip.textContent=v;
      chips.appendChild(chip);
    });
    if(selected.length>3){
      const more=document.createElement("div"); more.className="more";
      more.textContent="+"+(selected.length-3); chips.appendChild(more);
    }
    control.appendChild(chips);
  }

  const input=document.createElement("input");
  input.className="input"; input.type="text"; input.value=query;
  input.placeholder=selected.length?"":String(args.placeholder||"Search and select components...");
  input.addEventListener("focus",()=>{if(!opened){opened=true;draw();}});
  input.addEventListener("click",e=>{e.stopPropagation();if(!opened){opened=true;draw();}});
  input.addEventListener("input",e=>{query=e.target.value;opened=true;draw();});
  input.addEventListener("keydown",e=>{if(e.key==="Escape"){opened=false;query="";draw();}});
  control.appendChild(input);

  if(selected.length){
    const clear=document.createElement("div"); clear.className="clear"; clear.textContent="⊗";
    clear.title="Clear selections";
    clear.addEventListener("click",e=>{e.stopPropagation();selected=[];emit();draw();});
    control.appendChild(clear);
  }

  const arrow=document.createElement("div"); arrow.className="arrow";
  arrow.textContent=opened?"⌃":"⌄";
  arrow.addEventListener("click",e=>{e.stopPropagation();opened=!opened;if(!opened)query="";draw();});
  control.appendChild(arrow);
  root.appendChild(control);

  if(opened){
    const menu=document.createElement("div"); menu.className="menu";
    const vals=values();
    const allSelected=vals.length>0&&vals.every(v=>selected.includes(v));

    const allRow=document.createElement("div");
    allRow.className="row select-all";
    const allName=document.createElement("div"); allName.className="name"; allName.textContent="Select all";
    allRow.appendChild(allName);
    const allSpacer=document.createElement("div"); allSpacer.className="thumb-empty"; allRow.appendChild(allSpacer);
    const allCheck=document.createElement("div"); allCheck.className="check"; allCheck.textContent=allSelected?"✓":"";
    allRow.appendChild(allCheck);
    allRow.addEventListener("click",toggleAll);
    menu.appendChild(allRow);

    const rows=filtered().filter(row=>!selected.includes(String(row.value||"")));
    if(!rows.length){
      const empty=document.createElement("div"); empty.className="empty"; empty.textContent="No components found";
      menu.appendChild(empty);
    }else{
      rows.forEach(row=>{
        const value=String(row.value||"");
        const item=document.createElement("div"); item.className="row";

        const name=document.createElement("div"); name.className="name";
        name.textContent=String(row.label||value); item.appendChild(name);

        const b64=String(row.image_b64||"").trim();
        if(b64){
          const img=document.createElement("img"); img.className="thumb";
          img.src="data:image/png;base64,"+b64;
          img.alt=String(row.label||value)+" image";
          item.appendChild(img);
        }else{
          const spacer=document.createElement("div"); spacer.className="thumb-empty";
          item.appendChild(spacer);
        }

        const check=document.createElement("div"); check.className="check"; check.textContent="";
        item.appendChild(check);
        item.addEventListener("click",()=>toggle(value));
        menu.appendChild(item);
      });
    }
    root.appendChild(menu);
  }

  setHeight();
  if(opened){
    requestAnimationFrame(()=>{
      const f=root.querySelector(".input");
      if(f){
        f.focus({preventScroll:true});
        try{const n=f.value.length;f.setSelectionRange(n,n);}catch(_){}
      }
    });
  }
}

draw();

window.addEventListener("message",event=>{
  const data=event.data||{};
  if(!data.isStreamlitMessage||data.type!=="streamlit:render") return;
  args=data.args||args;
  const valid=new Set(values());
  const incoming=Array.isArray(args.selected)?args.selected.map(String):[];
  selected=incoming.filter(v=>valid.has(v));
  draw();
});

post("streamlit:componentReady",{apiVersion:1});
setHeight();
})();