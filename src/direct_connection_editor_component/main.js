(() => {
  "use strict";
  const READY="streamlit:componentReady", SET_VALUE="streamlit:setComponentValue", SET_HEIGHT="streamlit:setFrameHeight", RENDER="streamlit:render";
  const root=document.getElementById("root");
  let argsState={}, routes={}, components={}, selectedEdge=null, selectedComponents=new Set(), clipboard=[], drag=null, zoom=1, panX=0, panY=0, snap=true, grid=.25, lastHeight=-1, contextMenu=null, initialSnapshot=null, history=[], historyIndex=-1, dirty=false;
  const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
  const clonePoints=p=>(p||[]).map(q=>[Number(q[0]),Number(q[1])]);
  const cloneBox=b=>Array.isArray(b)&&b.length===4?b.map(Number):[0,0,1,1];
  const eid=()=>`${Date.now().toString(36)}_${Math.random().toString(36).slice(2)}`;
  function post(type,extra={}){if(window.parent===window)return;window.parent.postMessage(Object.assign({isStreamlitMessage:true,type},extra),"*");}
  function ready(){post(READY,{apiVersion:1});} function emit(type,extra={}){post(SET_VALUE,{value:Object.assign({type,event_id:eid()},extra)});}
  function snapshot(){return {routes:Object.values(routes).map(r=>({...r,points:clonePoints(r.points),original_points:clonePoints(r.original_points||r.points)})),components:Object.values(components).map(c=>({...c,box:cloneBox(c.box)}))};}
  function applySnapshot(state){routes={};components={};for(const r of (state?.routes||[])){const id=String(r.edge_id||"");if(id)routes[id]={...r,edge_id:id,points:clonePoints(r.points),original_points:clonePoints(r.original_points||r.points),hidden:!!r.hidden};}for(const c of (state?.components||[])){const id=String(c.instance_id||"");if(id)components[id]={...c,instance_id:id,box:cloneBox(c.box),hidden:!!c.hidden};}selectedEdge=null;selectedComponents.clear();renderOverlay();}
  function checkpoint(){const s=snapshot();history=history.slice(0,historyIndex+1);history.push(JSON.parse(JSON.stringify(s)));if(history.length>100)history=history.slice(-100);historyIndex=history.length-1;dirty=true;}
  function undoLocal(){if(historyIndex<=0)return;historyIndex--;applySnapshot(history[historyIndex]);dirty=historyIndex>0;}
  function redoLocal(){if(historyIndex>=history.length-1)return;historyIndex++;applySnapshot(history[historyIndex]);dirty=true;}
  function resetAllLocal(){if(!initialSnapshot)return;applySnapshot(JSON.parse(JSON.stringify(initialSnapshot)));checkpoint();}
  function duplicateIds(ids){let made=[];for(const id of ids){const src=components[id];if(!src||src.hidden)continue;const nid=`draft_${eid()}`;const b=cloneBox(src.box);b[0]+=0.30;b[1]+=0.30;components[nid]={...src,instance_id:nid,title:`${src.title||id} Copy`,box:b,hidden:false,draft_duplicate_of:id};made.push(nid);}if(made.length){selectedEdge=null;selectedComponents=new Set(made);checkpoint();renderOverlay();}}
  function setHeight(force=false){const h=Math.max(1,Math.ceil(root.getBoundingClientRect().height||document.body.scrollHeight||1));if(force||h!==lastHeight){lastHeight=h;post(SET_HEIGHT,{height:h});}}
  function svgEl(name,attrs={}){const e=document.createElementNS("http://www.w3.org/2000/svg",name);Object.entries(attrs).forEach(([k,v])=>e.setAttribute(k,String(v)));return e;}
  const ptsString=p=>(p||[]).map(q=>`${q[0]},${q[1]}`).join(" ");
  function snapPoint(p){return snap?[Math.round(p[0]/grid)*grid,Math.round(p[1]/grid)*grid]:[p[0],p[1]];}
  function canvasSize(){return [Number(argsState.canvas_width||1),Number(argsState.canvas_height||1)];}
  function clientToCanvas(svg,ev){const pt=svg.createSVGPoint();pt.x=ev.clientX;pt.y=ev.clientY;const m=svg.getScreenCTM();if(!m)return[0,0];const q=pt.matrixTransform(m.inverse());return[q.x,q.y];}
  function pointInBox(p,b){return b&&p[0]>=b[0]&&p[0]<=b[0]+b[2]&&p[1]>=b[1]&&p[1]<=b[1]+b[3];}
  function componentAt(p,exclude=null){const vals=Object.values(components).reverse();for(const c of vals){if(!c.hidden&&c.instance_id!==exclude&&pointInBox(p,c.box))return c;}return null;}
  function boundaryPoint(box,p){const [x,y,w,h]=box,rx=x+w,by=y+h,px=p[0],py=p[1],cx=clamp(px,x,rx),cy=clamp(py,y,by);const cand=[[Math.abs(px-x),[x,cy]],[Math.abs(px-rx),[rx,cy]],[Math.abs(py-y),[cx,y]],[Math.abs(py-by),[cx,by]]];cand.sort((a,b)=>a[0]-b[0]);return cand[0][1];}
  function sidePort(box,side){const [x,y,w,h]=box;if(side==="left")return[x,y+h/2];if(side==="right")return[x+w,y+h/2];if(side==="top")return[x+w/2,y];return[x+w/2,y+h];}
  function nearestSegment(points,p){let bi=0,bd=Infinity,bp=p;for(let i=0;i<points.length-1;i++){const a=points[i],b=points[i+1],vx=b[0]-a[0],vy=b[1]-a[1],l=vx*vx+vy*vy||1;let t=((p[0]-a[0])*vx+(p[1]-a[1])*vy)/l;t=clamp(t,0,1);const q=[a[0]+t*vx,a[1]+t*vy],d=(q[0]-p[0])**2+(q[1]-p[1])**2;if(d<bd){bd=d;bi=i;bp=q;}}return{index:bi,point:bp};}
  function addWaypoint(r,seg,p){const idx=clamp(seg+1,1,r.points.length-1);r.points.splice(idx,0,snapPoint(p));return idx;}
  function removeWaypoint(r,idx){if(!r||idx<=0||idx>=r.points.length-1)return false;r.points.splice(idx,1);return true;}
  function connectedRoutes(id){return Object.values(routes).filter(r=>!r.hidden&&(r.source===id||r.target===id));}
  function collectRoutePayload(ids){const set=new Set(ids||[]),out=[];Object.values(routes).forEach(r=>{if(set.has(r.source)||set.has(r.target))out.push({edge_id:r.edge_id,points:clonePoints(r.points),source:r.source,target:r.target,hidden:!!r.hidden});});return out;}
  function selectEdge(id){if(!routes[id]||routes[id].hidden)return;selectedEdge=id;selectedComponents.clear();closeContext();renderOverlay();root.focus({preventScroll:true});}
  function selectComponent(id,add=false){if(!components[id]||components[id].hidden)return;selectedEdge=null;if(!add)selectedComponents.clear();if(add&&selectedComponents.has(id))selectedComponents.delete(id);else selectedComponents.add(id);closeContext();renderOverlay();root.focus({preventScroll:true});}
  function deselect(){selectedEdge=null;selectedComponents.clear();closeContext();renderOverlay();}
  function createDefs(svg){const defs=svgEl("defs");for(const id of ["arrow"]){const m=svgEl("marker",{id,viewBox:"0 0 10 10",refX:"8",refY:"5",markerWidth:"5",markerHeight:"5",orient:"auto-start-reverse"});m.appendChild(svgEl("path",{d:"M 0 0 L 10 5 L 0 10 z",fill:"#ff7a00"}));defs.appendChild(m);}svg.appendChild(defs);}
  function applyArrow(line,r){if(r.direction==="target_to_source")line.setAttribute("marker-start","url(#arrow)");else if(r.direction!=="unknown")line.setAttribute("marker-end","url(#arrow)");}
  function drawRoute(g,r,selected=false){const under=svgEl("polyline",{points:ptsString(r.points),class:selected?"selected-underlay":"normal-underlay"});g.appendChild(under);const line=svgEl("polyline",{points:ptsString(r.points),class:selected?"selected-line":"normal-line",stroke:r.color||"#1473E6"});if(r.dotted)line.setAttribute("stroke-dasharray",".032 .11");applyArrow(line,r);g.appendChild(line);}
  function bindRouteHit(g,svg,r){const hit=svgEl("polyline",{points:ptsString(r.points),class:"hit-line"});hit.addEventListener("click",e=>{e.stopPropagation();selectEdge(r.edge_id);});hit.addEventListener("contextmenu",e=>{e.preventDefault();e.stopPropagation();selectEdge(r.edge_id);openContext(e.clientX,e.clientY,"edge",r.edge_id);});hit.addEventListener("dblclick",e=>{e.preventDefault();e.stopPropagation();selectEdge(r.edge_id);const n=nearestSegment(r.points,clientToCanvas(svg,e));addWaypoint(r,n.index,n.point);checkpoint();renderOverlay();});hit.addEventListener("pointerdown",e=>{if(e.button!==0)return;e.preventDefault();e.stopPropagation();selectEdge(r.edge_id);const p=clientToCanvas(svg,e),seg=nearestSegment(r.points,p).index;drag={kind:"segment",edgeId:r.edge_id,seg,start:p,base:clonePoints(r.points),pid:e.pointerId};try{svg.setPointerCapture(e.pointerId);}catch(_){}});g.appendChild(hit);}
  function moveSegment(r,p){const b=drag.base,a=b[drag.seg],c=b[drag.seg+1],dx=p[0]-drag.start[0],dy=p[1]-drag.start[1],horizontal=Math.abs(c[0]-a[0])>=Math.abs(c[1]-a[1]),last=b.length-2;if(drag.seg===0){const n=clonePoints(b);if(horizontal){const y=snapPoint([0,a[1]+dy])[1];r.points=[b[0],[b[0][0],y],[b[1][0],y],...n.slice(1)];}else{const x=snapPoint([a[0]+dx,0])[0];r.points=[b[0],[x,b[0][1]],[x,b[1][1]],...n.slice(1)];}return;}if(drag.seg===last){const pre=clonePoints(b.slice(0,-1)),end=b[b.length-1];if(horizontal){const y=snapPoint([0,a[1]+dy])[1];r.points=[...pre,[a[0],y],[end[0],y],end];}else{const x=snapPoint([a[0]+dx,0])[0];r.points=[...pre,[x,a[1]],[x,end[1]],end];}return;}const n=clonePoints(b);if(horizontal){const y=snapPoint([0,a[1]+dy])[1];n[drag.seg][1]=y;n[drag.seg+1][1]=y;}else{const x=snapPoint([a[0]+dx,0])[0];n[drag.seg][0]=x;n[drag.seg+1][0]=x;}r.points=n;}
  function drawLineHandles(g,svg,r){r.points.forEach((p,i)=>{const end=i===0||i===r.points.length-1,h=svgEl("rect",{x:p[0]-.07,y:p[1]-.07,width:.14,height:.14,rx:end?.035:.012,class:end?"endpoint":"waypoint"});h.addEventListener("pointerdown",e=>{e.preventDefault();e.stopPropagation();drag={kind:end?"endpoint":"waypoint",edgeId:r.edge_id,index:i,pid:e.pointerId};try{svg.setPointerCapture(e.pointerId);}catch(_){}});if(!end){const rm=e=>{e.preventDefault();e.stopPropagation();if(removeWaypoint(r,i)){checkpoint();renderOverlay();}};h.addEventListener("dblclick",rm);h.addEventListener("contextmenu",rm);}g.appendChild(h);});for(let i=0;i<r.points.length-1;i++){const a=r.points[i],b=r.points[i+1],m=[(a[0]+b[0])/2,(a[1]+b[1])/2],v=svgEl("circle",{cx:m[0],cy:m[1],r:.052,class:"virtual-point"});v.addEventListener("pointerdown",e=>{e.preventDefault();e.stopPropagation();const idx=addWaypoint(r,i,clientToCanvas(svg,e));drag={kind:"waypoint",edgeId:r.edge_id,index:idx,pid:e.pointerId};try{svg.setPointerCapture(e.pointerId);}catch(_){}renderOverlay();});g.appendChild(v);}}
  function drawComponent(g,svg,c){const [x,y,w,h]=c.box,img=svgEl("image",{x,y,width:w,height:h,href:`data:image/png;base64,${c.image_b64||""}`,class:"component-image",preserveAspectRatio:"none"});img.addEventListener("click",e=>{e.stopPropagation();selectComponent(c.instance_id,e.shiftKey||e.ctrlKey||e.metaKey);});img.addEventListener("contextmenu",e=>{e.preventDefault();e.stopPropagation();if(!selectedComponents.has(c.instance_id))selectComponent(c.instance_id,false);openContext(e.clientX,e.clientY,"component",c.instance_id);});img.addEventListener("pointerdown",e=>{if(e.button!==0)return;e.preventDefault();e.stopPropagation();if(!selectedComponents.has(c.instance_id))selectComponent(c.instance_id,e.shiftKey||e.ctrlKey||e.metaKey);const p=clientToCanvas(svg,e),ids=[...selectedComponents],boxes=Object.fromEntries(ids.map(id=>[id,cloneBox(components[id].box)])),routeBase=Object.fromEntries(Object.values(routes).map(r=>[r.edge_id,clonePoints(r.points)]));drag={kind:"components",ids,start:p,boxes,routeBase,pid:e.pointerId};try{svg.setPointerCapture(e.pointerId);}catch(_){}});g.appendChild(img);}
  function drawSelection(g,svg,c){const [x,y,w,h]=c.box;g.appendChild(svgEl("rect",{x,y,width:w,height:h,class:"component-selection"}));if(selectedComponents.size===1){const size=.13;for(const [name,cx,cy] of [["nw",x,y],["ne",x+w,y],["sw",x,y+h],["se",x+w,y+h]]){const hnd=svgEl("rect",{x:cx-size/2,y:cy-size/2,width:size,height:size,class:`resize-handle resize-${name}`});hnd.addEventListener("pointerdown",e=>{e.preventDefault();e.stopPropagation();drag={kind:"resize",id:c.instance_id,corner:name,start:clientToCanvas(svg,e),box:cloneBox(c.box),pid:e.pointerId};try{svg.setPointerCapture(e.pointerId);}catch(_){}});g.appendChild(hnd);}for(const side of ["left","right","top","bottom"]){const p=sidePort(c.box,side),ph=svgEl("circle",{cx:p[0],cy:p[1],r:.065,class:"port-handle"});ph.addEventListener("pointerdown",e=>{e.preventDefault();e.stopPropagation();drag={kind:"newConnection",source:c.instance_id,start:p,current:p,pid:e.pointerId};try{svg.setPointerCapture(e.pointerId);}catch(_){}renderOverlay();});g.appendChild(ph);}}}
  function moveSelected(p){const dx=snapPoint([p[0]-drag.start[0],p[1]-drag.start[1]])[0],dy=snapPoint([p[0]-drag.start[0],p[1]-drag.start[1]])[1];for(const id of drag.ids){const b=drag.boxes[id];components[id].box=[b[0]+dx,b[1]+dy,b[2],b[3]];}for(const [rid,pts] of Object.entries(drag.routeBase))routes[rid].points=clonePoints(pts);for(const id of drag.ids){for(const r of connectedRoutes(id)){if(r.source===id){r.points[0][0]+=dx;r.points[0][1]+=dy;if(r.points.length>2){r.points[1][0]+=dx;r.points[1][1]+=dy;}}if(r.target===id){const n=r.points.length;r.points[n-1][0]+=dx;r.points[n-1][1]+=dy;if(n>2){r.points[n-2][0]+=dx;r.points[n-2][1]+=dy;}}}}}
  function drawGrid(g){if(!snap)return;const [w,h]=canvasSize();for(let x=0;x<=w;x+=grid)g.appendChild(svgEl("line",{x1:x,y1:0,x2:x,y2:h,class:"grid-line"}));for(let y=0;y<=h;y+=grid)g.appendChild(svgEl("line",{x1:0,y1:y,x2:w,y2:y,class:"grid-line"}));}
  function renderOverlay(){const svg=document.getElementById("editorSvg");if(!svg)return;const g=document.getElementById("scene");g.innerHTML="";createDefs(g);drawGrid(g);const bg=svgEl("image",{x:0,y:0,width:canvasSize()[0],height:canvasSize()[1],href:`data:image/png;base64,${argsState.image_b64||""}`,preserveAspectRatio:"none",style:"pointer-events:none"});g.appendChild(bg);Object.values(routes).forEach(r=>{if(!r.hidden)drawRoute(g,r,r.edge_id===selectedEdge);});Object.values(routes).forEach(r=>{if(!r.hidden)bindRouteHit(g,svg,r);});Object.values(components).forEach(c=>{if(!c.hidden)drawComponent(g,svg,c);});if(selectedEdge&&routes[selectedEdge]&&!routes[selectedEdge].hidden)drawLineHandles(g,svg,routes[selectedEdge]);for(const id of selectedComponents){const c=components[id];if(c&&!c.hidden)drawSelection(g,svg,c);}if(drag&&drag.kind==="marquee"){const x=Math.min(drag.start[0],drag.current[0]),y=Math.min(drag.start[1],drag.current[1]),w=Math.abs(drag.current[0]-drag.start[0]),h=Math.abs(drag.current[1]-drag.start[1]);g.appendChild(svgEl("rect",{x,y,width:w,height:h,class:"marquee"}));}if(drag&&drag.kind==="newConnection"){const a=drag.start,b=drag.current,mx=(a[0]+b[0])/2;g.appendChild(svgEl("polyline",{points:ptsString([a,[mx,a[1]],[mx,b[1]],b]),class:"connect-preview"}));}}
  function updateView(){const svg=document.getElementById("editorSvg");if(!svg)return;const [w,h]=canvasSize(),vw=w/zoom,vh=h/zoom;svg.setAttribute("viewBox",`${panX} ${panY} ${vw} ${vh}`);const z=document.getElementById("zoomLabel");if(z)z.textContent=`${Math.round(zoom*100)}%`;}
  function fit(){zoom=1;panX=0;panY=0;updateView();}
  function zoomBy(factor){const [w,h]=canvasSize(),oldW=w/zoom,oldH=h/zoom,cx=panX+oldW/2,cy=panY+oldH/2;zoom=clamp(zoom*factor,.35,4);const nw=w/zoom,nh=h/zoom;panX=cx-nw/2;panY=cy-nh/2;updateView();}
  function align(kind){const ids=[...selectedComponents].filter(id=>components[id]&&!components[id].hidden);if(ids.length<2)return;const boxes=ids.map(id=>components[id].box);if(kind==="h"){const cy=boxes.reduce((s,b)=>s+b[1]+b[3]/2,0)/boxes.length;ids.forEach(id=>{const b=components[id].box,dy=cy-(b[1]+b[3]/2);b[1]+=dy;connectedRoutes(id).forEach(r=>{if(r.source===id){r.points[0][1]+=dy;if(r.points.length>2)r.points[1][1]+=dy;}if(r.target===id){const n=r.points.length;r.points[n-1][1]+=dy;if(n>2)r.points[n-2][1]+=dy;}});});}else{const cx=boxes.reduce((s,b)=>s+b[0]+b[2]/2,0)/boxes.length;ids.forEach(id=>{const b=components[id].box,dx=cx-(b[0]+b[2]/2);b[0]+=dx;connectedRoutes(id).forEach(r=>{if(r.source===id){r.points[0][0]+=dx;if(r.points.length>2)r.points[1][0]+=dx;}if(r.target===id){const n=r.points.length;r.points[n-1][0]+=dx;if(n>2)r.points[n-2][0]+=dx;}});});}checkpoint();renderOverlay();}
  function emitComponentBatch(ids){checkpoint();}
  function openContext(x,y,type,id){closeContext();const menu=document.createElement("div");menu.className="context";menu.style.left=`${Math.min(x,window.innerWidth-170)}px`;menu.style.top=`${Math.min(y,window.innerHeight-180)}px`;const add=(label,fn,danger=false)=>{const b=document.createElement("button");b.type="button";b.textContent=label;if(danger)b.className="danger";b.addEventListener("click",()=>{fn();closeContext();});menu.appendChild(b);};if(type==="edge"){add("Reverse direction",()=>{const r=routes[id];r.direction=r.direction==="target_to_source"?"source_to_target":"target_to_source";checkpoint();renderOverlay();});add("Reset route",()=>{const r=routes[id];r.points=clonePoints(r.original_points||r.points);r.direction=r.original_direction||"source_to_target";r.hidden=false;checkpoint();renderOverlay();});add("Delete connection",()=>{routes[id].hidden=true;selectedEdge=null;checkpoint();renderOverlay();},true);}else{add("Duplicate",()=>duplicateIds([...selectedComponents]));add("Copy",()=>{clipboard=[...selectedComponents];});add("Delete",()=>deleteSelection(),true);}document.body.appendChild(menu);contextMenu=menu;}
  function closeContext(){if(contextMenu){contextMenu.remove();contextMenu=null;}}
  function deleteSelection(){
    // Delete a selected connection by itself, exactly as before.
    if(selectedEdge){
      const edge=routes[selectedEdge];
      if(edge)edge.hidden=true;
      selectedEdge=null;
      checkpoint();
      renderOverlay();
      return;
    }

    // Delete selected component instance(s) as one edit transaction.  This works
    // for original editable components as well as components created by Duplicate/
    // Paste.  Any connection whose current source OR target is one of the deleted
    // instances is removed visually at the same time, including manual connections
    // and lines that were reconnected during this edit session.
    const ids=[...selectedComponents].filter(id=>components[id]&&!components[id].hidden);
    if(!ids.length)return;
    const deleted=new Set(ids);

    for(const id of ids){
      components[id].hidden=true;
      components[id].deleted_by_user=true;
    }

    for(const r of Object.values(routes)){
      if(deleted.has(String(r.source||""))||deleted.has(String(r.target||""))){
        r.hidden=true;
        r.deleted_with_component=true;
      }
    }

    if(selectedEdge&&routes[selectedEdge]&&routes[selectedEdge].hidden)selectedEdge=null;
    selectedComponents.clear();
    clipboard=clipboard.filter(id=>!deleted.has(id));
    checkpoint();
    renderOverlay();
  }
  function copySelection(){clipboard=[...selectedComponents];}
  function pasteSelection(){if(clipboard.length)duplicateIds(clipboard);}
  async function saveEditor(){const b=document.getElementById("saveEditorBtn");if(b){b.disabled=true;b.textContent="Saving...";}try{const image_b64=await composeEditedPng();emit("save_editor",{image_b64,routes:Object.values(routes).map(r=>({...r,points:clonePoints(r.points)})),components:Object.values(components).map(c=>({...c,box:cloneBox(c.box)})),canvas_width:canvasSize()[0],canvas_height:canvasSize()[1]});}catch(err){console.error(err);alert("Could not save the edited diagram. Please try again.");if(b){b.disabled=false;b.textContent="Save";}}}
  function loadImage(src){return new Promise((resolve,reject)=>{const img=new Image();img.onload=()=>resolve(img);img.onerror=reject;img.src=src;});}
  async function composeEditedPng(){const [cw,ch]=canvasSize();const bg=await loadImage(`data:image/png;base64,${argsState.image_b64||""}`);const canvas=document.createElement("canvas");canvas.width=bg.naturalWidth||1600;canvas.height=bg.naturalHeight||900;const ctx=canvas.getContext("2d");ctx.drawImage(bg,0,0,canvas.width,canvas.height);const sx=canvas.width/cw,sy=canvas.height/ch;ctx.save();ctx.scale(sx,sy);for(const r of Object.values(routes)){if(r.hidden||!r.points?.length)continue;ctx.lineJoin="round";ctx.lineCap="round";ctx.strokeStyle="#fff";ctx.lineWidth=.15;ctx.setLineDash([]);drawCanvasPolyline(ctx,r.points);ctx.strokeStyle=r.color||"#1473E6";ctx.lineWidth=.052;ctx.setLineDash(r.dotted?[.04,.11]:[]);drawCanvasPolyline(ctx,r.points);drawCanvasArrow(ctx,r);}ctx.restore();for(const c of Object.values(components)){if(c.hidden||!c.image_b64)continue;try{const img=await loadImage(`data:image/png;base64,${c.image_b64}`);const [x,y,w,h]=c.box;ctx.drawImage(img,x*sx,y*sy,w*sx,h*sy);}catch(_){}}return canvas.toDataURL("image/png").split(",")[1];}
  function drawCanvasPolyline(ctx,pts){ctx.beginPath();ctx.moveTo(pts[0][0],pts[0][1]);for(let i=1;i<pts.length;i++)ctx.lineTo(pts[i][0],pts[i][1]);ctx.stroke();}
  function drawCanvasArrow(ctx,r){if(r.direction==="unknown"||r.points.length<2)return;const rev=r.direction==="target_to_source";const tip=rev?r.points[0]:r.points[r.points.length-1],prev=rev?r.points[1]:r.points[r.points.length-2],ang=Math.atan2(tip[1]-prev[1],tip[0]-prev[0]),size=.16;ctx.save();ctx.fillStyle="#ff7a00";ctx.beginPath();ctx.moveTo(tip[0],tip[1]);ctx.lineTo(tip[0]-size*Math.cos(ang-.55),tip[1]-size*Math.sin(ang-.55));ctx.lineTo(tip[0]-size*Math.cos(ang+.55),tip[1]-size*Math.sin(ang+.55));ctx.closePath();ctx.fill();ctx.restore();}
  function renderToolbar(){const bar=document.createElement("div");bar.className="toolbar";const btn=(txt,title,fn,id)=>{const b=document.createElement("button");b.type="button";b.textContent=txt;b.title=title;b.addEventListener("click",fn);if(id)b.id=id;bar.appendChild(b);return b;};btn("↶","Undo (Ctrl+Z)",undoLocal);btn("↷","Redo (Ctrl+Y)",redoLocal);const d=()=>bar.appendChild(Object.assign(document.createElement("span"),{className:"divider"}));d();btn("Copy","Copy (Ctrl+C)",copySelection);btn("Paste","Paste (Ctrl+V)",pasteSelection);btn("Duplicate","Duplicate selected components (Ctrl+D)",()=>duplicateIds([...selectedComponents]));btn("Delete","Delete selection",deleteSelection);d();btn("−","Zoom out",()=>zoomBy(.85));const zl=document.createElement("span");zl.id="zoomLabel";zl.className="zoom-label";zl.textContent="100%";bar.appendChild(zl);btn("+","Zoom in",()=>zoomBy(1.18));btn("Fit","Fit to screen",fit);d();const sb=btn("Snap","Snap to grid",()=>{snap=!snap;sb.classList.toggle("active",snap);renderOverlay();});sb.classList.toggle("active",snap);btn("Align H","Align selected horizontally",()=>align("h"));btn("Align V","Align selected vertically",()=>align("v"));d();btn("Reset","Reset to original generated layout",()=>{if(confirm("Reset all manual diagram edits to the original generated layout?"))resetAllLocal();});d();const save=btn("Save","Save all edits to Worksheet",saveEditor,"saveEditorBtn");save.classList.add("save-button");const h=document.createElement("span");h.className="hint";h.textContent="All changes stay in Edit Mode until Save";bar.appendChild(h);return bar;}
  function finishDrag(svg,e){if(!drag||drag.pid!==e.pointerId)return;const d=drag;drag=null;try{svg.releasePointerCapture(e.pointerId);}catch(_){}if(d.kind==="segment"||d.kind==="waypoint"||d.kind==="endpoint"||d.kind==="components"||d.kind==="resize"){checkpoint();}else if(d.kind==="marquee"){const x1=Math.min(d.start[0],d.current[0]),x2=Math.max(d.start[0],d.current[0]),y1=Math.min(d.start[1],d.current[1]),y2=Math.max(d.start[1],d.current[1]);selectedComponents.clear();Object.values(components).forEach(c=>{if(!c.hidden&&c.box[0]>=x1&&c.box[1]>=y1&&c.box[0]+c.box[2]<=x2&&c.box[1]+c.box[3]<=y2)selectedComponents.add(c.instance_id);});renderOverlay();}else if(d.kind==="newConnection"){const target=componentAt(d.current,d.source);if(target){const sp=boundaryPoint(components[d.source].box,d.start),tp=boundaryPoint(target.box,d.current),mx=(sp[0]+tp[0])/2,pts=[sp,[mx,sp[1]],[mx,tp[1]],tp],rid=`manual_${eid()}`;routes[rid]={edge_id:rid,label:"Manual connection",source:d.source,target:target.instance_id,points:pts,original_points:clonePoints(pts),direction:"source_to_target",original_direction:"source_to_target",color:"#1473E6",dotted:false,hidden:false,custom:true};checkpoint();}renderOverlay();}}
  function renderEditor(){root.innerHTML="";root.appendChild(renderToolbar());const wrap=document.createElement("div");wrap.className="stage-wrap";const [w,h]=canvasSize(),svg=svgEl("svg",{id:"editorSvg",viewBox:`0 0 ${w} ${h}`,preserveAspectRatio:"xMidYMid meet"}),scene=svgEl("g",{id:"scene"});svg.appendChild(scene);wrap.appendChild(svg);root.appendChild(wrap);svg.addEventListener("pointerdown",e=>{closeContext();if(e.target===svg||e.target===scene){const p=clientToCanvas(svg,e);if(e.button===1||e.altKey){drag={kind:"pan",startClient:[e.clientX,e.clientY],startPan:[panX,panY],pid:e.pointerId};}else{selectedEdge=null;if(!e.shiftKey)selectedComponents.clear();drag={kind:"marquee",start:p,current:p,pid:e.pointerId};}try{svg.setPointerCapture(e.pointerId);}catch(_){}renderOverlay();}});svg.addEventListener("pointermove",e=>{if(!drag||drag.pid!==e.pointerId)return;e.preventDefault();const p=clientToCanvas(svg,e);if(drag.kind==="segment")moveSegment(routes[drag.edgeId],p);else if(drag.kind==="waypoint")routes[drag.edgeId].points[drag.index]=snapPoint(p);else if(drag.kind==="endpoint"){const r=routes[drag.edgeId],idx=drag.index,isSource=idx===0,c=componentAt(p,null);if(c){r.points[idx]=boundaryPoint(c.box,p);if(isSource)r.source=c.instance_id;else r.target=c.instance_id;}else{const box=components[isSource?r.source:r.target]?.box||(isSource?r.source_box:r.target_box);r.points[idx]=boundaryPoint(box,p);}}else if(drag.kind==="components")moveSelected(p);else if(drag.kind==="resize"){const c=components[drag.id],[bx,by,bw,bh]=drag.box,minW=.35,minH=.25;let x=bx,y=by,ww=bw,hh=bh;if(drag.corner.includes("e"))ww=Math.max(minW,p[0]-bx);if(drag.corner.includes("s"))hh=Math.max(minH,p[1]-by);if(drag.corner.includes("w")){x=Math.min(p[0],bx+bw-minW);ww=bx+bw-x;}if(drag.corner.includes("n")){y=Math.min(p[1],by+bh-minH);hh=by+bh-y;}c.box=[...snapPoint([x,y]),Math.max(minW,snap?Math.round(ww/grid)*grid:ww),Math.max(minH,snap?Math.round(hh/grid)*grid:hh)];connectedRoutes(c.instance_id).forEach(r=>{if(r.source===c.instance_id)r.points[0]=boundaryPoint(c.box,r.points[0]);if(r.target===c.instance_id)r.points[r.points.length-1]=boundaryPoint(c.box,r.points[r.points.length-1]);});}else if(drag.kind==="marquee"){drag.current=p;}else if(drag.kind==="newConnection"){drag.current=p;}else if(drag.kind==="pan"){const rect=svg.getBoundingClientRect(),vw=w/zoom,vh=h/zoom;panX=drag.startPan[0]-(e.clientX-drag.startClient[0])/rect.width*vw;panY=drag.startPan[1]-(e.clientY-drag.startClient[1])/rect.height*vh;updateView();return;}renderOverlay();});svg.addEventListener("pointerup",e=>finishDrag(svg,e));svg.addEventListener("pointercancel",e=>{if(drag&&drag.pid===e.pointerId)drag=null;});svg.addEventListener("wheel",e=>{e.preventDefault();zoomBy(e.deltaY<0?1.12:.89);},{passive:false});renderOverlay();updateView();setHeight(true);}

  function renderDragOnly(){
    root.innerHTML="";
    root.style.position="relative";
    root.style.width="100%";
    root.style.minHeight="1px";
    root.style.overflow="hidden";
    root.style.userSelect="none";
    root.style.touchAction="none";

    const [cw,ch]=canvasSize();
    const fixedScreenHeight=Math.max(1,Number(argsState.fixed_screen_height||700));
    if(argsState.fit_screen)root.style.height=`${fixedScreenHeight}px`;
    else root.style.height="auto";

    const stage=document.createElement("div");
    stage.style.cssText=argsState.fit_screen
      ? "position:relative;width:100%;height:100%;overflow:hidden;touch-action:none;user-select:none;"
      : `position:relative;width:100%;aspect-ratio:${cw}/${ch};overflow:hidden;touch-action:none;user-select:none;`;
    root.appendChild(stage);

    const bg=document.createElement("img");
    bg.src=`data:image/png;base64,${argsState.image_b64||""}`;
    bg.draggable=false;
    bg.style.cssText="position:absolute;inset:0;width:100%;height:100%;object-fit:fill;display:block;pointer-events:none;user-select:none;";
    stage.appendChild(bg);

    // Live route layer. The Worksheet background intentionally contains no
    // components/connections while drag-only mode is active.
    const routeSvg=document.createElementNS("http://www.w3.org/2000/svg","svg");
    routeSvg.setAttribute("viewBox",`0 0 ${cw} ${ch}`);
    routeSvg.setAttribute("preserveAspectRatio","none");
    routeSvg.style.cssText="position:absolute;inset:0;width:100%;height:100%;z-index:5;pointer-events:none;overflow:visible;";
    stage.appendChild(routeSvg);

    const routeEl=(name,attrs={})=>{
      const el=document.createElementNS("http://www.w3.org/2000/svg",name);
      for(const [k,v] of Object.entries(attrs)){
        if(v!==undefined&&v!==null)el.setAttribute(k,String(v));
      }
      return el;
    };

    const drawDragOnlyRoutes=()=>{
      routeSvg.innerHTML="";
      for(const route of (Array.isArray(argsState.routes)?argsState.routes:[])){
        if(route.hidden)continue;
        const pts=Array.isArray(route.points)?route.points:[];
        if(pts.length<2)continue;
        const points=pts.map(p=>`${Number(p[0]||0)},${Number(p[1]||0)}`).join(" ");

        // White underlay keeps the existing clear separated connection style.
        routeSvg.appendChild(routeEl("polyline",{
          points,fill:"none",stroke:"#ffffff","stroke-width":"0.15",
          "stroke-linejoin":"round","stroke-linecap":"round"
        }));

        const line=routeEl("polyline",{
          points,fill:"none",stroke:String(route.color||"#1473E6"),
          "stroke-width":"0.052","stroke-linejoin":"round","stroke-linecap":"round"
        });
        if(route.dotted)line.setAttribute("stroke-dasharray","0.032 0.11");
        routeSvg.appendChild(line);
      }
    };
    drawDragOnlyRoutes();

    const pendingId=String(argsState.pending_connection_source_id||"");
    let activeDrag=null;
    let hoverId="";
    const overlays=new Map();
    const componentLabels=new Map();

    const toPercent=(v,total)=>`${(Number(v||0)/Math.max(1,total))*100}%`;

    const applyBox=(el,box)=>{
      const [x,y,w,h]=cloneBox(box);
      el.style.left=toPercent(x,cw);
      el.style.top=toPercent(y,ch);
      el.style.width=toPercent(w,cw);
      el.style.height=toPercent(h,ch);
    };

    const canvasPoint=(ev)=>{
      const r=stage.getBoundingClientRect();
      if(!r.width||!r.height)return[0,0];
      return[
        clamp((ev.clientX-r.left)/r.width*cw,0,cw),
        clamp((ev.clientY-r.top)/r.height*ch,0,ch)
      ];
    };

    const makeGhostFromPreview=(component)=>{
      const ghost=document.createElement("img");
      ghost.draggable=false;
      ghost.style.cssText="position:absolute;z-index:40;pointer-events:none;user-select:none;object-fit:contain;filter:drop-shadow(0 5px 8px rgba(0,0,0,.18));";
      applyBox(ghost,component.box);

      const directSrc=String(component.image_b64||"").trim();
      if(directSrc){
        ghost.src=`data:image/png;base64,${directSrc}`;
      }else{
        ghost.src=`data:image/png;base64,${argsState.image_b64||""}`;
        ghost.style.objectFit="fill";
      }
      return ghost;
    };

    const setHover=(id)=>{
      if(hoverId===id)return;
      hoverId=id;
      for(const [cid,item] of overlays.entries()){
        const show=cid===hoverId;
        item.add.style.opacity=show?"1":"0";
        item.add.style.pointerEvents=show?"auto":"none";
        item.del.style.opacity=show?"1":"0";
        item.del.style.pointerEvents=show?"auto":"none";
      }
    };

    for(const c of Object.values(components)){
      if(c.hidden)continue;
      const id=String(c.instance_id||"");
      if(!id)continue;

      // Actual visible component layer. This is deliberately separate from the
      // transparent pointer target so the component itself moves immediately.
      const visual=document.createElement("img");
      visual.draggable=false;
      visual.alt=String(c.title||c.component||id);
      visual.src=`data:image/png;base64,${String(c.image_b64||"").trim()}`;
      visual.style.cssText=`position:absolute;z-index:15;pointer-events:none;user-select:none;object-fit:${String(c.image_fit||"contain")};`;
      applyBox(visual,c.box);
      stage.appendChild(visual);

      // Component label: render as SVG text on the live Worksheet layer so it
      // remains visible below the component and cannot be clipped by HTML drag
      // targets. The label is non-interactive and follows the component on drag.
      const labelText=String(c.title||c.component||id);
      const [lx,ly,lw,lh]=cloneBox(c.box);
      const labelX=lx+(lw/2);
      const labelY=ly+lh+0.18;

      const labelUnder=routeEl("text",{
        x:labelX,
        y:labelY,
        "text-anchor":"middle",
        "dominant-baseline":"hanging",
        "font-size":"0.16",
        "font-family":"Arial, Segoe UI, sans-serif",
        "font-weight":"700",
        fill:"#ffffff",
        stroke:"#ffffff",
        "stroke-width":"0.055",
        "stroke-linejoin":"round",
        style:"pointer-events:none;user-select:none;"
      });
      labelUnder.textContent=labelText;
      routeSvg.appendChild(labelUnder);

      const labelMain=routeEl("text",{
        x:labelX,
        y:labelY,
        "text-anchor":"middle",
        "dominant-baseline":"hanging",
        "font-size":"0.16",
        "font-family":"Arial, Segoe UI, sans-serif",
        "font-weight":"700",
        fill:"#173f75",
        style:"pointer-events:none;user-select:none;"
      });
      labelMain.textContent=labelText;
      routeSvg.appendChild(labelMain);

      componentLabels.set(id,{under:labelUnder,main:labelMain});

      const hit=document.createElement("div");
      hit.dataset.componentId=id;
      hit.title=String(c.title||c.component||id);
      hit.style.cssText="position:absolute;z-index:50;box-sizing:border-box;cursor:grab;background:rgba(0,0,0,0.001);touch-action:none;pointer-events:auto;-webkit-user-select:none;user-select:none;";
      applyBox(hit,c.box);

      if(id===pendingId){
        hit.style.outline="3px solid #0a66e3";
        hit.style.outlineOffset="2px";
        hit.style.borderRadius="6px";
      }

      const add=document.createElement("button");
      add.type="button";
      add.textContent="+";
      add.title="Add another component";
      add.style.cssText="position:absolute;right:-13px;top:-13px;width:30px;height:30px;border-radius:50%;border:2px solid #fff;background:#0a66e3;color:#fff;font:bold 21px/24px Arial,sans-serif;box-shadow:0 2px 8px rgba(0,0,0,.25);z-index:30;opacity:0;pointer-events:none;cursor:pointer;padding:0;";

      const del=document.createElement("button");
      del.type="button";
      del.textContent="×";
      del.title="Delete component";
      del.style.cssText="position:absolute;left:-13px;top:-13px;width:30px;height:30px;border-radius:50%;border:2px solid #fff;background:#dc2626;color:#fff;font:bold 20px/24px Arial,sans-serif;box-shadow:0 2px 8px rgba(0,0,0,.25);z-index:30;opacity:0;pointer-events:none;cursor:pointer;padding:0;";

      add.addEventListener("pointerdown",e=>{e.preventDefault();e.stopPropagation();});
      del.addEventListener("pointerdown",e=>{e.preventDefault();e.stopPropagation();});
      add.addEventListener("click",e=>{
        e.preventDefault();e.stopPropagation();
        emit("component_add",{component:String(c.component||""),instance_id:id});
      });
      del.addEventListener("click",e=>{
        e.preventDefault();e.stopPropagation();
        emit("component_delete",{component:String(c.component||""),instance_id:id});
      });

      hit.addEventListener("pointerenter",()=>setHover(id));
      hit.addEventListener("pointerleave",()=>{
        if(!activeDrag)setHover("");
      });

      hit.addEventListener("pointerdown",e=>{
        if(e.button!==0&&e.pointerType!=="touch"&&e.pointerType!=="pen")return;
        if(e.target===add||e.target===del)return;

        e.preventDefault();
        e.stopPropagation();

        const start=canvasPoint(e);
        activeDrag={
          id,
          component:c,
          pointerId:e.pointerId,
          start,
          base:cloneBox(c.box),
          moved:false,
          ghost:makeGhostFromPreview(c)
        };
        stage.appendChild(activeDrag.ghost);
        hit.style.cursor="grabbing";
        hit.style.outline="2px dashed #0a66e3";
        hit.style.outlineOffset="2px";
        try{hit.setPointerCapture(e.pointerId);}catch(_){}
      });

      const moveActiveDrag=e=>{
        if(!activeDrag||activeDrag.id!==id||activeDrag.pointerId!==e.pointerId)return;
        e.preventDefault();
        e.stopPropagation();

        const p=canvasPoint(e);
        const [bx,by,bw,bh]=activeDrag.base;
        const dx=p[0]-activeDrag.start[0];
        const dy=p[1]-activeDrag.start[1];
        const nx=clamp(bx+dx,0,Math.max(0,cw-bw));
        const ny=clamp(by+dy,0,Math.max(0,ch-bh));

        c.box=[nx,ny,bw,bh];
        applyBox(hit,c.box);
        applyBox(visual,c.box);

        const labelPair=componentLabels.get(id);
        if(labelPair){
          const labelX=nx+(bw/2);
          const labelY=ny+bh+0.18;
          labelPair.under.setAttribute("x",String(labelX));
          labelPair.under.setAttribute("y",String(labelY));
          labelPair.main.setAttribute("x",String(labelX));
          labelPair.main.setAttribute("y",String(labelY));
        }

        applyBox(activeDrag.ghost,c.box);
        activeDrag.moved=activeDrag.moved||Math.hypot(nx-bx,ny-by)>.02;
      };

      hit.addEventListener("pointermove",moveActiveDrag);
      stage.addEventListener("pointermove",moveActiveDrag);

      let suppressComponentClick=false;
      const finish=e=>{
        if(!activeDrag||activeDrag.id!==id||activeDrag.pointerId!==e.pointerId)return;
        e.preventDefault();
        e.stopPropagation();

        const d=activeDrag;
        activeDrag=null;
        try{hit.releasePointerCapture(e.pointerId);}catch(_){}
        if(d.ghost&&d.ghost.parentNode)d.ghost.parentNode.removeChild(d.ghost);
        hit.style.cursor="grab";
        hit.style.outline=id===pendingId?"3px solid #0a66e3":"none";
        hit.style.outlineOffset=id===pendingId?"2px":"0";

        if(d.moved){
          suppressComponentClick=true;
          emit("component_move",{
            instance_id:id,
            component:String(c.component||""),
            box:cloneBox(c.box)
          });
        }else{
          // Selection is emitted by the normal click event below.
        }
      };

      hit.addEventListener("pointerup",finish);
      stage.addEventListener("pointerup",finish);
      hit.addEventListener("click",e=>{
        if(suppressComponentClick){suppressComponentClick=false;return;}
        e.preventDefault();
        e.stopPropagation();
        emit("component_select",{
          instance_id:id,
          component:String(c.component||"")
        });
      });
      hit.addEventListener("pointercancel",e=>{
        if(!activeDrag||activeDrag.id!==id||activeDrag.pointerId!==e.pointerId)return;
        const d=activeDrag;
        activeDrag=null;
        c.box=cloneBox(d.base);
        applyBox(hit,c.box);
        applyBox(visual,c.box);

        const labelPair=componentLabels.get(id);
        if(labelPair){
          const [rx,ry,rw,rh]=cloneBox(c.box);
          const labelX=rx+(rw/2);
          const labelY=ry+rh+0.18;
          labelPair.under.setAttribute("x",String(labelX));
          labelPair.under.setAttribute("y",String(labelY));
          labelPair.main.setAttribute("x",String(labelX));
          labelPair.main.setAttribute("y",String(labelY));
        }

        if(d.ghost&&d.ghost.parentNode)d.ghost.parentNode.removeChild(d.ghost);
        hit.style.cursor="grab";
      });

      hit.appendChild(add);
      hit.appendChild(del);
      stage.appendChild(hit);
      overlays.set(id,{hit,add,del,visual});
    }

    stage.addEventListener("pointerleave",()=>{
      if(!activeDrag)setHover("");
    });

    bg.addEventListener("load",()=>{
      if(argsState.fit_screen){
        lastHeight=fixedScreenHeight;
        post(SET_HEIGHT,{height:fixedScreenHeight});
      }else{
        requestAnimationFrame(()=>setHeight(true));
      }
    });

    if(argsState.fit_screen){
      lastHeight=fixedScreenHeight;
      post(SET_HEIGHT,{height:fixedScreenHeight});
    }else{
      requestAnimationFrame(()=>setHeight(true));
    }
  }

  function renderNormal(){
    root.innerHTML="";
    root.style.position="relative";
    const pendingId=String(argsState.pending_connection_source_id||"");
    const hotspotElements=new Map();

    const img=document.createElement("img");
    img.style.cssText="display:block;width:100%;height:auto";
    img.src=`data:image/png;base64,${argsState.image_b64||""}`;
    root.appendChild(img);

    const overlay=document.createElementNS("http://www.w3.org/2000/svg","svg");
    overlay.setAttribute("viewBox",`0 0 ${Number(argsState.canvas_width||1)} ${Number(argsState.canvas_height||1)}`);
    overlay.setAttribute("preserveAspectRatio","xMidYMid meet");
    overlay.style.cssText="position:absolute;inset:0;width:100%;height:100%;z-index:18;pointer-events:none;overflow:visible;";
    root.appendChild(overlay);

    img.addEventListener("load",()=>setHeight(true));

    const refreshSelection=()=>{
      for(const [id,el] of hotspotElements.entries()){
        if(id===pendingId){
          el.style.outline="3px solid #0a66e3";
          el.style.outlineOffset="2px";
          el.style.borderRadius="6px";
        }else{
          el.style.outline="none";
          el.style.outlineOffset="0";
        }
      }
    };

    const itemById=(id)=>(argsState.hotspots||[]).find(x=>String(x.instance_id||"")===String(id||""));
    const centerOf=(item)=>[
      Number(item.left||0)+Number(item.width||0)/2,
      Number(item.top||0)+Number(item.height||0)/2
    ];
    const drawImmediateConnection=(firstId,secondId)=>{
      const first=itemById(firstId), second=itemById(secondId);
      if(!first||!second)return;
      const [x1,y1]=centerOf(first), [x2,y2]=centerOf(second);
      const line=document.createElementNS("http://www.w3.org/2000/svg","polyline");
      const mx=(x1+x2)/2;
      line.setAttribute("points",`${x1},${y1} ${mx},${y1} ${mx},${y2} ${x2},${y2}`);
      line.setAttribute("fill","none");
      line.setAttribute("stroke","#1473E6");
      line.setAttribute("stroke-width","0.06");
      line.setAttribute("stroke-linecap","round");
      line.setAttribute("stroke-linejoin","round");
      line.setAttribute("vector-effect","non-scaling-stroke");
      overlay.appendChild(line);
    };

    const chooseComponent=(item,itemId)=>{
      if(!itemId)return;
      if(pendingId && pendingId!==itemId){
        drawImmediateConnection(pendingId,itemId);
      }
      emit("component_select",{instance_id:itemId,component:String(item.component||"")});
    };

    for(const item of (argsState.hotspots||[])){
      const hover=document.createElement("div");
      const itemId=String(item.instance_id||"");
      hover.style.cssText=`position:absolute;z-index:19;background:transparent;cursor:pointer;touch-action:manipulation;left:${100*Number(item.left||0)/Number(argsState.canvas_width||1)}%;top:${100*Number(item.top||0)/Number(argsState.canvas_height||1)}%;width:${100*Number(item.width||0)/Number(argsState.canvas_width||1)}%;height:${100*Number(item.height||0)/Number(argsState.canvas_height||1)}%;`;
      hotspotElements.set(itemId,hover);

      const b=document.createElement("button");
      b.type="button";
      b.title="Add another component";
      b.setAttribute("aria-label",`Add another ${String(item.title||item.component||"component")}`);
      b.textContent="+";
      b.style.cssText="position:absolute;z-index:20;opacity:0;pointer-events:none;display:flex;align-items:center;justify-content:center;border:2px solid #fff;border-radius:50%;background:#0a66e3;color:#fff;font:bold 20px/1 Arial,sans-serif;box-shadow:0 2px 8px rgba(0,0,0,.25);cursor:pointer;transition:opacity .12s ease;right:-8px;top:-8px;width:30px;height:30px;";

      const d=document.createElement("button");
      d.type="button";
      d.title="Delete this component";
      d.setAttribute("aria-label",`Delete ${String(item.title||item.component||"component")}`);
      d.textContent="×";
      d.style.cssText="position:absolute;z-index:20;opacity:0;pointer-events:none;display:flex;align-items:center;justify-content:center;border:2px solid #fff;border-radius:50%;background:#dc2626;color:#fff;font:bold 19px/1 Arial,sans-serif;box-shadow:0 2px 8px rgba(0,0,0,.25);cursor:pointer;transition:opacity .12s ease;left:-8px;top:-8px;width:30px;height:30px;";

      const show=()=>{
        b.style.opacity="1";
        b.style.pointerEvents="auto";
        d.style.opacity="1";
        d.style.pointerEvents="auto";
      };
      const hide=()=>{
        b.style.opacity="0";
        b.style.pointerEvents="none";
        d.style.opacity="0";
        d.style.pointerEvents="none";
      };
      hover.addEventListener("mouseenter",show);
      hover.addEventListener("mouseleave",hide);
      hover.addEventListener("focusin",show);
      hover.addEventListener("focusout",hide);
      hover.addEventListener("pointerenter",show);

      let lastPointerSelection=0;
      hover.addEventListener("pointerup",e=>{
        if(e.target===b||e.target===d)return;
        if(e.pointerType!=="touch"&&e.pointerType!=="pen")return;
        e.preventDefault();
        e.stopPropagation();
        lastPointerSelection=Date.now();
        chooseComponent(item,itemId);
      });
      hover.addEventListener("click",e=>{
        if(e.target===b||e.target===d)return;
        if(Date.now()-lastPointerSelection<500)return;
        e.preventDefault();
        e.stopPropagation();
        chooseComponent(item,itemId);
      });
      b.addEventListener("click",e=>{
        e.preventDefault();
        e.stopPropagation();
        emit("component_add",{component:String(item.component||""),instance_id:itemId});
      });
      d.addEventListener("click",e=>{
        e.preventDefault();
        e.stopPropagation();
        emit("component_delete",{component:String(item.component||""),instance_id:itemId});
      });
      hover.appendChild(b);
      hover.appendChild(d);
      root.appendChild(hover);
    }
    refreshSelection();
    setHeight(true);
  }

  function render(args){argsState=args||{};routes={};components={};selectedEdge=null;selectedComponents.clear();drag=null;zoom=1;panX=0;panY=0;const saved=(argsState.edit_mode&&argsState.editor_state&&Array.isArray(argsState.editor_state.routes)&&Array.isArray(argsState.editor_state.components))?argsState.editor_state:null;const rr=saved?saved.routes:(argsState.routes||[]),cc=saved?saved.components:(argsState.components||[]);rr.forEach(r=>{const id=String(r.edge_id||"");if(id)routes[id]={...r,edge_id:id,points:clonePoints(r.points),original_points:clonePoints(r.original_points||r.points),hidden:!!r.hidden};});cc.forEach(c=>{const id=String(c.instance_id||"");if(id)components[id]={...c,instance_id:id,box:cloneBox(c.box),hidden:!!c.hidden};});if(argsState.edit_mode){initialSnapshot=snapshot();history=[JSON.parse(JSON.stringify(initialSnapshot))];historyIndex=0;dirty=false;renderEditor();}else if(argsState.drag_only){renderDragOnly();}else renderNormal();}
  function keydown(e){if(["INPUT","TEXTAREA","SELECT"].includes(document.activeElement?.tagName))return;const cmd=e.ctrlKey||e.metaKey,k=String(e.key||"").toLowerCase();if(cmd&&k==="z"){e.preventDefault();e.shiftKey?redoLocal():undoLocal();return;}if(cmd&&k==="y"){e.preventDefault();redoLocal();return;}if(cmd&&k==="c"){e.preventDefault();copySelection();return;}if(cmd&&k==="v"){e.preventDefault();pasteSelection();return;}if(cmd&&k==="d"){e.preventDefault();duplicateIds([...selectedComponents]);return;}if(cmd&&k==="s"){e.preventDefault();saveEditor();return;}if(e.key==="Escape"){deselect();return;}if(e.key==="Delete"||e.key==="Backspace"){e.preventDefault();deleteSelection();return;}if(!cmd&&k==="d"&&selectedEdge){const r=routes[selectedEdge];r.direction=r.direction==="target_to_source"?"source_to_target":"target_to_source";checkpoint();renderOverlay();}}
  window.addEventListener("message",e=>{const d=e.data;if(d&&d.type===RENDER)render(d.args||{});});window.addEventListener("resize",()=>{if(!argsState.fit_screen)requestAnimationFrame(()=>setHeight(true));});window.addEventListener("pointerdown",e=>{if(contextMenu&&!contextMenu.contains(e.target))closeContext();});root.addEventListener("keydown",keydown);ready();setTimeout(ready,120);setHeight(true);setTimeout(()=>setHeight(true),250);
})();
