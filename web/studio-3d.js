import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

const state = {
  lid: "open",
  assembly: null,
  fileId: null,
  meshes: [],
  selected: null,
  rebuildTimer: null,
  rebuilding: false,
  rebuildGen: 0,
  pendingBody: null,
  wood: null,
  woodHi: null,
  woodGhost: null,
  ghostLid: null,
  ghostLidAnim: null,
  edgeGhost: null,
  handles: [],
  handleRoot: null,
  handleMat: null,
  handleMatHot: null,
  drag: null,
  dividerDrag: null,
  sx: null,
  sy: null,
  undo: [],
  flatLayouts: [],
  summary: null,
  attach: null,
};

const PANEL_DIMS = {
  bottom: "X + Y",
  top: "X + Y",
  lid: "X + Y",
  front: "X + H",
  back: "X + H",
  left: "Y + H",
  right: "Y + H",
};

const ROLE_FIELD = {
  bottom: null,
  top: null,
  lid: null,
  front: "box-x",
  back: "box-x",
  left: "box-y",
  right: "box-y",
};

function panelRole(partId) {
  const id = String(partId || "").toLowerCase();
  const leaf = id.split("/").pop() || id;
  if (PANEL_DIMS[leaf]) return leaf;
  for (const key of Object.keys(PANEL_DIMS)) {
    if (leaf.includes(key)) return key;
  }
  if (/divider-x/.test(leaf)) return "divider-x";
  if (/divider-y/.test(leaf)) return "divider-y";
  if (leaf.includes("divider")) return "divider";
  return "other";
}

function parseDividerMeta(partId) {
  const leaf = String(partId || "").toLowerCase().split("/").pop() || "";
  let m = leaf.match(/divider-x-(\d+)/);
  if (m) return { axis: "x", index: Number(m[1]) - 1 };
  m = leaf.match(/divider-y-(\d+)/);
  if (m) return { axis: "y", index: Number(m[1]) - 1 };
  return null;
}

function linkedDims(partId) {
  const role = panelRole(partId);
  if (role === "other") return "Temas yok — otomatik ölçek yok";
  return PANEL_DIMS[role] + " · kalınlık ortak";
}

const $ = (id) => document.getElementById(id);

function setStatus(text, kind) {
  const el = $("status");
  el.textContent = text || "";
  el.className = "status" + (kind ? " " + kind : "");
}

function setLoading(on, text) {
  const el = $("stage-loading");
  if (!el) return;
  el.classList.toggle("hide", !on);
  if (text) $("stage-loading-text").textContent = text;
  document.body.classList.toggle("is-rebuilding", !!on);
}

function clearGhostLid() {
  if (state.ghostLidAnim) {
    cancelAnimationFrame(state.ghostLidAnim);
    state.ghostLidAnim = null;
  }
  if (!state.ghostLid || !view.root) return;
  view.root.remove(state.ghostLid);
  state.ghostLid.traverse((obj) => {
    if (obj.geometry) obj.geometry.dispose();
  });
  state.ghostLid = null;
}

function assemblyAnchor() {
  // Prefer bottom panel world pose so ghost lid sits on the live box, not a guess origin.
  let bottom = null;
  for (const g of state.meshes || []) {
    if (g.userData && g.userData.role === "bottom") {
      bottom = g;
      break;
    }
  }
  if (bottom && bottom.userData.baseMatrix) {
    const pos = new THREE.Vector3().setFromMatrixPosition(bottom.userData.baseMatrix);
    return { x: pos.x, y: pos.y, z: pos.z };
  }
  return null;
}

function showOptimisticLid() {
  clearGhostLid();
  const lid = ($("box-lid") && $("box-lid").value) || "open";
  if (lid === "open") {
    // Open = hide any prior ghost immediately so the viewport feels responsive.
    return;
  }
  const x = Number($("box-x").value) || 100;
  const y = Number($("box-y").value) || 80;
  const h = Number($("box-h").value) || 40;
  const t = Number($("box-t").value) || 3;
  const mode = ($("box-dims") && $("box-dims").value) || "internal";
  const xi = mode === "external" ? Math.max(8, x - 2 * t) : x;
  const yi = mode === "external" ? Math.max(8, y - 2 * t) : y;
  const hi = mode === "external" ? Math.max(8, h - t) : h;
  if (!state.woodGhost) {
    state.woodGhost = new THREE.MeshStandardMaterial({
      color: 0x2f6fed,
      transparent: true,
      opacity: 0.55,
      roughness: 0.65,
      metalness: 0.08,
      depthWrite: false,
    });
  }
  if (!state.edgeGhost) {
    state.edgeGhost = new THREE.LineBasicMaterial({ color: 0x9ec1ff, transparent: true, opacity: 0.9 });
  }
  const doors = lid === "double_door" ? 2 : 1;
  const group = new THREE.Group();
  group.userData.ghost = true;
  group.userData.lidType = lid;

  function addPlate(w, d, cx, cy, cz) {
    const holder = new THREE.Group();
    holder.position.set(cx, cy, cz);
    holder.userData.base = { x: cx, y: cy, z: cz, w, d };
    const geom = new THREE.BoxGeometry(w, d, t);
    const mesh = new THREE.Mesh(geom, state.woodGhost);
    const edges = new THREE.LineSegments(new THREE.EdgesGeometry(geom), state.edgeGhost);
    holder.add(mesh);
    holder.add(edges);
    group.add(holder);
    return holder;
  }

  const zClosed = hi + t / 2;
  const plates = [];
  if (doors === 1) {
    plates.push(addPlate(xi, yi, xi / 2, yi / 2, zClosed));
  } else {
    const half = Math.max(8, (xi - t) / 2);
    plates.push(addPlate(half, yi, half / 2, yi / 2, zClosed));
    plates.push(addPlate(half, yi, half + t + half / 2, yi / 2, zClosed));
  }

  const anchor = assemblyAnchor();
  if (anchor) {
    group.position.set(anchor.x, anchor.y, anchor.z);
  } else {
    group.position.set(-xi / 2, -yi / 2, 0);
  }
  view.root.add(group);
  state.ghostLid = group;
  rebuildResizeHandles();

  // Per-type motion so lid change is readable before the SVG rebuild returns.
  const start = performance.now();
  const duration = 420;
  const tick = (now) => {
    if (!state.ghostLid) return;
    const u = Math.min(1, (now - start) / duration);
    const e = 1 - Math.pow(1 - u, 3);
    plates.forEach((holder) => {
      const b = holder.userData.base;
      holder.rotation.set(0, 0, 0);
      holder.position.set(b.x, b.y, b.z);
      if (lid === "hinged" || lid === "double_door") {
        const angle = -e * (Math.PI / 2.4);
        // Pivot around back edge (local +Y)
        holder.position.set(b.x, yi, zClosed);
        holder.rotation.x = angle;
        const child = holder.children[0];
        if (child) child.position.set(0, b.y - yi, 0);
        holder.children.forEach((c) => {
          if (c !== child) c.position.set(0, b.y - yi, 0);
        });
      } else if (lid === "sliding") {
        holder.position.set(b.x, b.y + e * (yi * 0.55), b.z + e * (t * 0.4));
      } else if (lid === "removable") {
        holder.position.set(b.x, b.y, b.z + e * (t * 4 + 8));
      } else {
        holder.position.set(b.x, b.y, b.z + e * (t * 1.6));
      }
    });
    if (u < 1) state.ghostLidAnim = requestAnimationFrame(tick);
    else state.ghostLidAnim = null;
  };
  state.ghostLidAnim = requestAnimationFrame(tick);
}

async function api(url, opts) {
  const res = await fetch(url, {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...(opts && opts.headers) },
    ...opts,
  });
  const data = await res.json().catch(() => ({}));
  return { res, data };
}

function shapeFromOutline(points, holes) {
  if (!points || points.length < 3) return null;
  const shape = new THREE.Shape();
  shape.moveTo(points[0][0], points[0][1]);
  for (let i = 1; i < points.length; i++) shape.lineTo(points[i][0], points[i][1]);
  shape.closePath();
  (holes || []).forEach((hole) => {
    const pts = hole.points || [];
    if (pts.length < 3) return;
    const path = new THREE.Path();
    path.moveTo(pts[0][0], pts[0][1]);
    for (let i = 1; i < pts.length; i++) path.lineTo(pts[i][0], pts[i][1]);
    path.closePath();
    shape.holes.push(path);
  });
  return shape;
}

function matrixFromRow(transform) {
  const m = (transform && transform.matrix) || null;
  if (!m || m.length !== 4) return new THREE.Matrix4();
  return new THREE.Matrix4().set(
    m[0][0], m[0][1], m[0][2], m[0][3],
    m[1][0], m[1][1], m[1][2], m[1][3],
    m[2][0], m[2][1], m[2][2], m[2][3],
    0, 0, 0, 1
  );
}

function centroidLocal(points) {
  let x = 0;
  let y = 0;
  const n = points.length || 1;
  points.forEach((p) => {
    x += p[0];
    y += p[1];
  });
  return [x / n, y / n];
}

let view = {};

function buildScene() {
  const canvas = $("viewport");
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 5000);
  camera.position.set(220, 180, 260);
  const controls = new OrbitControls(camera, canvas);
  controls.enableDamping = true;
  const root = new THREE.Group();
  scene.add(root);
  scene.add(new THREE.AmbientLight(0xffffff, 0.55));
  const key = new THREE.DirectionalLight(0xfff0dd, 0.9);
  key.position.set(120, 220, 160);
  scene.add(key);
  const fill = new THREE.DirectionalLight(0x9bb7ff, 0.35);
  fill.position.set(-140, 80, -90);
  scene.add(fill);
  state.wood = new THREE.MeshStandardMaterial({ color: 0xc4a574, roughness: 0.85, metalness: 0.05 });
  state.woodHi = new THREE.MeshStandardMaterial({ color: 0xe0c08a, roughness: 0.7, metalness: 0.08 });
  state.woodGhost = new THREE.MeshStandardMaterial({
    color: 0x3d8bfd, transparent: true, opacity: 0.45, roughness: 0.7, metalness: 0.05, depthWrite: false,
  });
  view = { renderer, scene, camera, controls, root, canvas };

  function resize() {
    const w = canvas.clientWidth || canvas.parentElement.clientWidth;
    const h = canvas.clientHeight || canvas.parentElement.clientHeight;
    renderer.setSize(w, h, false);
    camera.aspect = w / Math.max(h, 1);
    camera.updateProjectionMatrix();
  }
  resize();
  window.addEventListener("resize", resize);

  const ray = new THREE.Raycaster();
  const mouse = new THREE.Vector2();
  const dragPlane = new THREE.Plane();
  const hitPoint = new THREE.Vector3();

  function pointerNDC(ev) {
    const rect = canvas.getBoundingClientRect();
    mouse.x = ((ev.clientX - rect.left) / rect.width) * 2 - 1;
    mouse.y = -((ev.clientY - rect.top) / rect.height) * 2 + 1;
  }

  canvas.addEventListener("pointerdown", (ev) => {
    if (ev.button !== 0) return;
    pointerNDC(ev);
    ray.setFromCamera(mouse, camera);

    // Resize handles first (lid sides)
    const handleHits = state.handleRoot
      ? ray.intersectObjects(state.handles, true)
      : [];
    if (handleHits.length) {
      let h = handleHits[0].object;
      while (h && !h.userData.resize) h = h.parent;
      if (h && h.userData.resize) {
        ev.preventDefault();
        canvas.setPointerCapture(ev.pointerId);
        const field = h.userData.field;
        const axis = h.userData.axis;
        const startVal = Number($(field).value) || 100;
        const pivot = handleHits[0].point.clone();
        if (axis === "z") {
          const n = new THREE.Vector3(
            camera.position.x - pivot.x,
            camera.position.y - pivot.y,
            0
          );
          if (n.lengthSq() < 1e-6) n.set(1, 0, 0);
          else n.normalize();
          dragPlane.setFromNormalAndCoplanarPoint(n, pivot);
        } else {
          dragPlane.setFromNormalAndCoplanarPoint(new THREE.Vector3(0, 0, 1), pivot);
        }
        ray.ray.intersectPlane(dragPlane, hitPoint);
        state.drag = {
          field,
          axis,
          sign: h.userData.sign,
          startVal,
          startPoint: hitPoint.clone(),
          handle: h,
        };
        controls.enabled = false;
        canvas.style.cursor = "grabbing";
        if (state.handleMatHot) h.traverse((o) => {
          if (o.isMesh) o.material = state.handleMatHot;
        });
        setStatus("Tut-çek: " + field.replace("box-", "").toUpperCase() + " · bırakınca paneller yenilenir", "ok");
        return;
      }
    }

    const hits = ray.intersectObjects(state.meshes, true);
    if (!hits.length) {
      selectPanel(null);
      hideDimPop();
      return;
    }
    let obj = hits[0].object;
    while (obj && !obj.userData.partId) obj = obj.parent;
    if (obj && obj.userData.divider) {
      ev.preventDefault();
      canvas.setPointerCapture(ev.pointerId);
      const div = obj.userData.divider;
      const fp = boxFootprintMm();
      const positions = (div.axis === "x"
        ? (state.summary && state.summary.divider_x_pos) || []
        : (state.summary && state.summary.divider_y_pos) || []).map(Number);
      dragPlane.setFromNormalAndCoplanarPoint(new THREE.Vector3(0, 0, 1), hits[0].point.clone());
      ray.ray.intersectPlane(dragPlane, hitPoint);
      state.dividerDrag = {
        group: obj,
        axis: div.axis,
        index: div.index,
        positions: positions.slice(),
        startPos: positions[div.index],
        startPoint: hitPoint.clone(),
        span: div.axis === "x" ? fp.xi : fp.yi,
        thickness: fp.t,
      };
      controls.enabled = false;
      canvas.style.cursor = "grabbing";
      selectPanel(obj);
      hideDimPop();
      setStatus("Bölücüyü kaydır · hücre ≥ 8 mm · bırakınca yenilenir", "ok");
      return;
    }
    if (obj) {
      selectPanel(obj);
      openDimPop(obj, ev.clientX, ev.clientY);
    }
  });

  canvas.addEventListener("pointermove", (ev) => {
    pointerNDC(ev);
    ray.setFromCamera(mouse, camera);
    if (state.drag) {
      if (!ray.ray.intersectPlane(dragPlane, hitPoint)) return;
      const d = state.drag;
      let deltaWorld = 0;
      if (d.axis === "x") deltaWorld = hitPoint.x - d.startPoint.x;
      else if (d.axis === "y") deltaWorld = hitPoint.y - d.startPoint.y;
      else deltaWorld = hitPoint.z - d.startPoint.z;
      const lo = d.field === "box-h" ? 10 : 20;
      const next = Math.round(Math.max(lo, Math.min(800, d.startVal + deltaWorld * d.sign)));
      if (Number($(d.field).value) === next) return;
      $(d.field).value = String(next);
      applyLiveResizePreview(d.field, d.startVal, next);
      $("sum-dims").textContent = d.field.replace("box-", "").toUpperCase() + " → " + next + " mm";
      return;
    }
    if (state.dividerDrag) {
      if (!ray.ray.intersectPlane(dragPlane, hitPoint)) return;
      const d = state.dividerDrag;
      const delta = d.axis === "x"
        ? (hitPoint.x - d.startPoint.x)
        : (hitPoint.y - d.startPoint.y);
      const t = d.thickness;
      const minP = t / 2 + 8;
      const maxP = d.span - t / 2 - 8;
      let next = Math.round((d.startPos + delta) * 10) / 10;
      next = Math.max(minP, Math.min(maxP, next));
      // Keep clear of neighboring dividers
      const prev = d.index > 0 ? d.positions[d.index - 1] : null;
      const nxt = d.index < d.positions.length - 1 ? d.positions[d.index + 1] : null;
      if (prev != null) next = Math.max(next, prev + t + 8);
      if (nxt != null) next = Math.min(next, nxt - t - 8);
      d.positions[d.index] = next;
      // Live translate divider mesh along axis from seated pose
      if (d.group && d.group.userData.baseMatrix) {
        const m = d.group.userData.baseMatrix.clone();
        const shift = new THREE.Vector3(
          d.axis === "x" ? (next - d.startPos) : 0,
          d.axis === "y" ? (next - d.startPos) : 0,
          0
        );
        m.setPosition(new THREE.Vector3().setFromMatrixPosition(m).add(shift));
        d.group.matrix.copy(m);
        d.group.matrixWorldNeedsUpdate = true;
      }
      $("sum-dims").textContent = "bölücü " + d.axis.toUpperCase() + (d.index + 1) + " → " + next + " mm";
      return;
    }
    // Hover cursor on handles / dividers
    const handleHits = state.handleRoot
      ? ray.intersectObjects(state.handles, true)
      : [];
    if (handleHits.length) {
      let h = handleHits[0].object;
      while (h && !h.userData.resize) h = h.parent;
      canvas.style.cursor = (h && h.userData.axis === "y") ? "ns-resize"
        : (h && h.userData.axis === "z") ? "ns-resize"
          : "ew-resize";
      return;
    }
    const meshHits = ray.intersectObjects(state.meshes, true);
    if (meshHits.length) {
      let o = meshHits[0].object;
      while (o && !o.userData.partId) o = o.parent;
      canvas.style.cursor = (o && o.userData.divider) ? "grab" : "";
    } else {
      canvas.style.cursor = "";
    }
  });

  function endDrag(ev) {
    if (state.dividerDrag) {
      const d = state.dividerDrag;
      state.dividerDrag = null;
      controls.enabled = true;
      canvas.style.cursor = "";
      try { canvas.releasePointerCapture(ev.pointerId); } catch (_) { /* ignore */ }
      if (d.axis === "x") {
        state.sx = null; // send positions instead
        state.dividerXPos = d.positions.slice();
      } else {
        state.sy = null;
        state.dividerYPos = d.positions.slice();
      }
      pushUndo();
      scheduleRebuild(true);
      return;
    }
    if (!state.drag) return;
    const d = state.drag;
    if (d.handle && state.handleMat) {
      d.handle.traverse((o) => {
        if (o.isMesh) o.material = state.handleMat;
      });
    }
    state.drag = null;
    controls.enabled = true;
    canvas.style.cursor = "";
    try { canvas.releasePointerCapture(ev.pointerId); } catch (_) { /* ignore */ }
    pushUndo();
    scheduleRebuild(true);
  }
  canvas.addEventListener("pointerup", endDrag);
  canvas.addEventListener("pointercancel", endDrag);

  function frame() {
    controls.update();
    renderer.render(scene, camera);
    requestAnimationFrame(frame);
  }
  frame();
}

function clearResizeHandles() {
  if (!state.handleRoot || !view.root) {
    state.handles = [];
    return;
  }
  view.root.remove(state.handleRoot);
  state.handleRoot.traverse((obj) => {
    if (obj.geometry) obj.geometry.dispose();
  });
  state.handleRoot = null;
  state.handles = [];
}

function boxFootprintMm() {
  const x = Number($("box-x").value) || 100;
  const y = Number($("box-y").value) || 80;
  const h = Number($("box-h").value) || 40;
  const t = Number($("box-t").value) || 3;
  const mode = ($("box-dims") && $("box-dims").value) || "internal";
  const xi = mode === "external" ? Math.max(8, x - 2 * t) : x;
  const yi = mode === "external" ? Math.max(8, y - 2 * t) : y;
  const hi = mode === "external" ? Math.max(8, h - t) : h;
  return { xi, yi, hi, t, x, y, h };
}

function rebuildResizeHandles() {
  clearResizeHandles();
  if (!view.root) return;
  const lid = ($("box-lid") && $("box-lid").value) || "open";
  // Handles sit on lid plane; if open, on the top rim so sides are still grabable.
  const { xi, yi, hi, t } = boxFootprintMm();
  if (!state.handleMat) {
    state.handleMat = new THREE.MeshStandardMaterial({
      color: 0x4ea1ff,
      emissive: 0x12385c,
      roughness: 0.45,
      metalness: 0.2,
    });
  }
  if (!state.handleMatHot) {
    state.handleMatHot = new THREE.MeshStandardMaterial({
      color: 0xffc857,
      emissive: 0x5a3a00,
      roughness: 0.4,
      metalness: 0.15,
    });
  }
  const root = new THREE.Group();
  root.userData.handles = true;
  const z = hi + t + 1.5;
  const grip = Math.max(6, Math.min(14, Math.min(xi, yi) * 0.08));
  const stick = Math.max(10, Math.min(22, Math.min(xi, yi) * 0.12));
  const specs = [
    { field: "box-x", axis: "x", sign: 1, pos: [xi + stick / 2, yi / 2, z], size: [stick, grip, grip], cursor: "ew-resize" },
    { field: "box-x", axis: "x", sign: -1, pos: [-stick / 2, yi / 2, z], size: [stick, grip, grip], cursor: "ew-resize" },
    { field: "box-y", axis: "y", sign: 1, pos: [xi / 2, yi + stick / 2, z], size: [grip, stick, grip], cursor: "ns-resize" },
    { field: "box-y", axis: "y", sign: -1, pos: [xi / 2, -stick / 2, z], size: [grip, stick, grip], cursor: "ns-resize" },
  ];
  // Height grips on lid front/back corners when a lid exists (grow H)
  if (lid !== "open") {
    specs.push(
      { field: "box-h", axis: "z", sign: 1, pos: [xi / 2, yi / 2, z + stick / 2], size: [grip, grip, stick], cursor: "ns-resize", plane: "z" }
    );
  }
  specs.forEach((s) => {
    const geom = new THREE.BoxGeometry(s.size[0], s.size[1], s.size[2]);
    const mesh = new THREE.Mesh(geom, state.handleMat);
    mesh.position.set(s.pos[0], s.pos[1], s.pos[2]);
    mesh.userData.resize = true;
    mesh.userData.field = s.field;
    mesh.userData.axis = s.axis;
    mesh.userData.sign = s.sign;
    mesh.userData.plane = s.plane || "xy";
    // Soft edge
    const edges = new THREE.LineSegments(
      new THREE.EdgesGeometry(geom),
      new THREE.LineBasicMaterial({ color: 0xd7ebff })
    );
    mesh.add(edges);
    root.add(mesh);
    state.handles.push(mesh);
  });
  const anchor = assemblyAnchor();
  if (anchor) root.position.set(anchor.x, anchor.y, anchor.z);
  else root.position.set(-xi / 2, -yi / 2, 0);
  view.root.add(root);
  state.handleRoot = root;
}

function applyLiveResizePreview(field, fromVal, toVal) {
  if (!fromVal || !toVal || fromVal === toVal) return;
  const sx = field === "box-x" ? toVal / fromVal : 1;
  const sy = field === "box-y" ? toVal / fromVal : 1;
  const sz = field === "box-h" ? toVal / fromVal : 1;
  // Scale seated assembly around box origin for instant feedback
  state.meshes.forEach((group) => {
    if (!group.userData.baseMatrix) return;
    const m = group.userData.baseMatrix.clone();
    const scale = new THREE.Matrix4().makeScale(sx, sy, sz);
    // Prefer anchoring at current handle-root origin
    const origin = state.handleRoot
      ? state.handleRoot.position.clone()
      : new THREE.Vector3();
    const toLocal = new THREE.Matrix4().makeTranslation(-origin.x, -origin.y, -origin.z);
    const toWorld = new THREE.Matrix4().makeTranslation(origin.x, origin.y, origin.z);
    group.matrix.copy(toWorld.clone().multiply(scale).multiply(toLocal).multiply(m));
    group.matrixWorldNeedsUpdate = true;
  });
  if (state.handleRoot) {
    const { xi, yi, hi, t } = boxFootprintMm();
    // Reposition grips to match live numbers without full rebuild
    const z = hi + t + 1.5;
    const stick = Math.max(10, Math.min(22, Math.min(xi, yi) * 0.12));
    const grip = Math.max(6, Math.min(14, Math.min(xi, yi) * 0.08));
    state.handles.forEach((mesh) => {
      const f = mesh.userData.field;
      const sign = mesh.userData.sign;
      if (f === "box-x") mesh.position.set(sign > 0 ? xi + stick / 2 : -stick / 2, yi / 2, z);
      else if (f === "box-y") mesh.position.set(xi / 2, sign > 0 ? yi + stick / 2 : -stick / 2, z);
      else if (f === "box-h") mesh.position.set(xi / 2, yi / 2, z + stick / 2);
      if (f === "box-x") mesh.scale.set(1, grip / Math.max(mesh.geometry.parameters.height, 1), grip / Math.max(mesh.geometry.parameters.depth, 1));
    });
  }
}

function clearMeshes() {
  clearResizeHandles();
  state.meshes.forEach((g) => {
    view.root.remove(g);
    g.traverse((obj) => {
      if (obj.geometry) obj.geometry.dispose();
    });
  });
  state.meshes = [];
  state.flatLayouts = [];
}

function selectPanel(group) {
  state.selected = group;
  state.meshes.forEach((g) => {
    g.traverse((obj) => {
      if (obj.isMesh && obj.material && obj.material.isMeshStandardMaterial) {
        obj.material = state.selected === g ? state.woodHi : state.wood;
      }
    });
  });
  if (!group) {
    $("sum-sel").textContent = "—";
    $("sum-dims").textContent = "—";
    return;
  }
  const id = group.userData.partId;
  $("sum-sel").textContent = id;
  $("sum-dims").textContent = linkedDims(id);
  setStatus("Seçili: " + id + " · " + linkedDims(id), "ok");
}

function hideDimPop() {
  $("dim-pop").classList.add("hide");
}

function openDimPop(group, _x, _y) {
  const role = panelRole(group.userData.partId);
  const field =
    role === "front" || role === "back" ? "box-x"
      : role === "left" || role === "right" ? "box-y"
        : role === "bottom" || role === "lid" || role === "top" ? "box-x"
          : null;
  if (!field) {
    hideDimPop();
    return;
  }
  $("dim-pop").classList.remove("hide");
  $("dim-pop-label").textContent = group.userData.partId + " · " + linkedDims(group.userData.partId);
  $("dim-pop-val").value = $(field).value;
  $("dim-pop").dataset.field = field;
  if (role === "bottom" || role === "lid" || role === "top") {
    $("dim-pop").dataset.field2 = "box-y";
  } else if (role === "front" || role === "back") {
    $("dim-pop").dataset.field2 = "box-h";
  } else if (role === "left" || role === "right") {
    $("dim-pop").dataset.field2 = "box-h";
  } else {
    delete $("dim-pop").dataset.field2;
  }
}

function paintSummary(summary) {
  state.summary = summary || null;
  if (summary) {
    if (Array.isArray(summary.sx)) state.sx = summary.sx.slice();
    if (Array.isArray(summary.sy)) state.sy = summary.sy.slice();
    if (Array.isArray(summary.divider_x_pos)) state.dividerXPos = summary.divider_x_pos.slice();
    if (Array.isArray(summary.divider_y_pos)) state.dividerYPos = summary.divider_y_pos.slice();
  }
  if (!summary) {
    $("sum-inner").textContent = "—";
    $("sum-outer").textContent = "—";
    $("sum-vol").textContent = "—";
    return;
  }
  $("sum-inner").textContent =
    summary.x_inner_mm + " × " + summary.y_inner_mm + " × " + summary.h_inner_mm;
  $("sum-outer").textContent =
    summary.x_outer_mm + " × " + summary.y_outer_mm + " × " + summary.h_outer_mm;
  $("sum-vol").textContent = (summary.volume_l != null ? summary.volume_l + " L" : "—");
}

function loadAssembly(assembly) {
  clearGhostLid();
  clearMeshes();
  state.assembly = assembly;
  state.selected = null;
  hideDimPop();
  if (!assembly || !assembly.success || !(assembly.panels || []).length) {
    setStatus((assembly && (assembly.look_again || []).join(" ")) || "Montaj verisi yok.", "bad");
    return;
  }
  const thickness = Number(assembly.thickness_mm || 3);
  const edgeMat = new THREE.LineBasicMaterial({ color: 0x5a4030 });
  const panels = assembly.panels || [];
  let cursorX = 0;
  const gap = 6;
  panels.forEach((panel, index) => {
    const shape = shapeFromOutline(panel.outline_local_mm, panel.inner_cuts);
    if (!shape) return;
    const geom = new THREE.ExtrudeGeometry(shape, {
      depth: thickness,
      bevelEnabled: false,
    });
    const group = new THREE.Group();
    const mesh = new THREE.Mesh(geom, state.wood);
    const edges = new THREE.LineSegments(new THREE.EdgesGeometry(geom), edgeMat);
    group.add(mesh);
    group.add(edges);
    const matrix = matrixFromRow(panel.transform);
    group.matrixAutoUpdate = false;
    group.matrix.copy(matrix);
    group.matrixWorldNeedsUpdate = true;
    group.userData.partId = panel.part_id;
    group.userData.role = panelRole(panel.part_id);
    group.userData.baseMatrix = matrix.clone();
    const divMeta = parseDividerMeta(panel.part_id);
    if (divMeta) group.userData.divider = divMeta;

    const seated = new THREE.Vector3().setFromMatrixPosition(matrix);
    const [cx, cy] = centroidLocal(panel.outline_local_mm || [[0, 0]]);
    const local = new THREE.Vector3(cx, cy, thickness / 2).applyMatrix4(matrix);
    const outward = local.clone().sub(new THREE.Vector3(60, 30, 40));
    if (outward.lengthSq() < 1e-6) outward.set(0, 1, 0);
    else outward.normalize();
    const explodeAt = seated.clone().add(outward.multiplyScalar(28 + index * 4));

    // Flat nesting pose: lay on XY floor in a row (assembly scrubber → 100%)
    const xs = (panel.outline_local_mm || []).map((p) => p[0]);
    const ys = (panel.outline_local_mm || []).map((p) => p[1]);
    const w = Math.max(...xs) - Math.min(...xs);
    const d = Math.max(...ys) - Math.min(...ys);
    const flat = new THREE.Matrix4().makeRotationX(-Math.PI / 2);
    flat.setPosition(cursorX + w / 2, 0, d / 2);
    cursorX += w + gap;
    group.userData.seated = seated;
    group.userData.exploded = explodeAt;
    group.userData.flatMatrix = flat;
    view.root.add(group);
    state.meshes.push(group);
  });
  applyExplode(Number($("explode").value || 0) / 100);
  rebuildResizeHandles();
  fitCamera();
  setStatus("Mavi tutamaç / bölücü tut-çek · panele tıkla = ölçü.", "ok");
  $("sum-panels").textContent = String(panels.length);
  $("sum-t").textContent = thickness + " mm";
  $("sum-val").textContent = assembly.validation_state || "—";
  $("sum-sel").textContent = "—";
  $("sum-dims").textContent = "—";
  $("sum-note").textContent = assembly.note || "Kapak kenarı = boyut · bölücü = kaydır.";
  if ($("box-t") && thickness) $("box-t").value = String(thickness);
  if ($("stl-h") && thickness) $("stl-h").value = String(thickness);
  paintNestStats();
}

function paintNestStats() {
  const el = $("nest-stats");
  if (!el) return;
  const gap = Number(($("nest-gap") && $("nest-gap").value) || 6);
  const panels = (state.assembly && state.assembly.panels) || [];
  if (!panels.length) {
    el.textContent = "Önce bir kutu üret. Nest özeti burada görünür.";
    return;
  }
  let cursor = 0;
  let maxD = 0;
  let area = 0;
  panels.forEach((panel) => {
    const xs = (panel.outline_local_mm || []).map((p) => p[0]);
    const ys = (panel.outline_local_mm || []).map((p) => p[1]);
    if (!xs.length) return;
    const w = Math.max(...xs) - Math.min(...xs);
    const d = Math.max(...ys) - Math.min(...ys);
    cursor += w + gap;
    maxD = Math.max(maxD, d);
    area += w * d;
  });
  const sheetW = Math.max(0, cursor - gap);
  const t = Number((state.assembly && state.assembly.thickness_mm) || ($("box-t") && $("box-t").value) || 3);
  el.textContent =
    panels.length + " panel · nest ≈ " +
    Math.round(sheetW) + " × " + Math.round(maxD) + " mm · " +
    "boşluk " + gap + " mm · alan ≈ " + Math.round(area) + " mm² · t=" + t + " mm";
}

function applyExplode(t) {
  // 0–0.85 assembled→exploded; 0.85–1.0 explode→flat nesting layout
  state.meshes.forEach((group) => {
    if (!group.userData.baseMatrix || !group.userData.seated) return;
    if (t <= 0.85) {
      const u = t / 0.85;
      const p = group.userData.seated.clone().lerp(group.userData.exploded, u);
      const delta = p.clone().sub(group.userData.seated);
      const m = group.userData.baseMatrix.clone();
      m.setPosition(new THREE.Vector3().setFromMatrixPosition(m).add(delta));
      group.matrix.copy(m);
    } else {
      const u = (t - 0.85) / 0.15;
      const from = new THREE.Matrix4();
      {
        const p = group.userData.exploded.clone();
        const delta = p.clone().sub(group.userData.seated);
        from.copy(group.userData.baseMatrix);
        from.setPosition(new THREE.Vector3().setFromMatrixPosition(from).add(delta));
      }
      const to = group.userData.flatMatrix || from;
      const a = new THREE.Vector3().setFromMatrixPosition(from);
      const b = new THREE.Vector3().setFromMatrixPosition(to);
      const qa = new THREE.Quaternion().setFromRotationMatrix(from);
      const qb = new THREE.Quaternion().setFromRotationMatrix(to);
      const q = qa.slerp(qb, u);
      const p = a.lerp(b, u);
      const m = new THREE.Matrix4().compose(p, q, new THREE.Vector3(1, 1, 1));
      group.matrix.copy(m);
    }
    group.matrixWorldNeedsUpdate = true;
  });
  if (t > 0.84) $("explode-lab").textContent = Math.round(t * 100) + "% düz";
}

function fitCamera() {
  const box = new THREE.Box3().setFromObject(view.root);
  if (box.isEmpty()) return;
  const size = box.getSize(new THREE.Vector3());
  const center = box.getCenter(new THREE.Vector3());
  const maxDim = Math.max(size.x, size.y, size.z, 40);
  view.controls.target.copy(center);
  view.camera.position.set(center.x + maxDim * 1.2, center.y + maxDim * 0.9, center.z + maxDim * 1.3);
  view.controls.update();
}

function paintJoints(data) {
  const el = $("sum-joints");
  if (!el) return;
  const joints = data.joints || (data.summary && data.summary.joints) || null;
  if (!joints) {
    el.textContent = "—";
    return;
  }
  const bits = [
    joints.status || "?",
    "finger " + (joints.finger_mm != null ? joints.finger_mm + " mm" : "?"),
    joints.style || "",
    "kerf " + (joints.kerf_status || "?"),
  ].filter(Boolean);
  el.textContent = bits.join(" · ");
  if (joints.physical_fit) {
    $("sum-note").textContent =
      (joints.warnings && joints.warnings[0]) ||
      ("Finger/kerf dijital: " + joints.status + ". Fiziksel fit " + joints.physical_fit + ".");
  }
}

function paintExports(data) {
  const fileId = data.file_id || (data.assembly && data.assembly.file_id);
  state.fileId = fileId;
  $("sum-file").textContent = fileId || "—";
  paintJoints(data);
  const svg = $("dl-svg");
  const dxf = $("dl-dxf");
  const edit = $("open-edit");
  if (fileId) {
    svg.href = data.svg_url || ("/files/" + encodeURIComponent(fileId));
    svg.classList.remove("hide");
    edit.href = "/out/" + encodeURIComponent(fileId);
    edit.classList.remove("hide");
  } else {
    svg.classList.add("hide");
    edit.classList.add("hide");
  }
  if (data.dxf_url || data.dxf_id) {
    dxf.href = data.dxf_url || ("/files/" + encodeURIComponent(data.dxf_id));
    dxf.classList.remove("hide");
  } else {
    dxf.classList.add("hide");
  }
  if (data.stl_url || data.stl_id) {
    const stl = $("dl-stl");
    stl.href = data.stl_url || ("/files/" + encodeURIComponent(data.stl_id));
    stl.classList.remove("hide");
  }
  const plan = data.plan || {};
  $("sum-plan").textContent = plan.plan_name || plan.plan || "—";
  if (plan.quota != null) $("sum-quota").textContent = (plan.used || 0) + " / " + plan.quota;
  paintSummary(data.summary);
}

function snapshotForm() {
  return {
    unit: $("box-unit").value,
    dimension_mode: $("box-dims").value,
    lid: $("box-lid").value,
    x: $("box-x").value,
    y: $("box-y").value,
    h: $("box-h").value,
    thickness: $("box-t").value,
    finger: $("box-finger").value,
    burn: $("box-burn").value,
    press_fit: $("box-bumps").checked,
    dividers_x: $("box-dx").value,
    dividers_y: $("box-dy").value,
    bottom_lift: $("box-lift").value,
  };
}

function restoreForm(snap) {
  if (!snap) return;
  $("box-unit").value = snap.unit || "mm";
  $("box-dims").value = snap.dimension_mode || "internal";
  $("box-lid").value = snap.lid || "open";
  $("box-x").value = snap.x;
  $("box-y").value = snap.y;
  $("box-h").value = snap.h;
  $("box-t").value = snap.thickness;
  $("box-finger").value = snap.finger;
  $("box-burn").value = snap.burn || "";
  $("box-bumps").checked = !!snap.press_fit;
  $("box-dx").value = snap.dividers_x || 0;
  $("box-dy").value = snap.dividers_y || 0;
  $("box-lift").value = snap.bottom_lift || 0;
  state.lid = snap.lid || "open";
}

function pushUndo() {
  state.undo.push(snapshotForm());
  if (state.undo.length > 30) state.undo.shift();
}

function boxBody() {
  const body = {
    unit: $("box-unit").value,
    dimension_mode: $("box-dims").value,
    lid: $("box-lid").value,
    x: Number($("box-x").value),
    y: Number($("box-y").value),
    h: Number($("box-h").value),
    thickness: Number($("box-t").value),
    finger: Number($("box-finger").value),
    press_fit: $("box-bumps").checked,
    dividers_x: Number($("box-dx").value),
    dividers_y: Number($("box-dy").value),
    bottom_lift: Number($("box-lift").value),
    name: "studio-box",
  };
  const burn = $("box-burn").value;
  if (burn !== "") body.burn = Number(burn);
  // Custom divider layout from drag (positions preferred)
  if (Array.isArray(state.dividerXPos) && state.dividerXPos.length) {
    body.divider_x_mm = state.dividerXPos.slice();
    body.dividers_x = state.dividerXPos.length;
  } else if (Array.isArray(state.sx) && state.sx.length > 1) {
    body.sx = state.sx.slice();
    body.dividers_x = state.sx.length - 1;
  }
  if (Array.isArray(state.dividerYPos) && state.dividerYPos.length) {
    body.divider_y_mm = state.dividerYPos.slice();
    body.dividers_y = state.dividerYPos.length;
  } else if (Array.isArray(state.sy) && state.sy.length > 1) {
    body.sy = state.sy.slice();
    body.dividers_y = state.sy.length - 1;
  }
  return body;
}

async function makeBox(opts) {
  const options = opts || {};
  const preview = options.preview !== false; // live edits = fast preview by default
  const gen = ++state.rebuildGen;
  state.rebuilding = true;
  const btn = $("make-box");
  if (btn) btn.disabled = true;
  const lidLabel = ($("box-lid") && $("box-lid").value) || "kutu";
  setLoading(true, preview
    ? ("Önizleme: " + lidLabel + "…")
    : "SVG/DXF kaydediliyor…");
  setStatus(preview
    ? "Hızlı önizleme — kapak/ölçü 3D’ye işleniyor…"
    : "Parametrik kesim kaydediliyor (kalınlık sabit, eklemler güncellenir)…");
  const body = { ...boxBody(), preview };
  try {
    const { data } = await api("/api/studio/box", { method: "POST", body: JSON.stringify(body) });
    if (gen !== state.rebuildGen) return; // newer request won
    if (!data.success && data.ok === false) {
      setStatus((data.look_again || []).join(" ") || "Kota veya plan engeli.", "bad");
      paintExports(data);
      return;
    }
    if (!data.success) {
      setStatus((data.look_again || []).join(" ") || "Üretim başarısız.", "bad");
      return;
    }
    paintExports(data);
    loadAssembly(data.assembly);
    if (data.file_id) {
      history.replaceState(null, "", "/studio?file=" + encodeURIComponent(data.file_id));
    }
    setStatus(
      preview
        ? "Önizleme hazır. İndirmek için Yeniden üret’e bas."
        : "Kayıtlı kesim hazır.",
      "ok"
    );
  } finally {
    if (gen === state.rebuildGen) {
      state.rebuilding = false;
      setLoading(false);
      if (btn) btn.disabled = false;
    }
  }
}

function scheduleRebuild(immediate) {
  clearTimeout(state.rebuildTimer);
  // Instant optimistic lid so the viewport reacts before the server returns.
  showOptimisticLid();
  setLoading(true, "Kapak / ölçü güncelleniyor…");
  const delay = immediate ? 40 : 220;
  state.rebuildTimer = setTimeout(() => {
    pushUndo();
    makeBox({ preview: true }).catch((err) => {
      setLoading(false);
      setStatus(String(err), "bad");
    });
  }, delay);
}

function fileKindFromName(name, mime) {
  const n = String(name || "").toLowerCase();
  const m = String(mime || "").toLowerCase();
  if (n.endsWith(".svg") || m.includes("svg")) return "svg";
  if (n.endsWith(".plt") || n.endsWith(".hpgl") || n.endsWith(".hpgl2")) return "plt";
  if (n.endsWith(".dxf")) return "dxf";
  if (m.startsWith("image/") || /\.(png|jpe?g|webp|gif|bmp)$/i.test(n)) return "photo";
  return "";
}

function readFileAsDataURL(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(reader.error || new Error("read failed"));
    reader.readAsDataURL(file);
  });
}

function readFileAsText(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(reader.error || new Error("read failed"));
    reader.readAsText(file);
  });
}

async function onAiFileChange() {
  const input = $("ai-file");
  const file = input && input.files && input.files[0];
  if (!file) {
    state.attach = null;
    $("ai-file-name").textContent = "Dosya yok — yalnız prompt da olur.";
    return;
  }
  if (file.size > 8 * 1024 * 1024) {
    state.attach = null;
    $("ai-file-name").textContent = "Dosya 8 MB’dan büyük — küçültüp tekrar dene.";
    setStatus("Dosya çok büyük (max 8 MB).", "bad");
    input.value = "";
    return;
  }
  const kind = fileKindFromName(file.name, file.type);
  if (!kind) {
    state.attach = null;
    $("ai-file-name").textContent = "Destek: foto, SVG, PLT, DXF.";
    setStatus("Bu dosya türü desteklenmiyor.", "bad");
    return;
  }
  try {
    if (kind === "photo") {
      const dataUrl = await readFileAsDataURL(file);
      state.attach = { kind: "photo", name: file.name, image_base64: dataUrl, bytes: file.size };
    } else if (kind === "plt") {
      // Prefer text; fall back to base64 for odd encodings
      const text = await readFileAsText(file);
      state.attach = { kind: "plt", name: file.name, file_text: text, bytes: file.size };
    } else {
      const text = await readFileAsText(file);
      state.attach = { kind, name: file.name, file_text: text, bytes: file.size };
    }
    $("ai-file-name").textContent =
      kind.toUpperCase() + " · " + file.name + " · " + Math.round(file.size / 1024) + " KB";
    setStatus("Dosya hazır: " + file.name, "ok");
    scheduleAiCost();
  } catch (err) {
    state.attach = null;
    $("ai-file-name").textContent = "Dosya okunamadı.";
    setStatus(String(err), "bad");
  }
}

function paintAiCost(data) {
  const el = $("ai-cost-out");
  if (!el || !data) return;
  const studio = data.studio_ai || {};
  const mcp = data.mcp_host_ai || {};
  const keys = data.workshop_llm_keys || [];
  const configured = keys.filter((k) => k.configured).map((k) => k.provider + ":" + (k.prefix || "ok"));
  const studioUsd = (studio.usd && studio.usd.total != null) ? Number(studio.usd.total) : 0;
  const mcpUsd = (mcp.usd && mcp.usd.total != null) ? Number(mcp.usd.total) : null;
  const tok = (mcp.tokens && mcp.tokens.input_total) || 0;
  const q = studio.quota || {};
  const lines = [
    "Stüdyo: " + (studio.uses_workshop_key
      ? ("atölye " + (studio.provider || "LLM") + " ≈ $" + studioUsd.toFixed(5) + " (sizin API faturanız)")
      : "yerel planner $0"),
    "MCP host (" + (mcp.model_label || "model") + "): ≈ $" +
      (mcpUsd != null ? mcpUsd.toFixed(5) : "?") + " · ~" + tok + " in tok",
    "Kota: " + (q.used != null ? q.used + "/" + (q.limit || "?") : "—") +
      (q.plan ? " · " + q.plan : ""),
    "LLM anahtar: " + (configured.length ? configured.join(", ") : "yok → Hesap → LLM"),
    data.recommendation || "",
  ];
  el.textContent = lines.filter(Boolean).join("\n");
  el.style.whiteSpace = "pre-line";
}

let aiCostTimer = null;
function scheduleAiCost() {
  clearTimeout(aiCostTimer);
  aiCostTimer = setTimeout(() => {
    estimateAiCost().catch(() => {});
  }, 400);
}

async function estimateAiCost() {
  const body = {
    prompt: ($("ai-prompt") && $("ai-prompt").value) || "",
    model: ($("ai-model") && $("ai-model").value) || "gpt-4o-mini",
    has_photo: !!(state.attach && state.attach.kind === "photo"),
    mode: "mcp_thin",
  };
  if (!body.prompt && !(state.attach)) {
    $("ai-cost-out").textContent = "Prompt veya dosya yazınca maliyet tahmini çıkar.";
    return;
  }
  if (!body.prompt && state.attach) body.prompt = "upload:" + state.attach.kind + " " + state.attach.name;
  const { data } = await api("/api/studio/ai_cost", { method: "POST", body: JSON.stringify(body) });
  paintAiCost(data);
}

async function makeAi() {
  const btn = $("make-ai");
  btn.disabled = true;
  setLoading(true, "AI / dosya işleniyor…");
  setStatus("AI tasarlıyor…");
  const body = {
    prompt: $("ai-prompt").value,
    thickness: Number($("ai-t").value),
    width_mm: Number($("ai-w").value) || 200,
    model: ($("ai-model") && $("ai-model").value) || "gpt-4o-mini",
  };
  if (state.attach) {
    body.file_kind = state.attach.kind;
    if (state.attach.kind === "photo") {
      body.image_base64 = state.attach.image_base64;
      body.has_photo = true;
    } else if (state.attach.kind === "svg") {
      body.svg = state.attach.file_text;
      body.file_text = state.attach.file_text;
    } else if (state.attach.kind === "plt") {
      body.plt = state.attach.file_text;
      body.file_text = state.attach.file_text;
    } else if (state.attach.kind === "dxf") {
      body.dxf = state.attach.file_text;
      body.file_text = state.attach.file_text;
    }
  }
  try {
    const { data } = await api("/api/studio/ai", { method: "POST", body: JSON.stringify(body) });
    if (data.cost) paintAiCost(data.cost);
    if (data.ok === false || (!data.success && (data.look_again || []).length)) {
      setStatus((data.look_again || []).join(" ") || "AI kapalı veya kota doldu.", "bad");
      paintExports(data);
      return;
    }
    if (!data.success) {
      setStatus((data.look_again || []).join(" ") || "AI üretim başarısız.", "bad");
      return;
    }
    paintExports(data);
    if (data.assembly) loadAssembly(data.assembly);
    setStatus(
      "Hazır (" + (data.source || "ai") + "). " + ((data.look_again || [])[0] || ""),
      "ok"
    );
    if (data.file_id) {
      history.replaceState(null, "", "/studio?file=" + encodeURIComponent(data.file_id));
    }
  } finally {
    btn.disabled = false;
    setLoading(false);
  }
}

async function makeStl() {
  if (!state.fileId) {
    setStatus("Önce bir kutu veya AI tasarımı üretin.", "bad");
    return;
  }
  const btn = $("make-stl");
  btn.disabled = true;
  setStatus("SVG → STL (mm ölçek korunuyor)…");
  const body = {
    file_id: state.fileId,
    height_mm: Number($("stl-h").value),
    prompt: $("stl-hint").value,
  };
  const { data } = await api("/api/studio/stl", { method: "POST", body: JSON.stringify(body) });
  btn.disabled = false;
  if (!data.success) {
    setStatus((data.look_again || []).join(" ") || "STL üretilemedi.", "bad");
    return;
  }
  paintExports(data);
  const ai = data.ai || {};
  const bbox = (ai.bbox_mm) || {};
  $("stl-note").textContent =
    "STL " + (data.height_mm || "?") + " mm Z · XY " +
    (bbox.width || "?") + "×" + (bbox.depth || "?") + " mm (SVG) · " +
    (data.triangle_count || "?") + " üçgen";
  setStatus("STL hazır — ölçek mm. Baskı büzülmesi NOT_VERIFIED.", "ok");
}

function syncMakerFields() {
  const kind = ($("maker-kind") && $("maker-kind").value) || "name_ornament";
  const name = $("maker-fields-name");
  const bird = $("maker-fields-bird");
  const xmas = $("maker-fields-xmas");
  if (name) name.classList.toggle("hide", kind !== "name_ornament");
  if (bird) bird.classList.toggle("hide", kind !== "birdhouse");
  if (xmas) xmas.classList.toggle("hide", kind !== "christmas");
  const hole = $("maker-hole");
  if (hole) hole.closest("label").classList.toggle("hide", kind === "birdhouse");
  const note = $("maker-note");
  if (note) {
    if (kind === "birdhouse") note.textContent = "Boxes.py BirdHouse — finger-joint. AI yok.";
    else if (kind === "christmas") note.textContent = "Yıldız / daire ası süsü — parametrik, AI yok.";
    else note.textContent = "İsim süsü + ası deliği + kazıma yazı. Fiziksel kuruluk NOT_VERIFIED.";
  }
}

function makerBody() {
  const kind = ($("maker-kind") && $("maker-kind").value) || "name_ornament";
  const body = {
    maker: kind,
    thickness: Number(($("maker-t") && $("maker-t").value) || 3),
  };
  if (kind === "name_ornament") {
    body.text = ($("maker-text") && $("maker-text").value) || "LaserMCP";
    body.width = Number(($("maker-w") && $("maker-w").value) || 120);
    body.height = Number(($("maker-h") && $("maker-h").value) || 40);
    body.hang_hole_mm = Number(($("maker-hole") && $("maker-hole").value) || 4);
  } else if (kind === "birdhouse") {
    body.x = Number(($("maker-bx") && $("maker-bx").value) || 120);
    body.y = Number(($("maker-by") && $("maker-by").value) || 100);
    body.h = Number(($("maker-bh") && $("maker-bh").value) || 100);
    body.roof_overhang = Number(($("maker-overhang") && $("maker-overhang").value) || 0.4);
  } else {
    body.shape = ($("maker-shape") && $("maker-shape").value) || "star";
    body.text = ($("maker-xtext") && $("maker-xtext").value) || "";
    body.size = Number(($("maker-size") && $("maker-size").value) || 80);
    body.hang_hole_mm = Number(($("maker-hole") && $("maker-hole").value) || 4);
  }
  return body;
}

async function makeMaker() {
  const btn = $("make-maker");
  if (btn) btn.disabled = true;
  setLoading(true, "Parametrik süs üretiliyor…");
  setStatus("Hazır maker — AI yok…");
  try {
    const { data } = await api("/api/studio/maker", {
      method: "POST",
      body: JSON.stringify(makerBody()),
    });
    if (!data.success && data.ok === false) {
      setStatus((data.look_again || []).join(" ") || "Kota veya plan engeli.", "bad");
      paintExports(data);
      return;
    }
    if (!data.success) {
      setStatus((data.look_again || []).join(" ") || "Üretim başarısız.", "bad");
      return;
    }
    paintExports(data);
    const panels = data.assembly && data.assembly.panels;
    if (panels && panels.length) {
      loadAssembly(data.assembly);
    } else {
      clearMeshes();
      setStatus("SVG/DXF hazır (düz nest). 3D montaj bu maker için zorunlu değil.", "ok");
      $("sum-note").textContent = (data.summary && data.summary.maker)
        ? ("Maker: " + data.summary.maker + " · AI: hayır")
        : "Parametrik maker · AI yok";
    }
    if (data.file_id) {
      history.replaceState(null, "", "/studio?file=" + encodeURIComponent(data.file_id));
    }
    const label = (data.summary && data.summary.maker) || "maker";
    setStatus("Parametrik " + label + " hazır — AI kullanılmadı.", "ok");
    $("sum-plan").textContent = "parametric_maker";
    $("sum-val").textContent = data.final_status || "DIGITAL_PROTOTYPE";
  } finally {
    setLoading(false);
    if (btn) btn.disabled = false;
  }
}

function wireUi() {
  document.querySelectorAll(".tabs button").forEach((btn) => {
    btn.onclick = () => {
      document.querySelectorAll(".tabs button").forEach((b) => b.classList.remove("on"));
      btn.classList.add("on");
      document.querySelectorAll(".pane").forEach((p) => p.classList.remove("on"));
      $("pane-" + btn.dataset.tab).classList.add("on");
      if (btn.dataset.tab === "makers") syncMakerFields();
    };
  });
  $("box-lid").onchange = () => {
    state.lid = $("box-lid").value;
    scheduleRebuild(true); // lid change → immediate preview + overlay
  };
  [
    "box-x", "box-y", "box-h", "box-t", "box-finger", "box-burn",
    "box-dx", "box-dy", "box-lift", "box-unit", "box-dims",
  ].forEach((id) => {
    const el = $(id);
    if (!el) return;
    const onChange = () => {
      if (id === "box-dx") {
        state.dividerXPos = null;
        state.sx = null;
      }
      if (id === "box-dy") {
        state.dividerYPos = null;
        state.sy = null;
      }
      scheduleRebuild();
    };
    el.addEventListener("change", onChange);
    el.addEventListener("input", () => {
      if (id === "box-burn") return;
      onChange();
    });
  });
  $("box-bumps").onchange = scheduleRebuild;
  $("explode").oninput = () => {
    const t = Number($("explode").value) / 100;
    $("explode-lab").textContent = Math.round(t * 100) + "%";
    applyExplode(t);
  };
  $("make-box").onclick = () => {
    pushUndo();
    clearGhostLid();
    makeBox({ preview: false }); // full SVG/DXF export
  };
  $("undo-box").onclick = () => {
    const prev = state.undo.pop();
    if (!prev) {
      setStatus("Geri alınacak adım yok.");
      return;
    }
    restoreForm(prev);
    makeBox();
  };
  $("make-ai").onclick = makeAi;
  $("make-stl").onclick = makeStl;
  if ($("maker-kind")) {
    $("maker-kind").onchange = syncMakerFields;
    syncMakerFields();
  }
  if ($("make-maker")) $("make-maker").onclick = () => makeMaker().catch((e) => setStatus(String(e), "bad"));
  if ($("nest-flat")) {
    $("nest-flat").onclick = () => {
      $("explode").value = "100";
      $("explode-lab").textContent = "100% düz";
      applyExplode(1);
      paintNestStats();
      setStatus("Düz nest yerleşimi — paneller yan yana.", "ok");
    };
  }
  if ($("nest-assemble")) {
    $("nest-assemble").onclick = () => {
      $("explode").value = "0";
      $("explode-lab").textContent = "0%";
      applyExplode(0);
      setStatus("Montaj görünümü.", "ok");
    };
  }
  if ($("nest-gap")) {
    $("nest-gap").onchange = () => {
      // Gap is visual estimate in nest stats; flat layout uses fixed gap in loadAssembly.
      paintNestStats();
    };
  }
  if ($("ai-file")) $("ai-file").onchange = () => { onAiFileChange().catch((e) => setStatus(String(e), "bad")); };
  if ($("ai-file-clear")) {
    $("ai-file-clear").onclick = () => {
      state.attach = null;
      if ($("ai-file")) $("ai-file").value = "";
      $("ai-file-name").textContent = "Dosya yok — yalnız prompt da olur.";
      scheduleAiCost();
    };
  }
  if ($("ai-cost-btn")) $("ai-cost-btn").onclick = () => estimateAiCost().catch((e) => setStatus(String(e), "bad"));
  if ($("ai-prompt")) {
    $("ai-prompt").addEventListener("input", scheduleAiCost);
  }
  if ($("ai-model")) $("ai-model").onchange = scheduleAiCost;
  if ($("ai-w")) $("ai-w").addEventListener("change", scheduleAiCost);
  $("dim-pop-cancel").onclick = hideDimPop;
  $("dim-pop-apply").onclick = () => {
    const field = $("dim-pop").dataset.field;
    const field2 = $("dim-pop").dataset.field2;
    const val = $("dim-pop-val").value;
    if (field) $(field).value = val;
    // For walls, primary field is the edge length along that wall's width;
    // height stays on box-h via field2 only when user intends — keep H unless role needs both.
    if (field2 === "box-y" && field === "box-x") {
      // bottom/lid: changing one dim in popup edits X; Y unchanged unless typed same — OK
    }
    hideDimPop();
    pushUndo();
    scheduleRebuild();
  };
  window.addEventListener("keydown", (ev) => {
    if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === "z") {
      ev.preventDefault();
      $("undo-box").click();
    }
  });
  if ($("mcp-open")) {
    $("mcp-open").onclick = () => {
      const id = String(($("mcp-file-id") && $("mcp-file-id").value) || "").trim();
      if (!id) {
        setStatus("MCP file_id gir.", "bad");
        return;
      }
      history.replaceState(null, "", "/studio?file=" + encodeURIComponent(id));
      loadFile(id).catch((e) => setStatus(String(e), "bad"));
    };
  }
}

async function loadFile(fileId) {
  setStatus("Montaj yükleniyor…");
  const { data } = await api("/api/assembly/" + encodeURIComponent(fileId));
  if (!data.success || !(data.panels || []).length) {
    setStatus((data.look_again || []).join(" ") || "Kayıtlı montaj yok; yeni parametrik kutu üretiliyor…", "bad");
    await makeBox();
    return;
  }
  paintExports({
    file_id: data.file_id || fileId,
    svg_url: data.svg_url,
    dxf_id: data.dxf_id,
    dxf_url: data.dxf_url,
  });
  loadAssembly(data);
}

async function boot() {
  buildScene();
  wireUi();
  const { data } = await api("/api/account");
  if (data && data.user) document.body.classList.add("signed-in");
  const plans = await api("/api/plans");
  const planRows = (plans.data && plans.data.plans) || [];
  const free = planRows.find((p) => p.id === "free");
  if (free && free.platform_ai === false) {
    $("ai-gate").textContent = "AI Maker/Pro. Parametrik kutu ücretsiz kalır. MCP linki ayrı ve ince.";
  }
  const params = new URLSearchParams(location.search);
  const file = params.get("file");
  if (file) await loadFile(file);
  else await makeBox({ preview: true });
}

boot().catch((err) => setStatus(String(err), "bad"));
