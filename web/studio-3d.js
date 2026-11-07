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
  liftDrag: null,
  sx: null,
  sy: null,
  dividerXPos: null,
  dividerYPos: null,
  lockedCellsX: {},
  lockedCellsY: {},
  undo: [],
  flatLayouts: [],
  summary: null,
  attach: null,
  assemblyGuide: null,
  asmStep: 0,
  asmPlaying: false,
  asmTimer: null,
  asmAnim: null,
  asmPlayToken: 0,
  woodMate: null,
  histAbort: null,
  histLoading: false,
  fitExplodeRaf: null,
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
  if (/shelf-\d+/.test(leaf)) return "shelf";
  return "other";
}

function panelLeafId(partId) {
  return String(partId || "").toLowerCase().split("/").pop() || "";
}

function matchGuidePart(partId, guidePartId) {
  const leaf = panelLeafId(partId);
  const want = String(guidePartId || "").toLowerCase();
  if (!leaf || !want) return false;
  return leaf === want || leaf.endsWith(want) || leaf.includes(want);
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
      color: 0xb8956a,
      transparent: true,
      opacity: 0.32,
      roughness: 0.9,
      metalness: 0.02,
      depthWrite: false,
    });
  }
  if (!state.edgeGhost) {
    state.edgeGhost = new THREE.LineBasicMaterial({ color: 0xc4a574, transparent: true, opacity: 0.75 });
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
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setClearColor(document.documentElement.getAttribute("data-theme") === "light" ? 0xd9d3c8 : 0x0f1419, 1);
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 5000);
  camera.position.set(220, 180, 260);
  const controls = new OrbitControls(camera, canvas);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  // Keep the kit readable: no underground flips, no whip-spin on drag.
  controls.rotateSpeed = 0.38;
  controls.zoomSpeed = 0.85;
  controls.panSpeed = 0.55;
  controls.minPolarAngle = 0.18;          // ~10° from top
  controls.maxPolarAngle = Math.PI * 0.49; // stay above the floor plane
  controls.minDistance = 40;
  controls.maxDistance = 1800;
  controls.enablePan = true;
  controls.screenSpacePanning = true;
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
    color: 0xb8956a, transparent: true, opacity: 0.28, roughness: 0.9, metalness: 0.02, depthWrite: false,
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
          lift: !!h.userData.lift,
        };
        controls.enabled = false;
        canvas.style.cursor = "grabbing";
        if (state.handleMatHot) h.traverse((o) => {
          if (o.isMesh) o.material = state.handleMatHot;
        });
        setStatus(
          h.userData.lift
            ? "Yükseltilmiş taban · tut-çek · bırakınca yenilenir"
            : ("Tut-çek: " + field.replace("box-", "").toUpperCase() + " · bırakınca paneller yenilenir"),
          "ok"
        );
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
        ? (state.summary && state.summary.divider_x_pos) || state.dividerXPos || []
        : (state.summary && state.summary.divider_y_pos) || state.dividerYPos || []).map(Number);
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
      setStatus("Bölücüyü kaydır · Del = birleştir · bırakınca yenilenir", "ok");
      return;
    }
    if (obj) {
      selectPanel(obj);
      let hitLocal = null;
      if (obj.userData.role === "bottom" && obj.userData.baseMatrix) {
        const inv = obj.userData.baseMatrix.clone().invert();
        const local = hits[0].point.clone().applyMatrix4(inv);
        hitLocal = { x: local.x, y: local.y };
      }
      openDimPop(obj, ev.clientX, ev.clientY, hitLocal);
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
      // Soften stretch so far-camera drags don't jump tens of mm per pixel.
      const stretchGain = d.axis === "z" || d.lift ? 0.7 : 0.55;
      deltaWorld *= stretchGain;
      let next;
      if (d.lift || d.field === "box-lift") {
        const hi = Number($("box-h").value) || 70;
        const t = Number($("box-t").value) || 3;
        next = Math.round(Math.max(0, Math.min(hi - t - 8, d.startVal + deltaWorld * d.sign)) * 2) / 2;
        if (Number($(d.field).value) === next) return;
        $(d.field).value = String(next);
        if (d.handle) d.handle.position.z = Math.max(next, 2) + t / 2;
        $("sum-dims").textContent = "lift → " + next + " mm";
        return;
      }
      const lo = d.field === "box-h" ? 10 : 20;
      next = Math.round(Math.max(lo, Math.min(800, d.startVal + deltaWorld * d.sign)));
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
      color: 0x6aa4ff,
      emissive: 0x0d2744,
      roughness: 0.55,
      metalness: 0.15,
      transparent: true,
      opacity: 0.82,
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
  const z = hi + t + 1.2;
  // Thin axis bars — not chunky cubes that read as loose parts.
  const bar = Math.max(3.2, Math.min(5.5, Math.min(xi, yi) * 0.028));
  const stick = Math.max(16, Math.min(34, Math.min(xi, yi) * 0.16));
  const specs = [
    { field: "box-x", axis: "x", sign: 1, pos: [xi + stick / 2, yi / 2, z], size: [stick, bar, bar], cursor: "ew-resize" },
    { field: "box-x", axis: "x", sign: -1, pos: [-stick / 2, yi / 2, z], size: [stick, bar, bar], cursor: "ew-resize" },
    { field: "box-y", axis: "y", sign: 1, pos: [xi / 2, yi + stick / 2, z], size: [bar, stick, bar], cursor: "ns-resize" },
    { field: "box-y", axis: "y", sign: -1, pos: [xi / 2, -stick / 2, z], size: [bar, stick, bar], cursor: "ns-resize" },
  ];
  if (lid !== "open") {
    specs.push(
      { field: "box-h", axis: "z", sign: 1, pos: [xi / 2, yi / 2, z + stick / 2], size: [bar, bar, stick], cursor: "ns-resize", plane: "z" }
    );
  }
  const lift = Number(($("box-lift") && $("box-lift").value) || 0);
  const liftZ = Math.max(lift, 2) + t / 2;
  specs.push({
    field: "box-lift",
    axis: "z",
    sign: 1,
    pos: [xi / 2, bar * 0.4, liftZ],
    size: [Math.min(xi * 0.4, 42), bar * 0.85, bar * 0.85],
    cursor: "ns-resize",
    plane: "z",
    lift: true,
  });
  specs.forEach((s) => {
    const geom = new THREE.BoxGeometry(s.size[0], s.size[1], s.size[2]);
    const mesh = new THREE.Mesh(geom, state.handleMat);
    mesh.position.set(s.pos[0], s.pos[1], s.pos[2]);
    mesh.userData.resize = true;
    mesh.userData.field = s.field;
    mesh.userData.axis = s.axis;
    mesh.userData.sign = s.sign;
    mesh.userData.plane = s.plane || "xy";
    mesh.userData.lift = !!s.lift;
    const edges = new THREE.LineSegments(
      new THREE.EdgesGeometry(geom),
      new THREE.LineBasicMaterial({ color: s.lift ? 0xffe0a0 : 0xd7ebff })
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
  syncHandleVisibility();
}

function syncHandleVisibility() {
  if (!state.handleRoot) return;
  const explode = Number(($("explode") && $("explode").value) || 0);
  const guide = state.assemblyGuide;
  const total = ((guide && guide.assembly_order) || []).length;
  const full = !total || Number(state.asmStep || 0) >= total;
  // Handles only on the seated, fully assembled edit pose — never as floating “parts”.
  state.handleRoot.visible = explode < 6 && full && !state.asmPlaying;
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
  delete $("dim-pop").dataset.mode;
  delete $("dim-pop").dataset.cellX;
  delete $("dim-pop").dataset.cellY;
  if ($("dim-pop-cell-wrap")) $("dim-pop-cell-wrap").classList.add("hide");
  if ($("dim-pop-val-wrap")) $("dim-pop-val-wrap").classList.remove("hide");
  if ($("dim-pop-title")) $("dim-pop-title").textContent = "Panel ölçüsü";
}

function cellIndexAt(coord, cells, thickness) {
  const list = Array.isArray(cells) && cells.length ? cells : [Number.POSITIVE_INFINITY];
  let cursor = 0;
  const t = Number(thickness) || 0;
  for (let i = 0; i < list.length; i++) {
    const end = cursor + Number(list[i]);
    if (coord <= end + 1e-6) return i;
    cursor = end + t;
  }
  return list.length - 1;
}

function openCellLockPop(localX, localY) {
  const sx = (state.summary && state.summary.sx) || state.sx || [];
  const sy = (state.summary && state.summary.sy) || state.sy || [];
  const t = Number($("box-t").value) || 3;
  const dx = Number($("box-dx").value) || 0;
  const dy = Number($("box-dy").value) || 0;
  if (dx <= 0 && dy <= 0) return false;
  const ix = dx > 0 && sx.length ? cellIndexAt(localX, sx, t) : null;
  const iy = dy > 0 && sy.length ? cellIndexAt(localY, sy, t) : null;
  $("dim-pop").classList.remove("hide");
  $("dim-pop").dataset.mode = "cell-lock";
  if ($("dim-pop-title")) $("dim-pop-title").textContent = "Hücre kilidi";
  if ($("dim-pop-val-wrap")) $("dim-pop-val-wrap").classList.add("hide");
  if ($("dim-pop-cell-wrap")) $("dim-pop-cell-wrap").classList.remove("hide");
  const bits = [];
  if (ix != null) {
    $("dim-pop").dataset.cellX = String(ix);
    $("dim-pop-cx-wrap").classList.remove("hide");
    $("dim-pop-cx").value = String(Math.round(Number(sx[ix]) * 10) / 10);
    bits.push("X" + (ix + 1));
  } else {
    delete $("dim-pop").dataset.cellX;
    $("dim-pop-cx-wrap").classList.add("hide");
  }
  if (iy != null) {
    $("dim-pop").dataset.cellY = String(iy);
    $("dim-pop-cy-wrap").classList.remove("hide");
    $("dim-pop-cy").value = String(Math.round(Number(sy[iy]) * 10) / 10);
    bits.push("Y" + (iy + 1));
  } else {
    delete $("dim-pop").dataset.cellY;
    $("dim-pop-cy-wrap").classList.add("hide");
  }
  $("dim-pop-label").textContent = "Hücre " + bits.join("×") + " · ≥ 8 mm · kilitle";
  return true;
}

function openDimPop(group, _x, _y, hitLocal) {
  const role = panelRole(group.userData.partId);
  if (role === "bottom" && hitLocal && openCellLockPop(hitLocal.x, hitLocal.y)) {
    return;
  }
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
  $("dim-pop").dataset.mode = "panel";
  if ($("dim-pop-title")) $("dim-pop-title").textContent = "Panel ölçüsü";
  if ($("dim-pop-val-wrap")) $("dim-pop-val-wrap").classList.remove("hide");
  if ($("dim-pop-cell-wrap")) $("dim-pop-cell-wrap").classList.add("hide");
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
    const wantDx = Number(($("box-dx") && $("box-dx").value) || 0);
    const wantDy = Number(($("box-dy") && $("box-dy").value) || 0);
    if (Array.isArray(summary.sx) && summary.sx.length === wantDx + 1) state.sx = summary.sx.slice();
    if (Array.isArray(summary.sy) && summary.sy.length === wantDy + 1) state.sy = summary.sy.slice();
    // Only keep dragged positions when count still matches the form — otherwise equal cells win.
    if (Array.isArray(summary.divider_x_pos) && summary.divider_x_pos.length === wantDx) {
      state.dividerXPos = summary.divider_x_pos.slice();
    } else if (wantDx === 0) {
      state.dividerXPos = null;
      state.sx = null;
    }
    if (Array.isArray(summary.divider_y_pos) && summary.divider_y_pos.length === wantDy) {
      state.dividerYPos = summary.divider_y_pos.slice();
    } else if (wantDy === 0) {
      state.dividerYPos = null;
      state.sy = null;
    }
    if ($("box-shelves") && summary.shelves != null) {
      // Don't overwrite while user is typing; only sync when idle rebuild finished.
      if (!state.rebuilding) $("box-shelves").value = String(summary.shelves);
    }
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

function stopAssemblyPlay() {
  state.asmPlaying = false;
  state.asmPlayToken = (state.asmPlayToken || 0) + 1;
  if (state.asmTimer) {
    clearTimeout(state.asmTimer);
    state.asmTimer = null;
  }
  if (state.asmAnim) {
    cancelAnimationFrame(state.asmAnim);
    state.asmAnim = null;
  }
  if ($("asm-play")) $("asm-play").textContent = "▶ Oynat";
}

function sleep(ms) {
  return new Promise((resolve) => {
    state.asmTimer = setTimeout(() => {
      state.asmTimer = null;
      resolve();
    }, ms);
  });
}

function findMeshForGuidePart(partId) {
  for (const g of state.meshes || []) {
    if (matchGuidePart(g.userData.partId, partId)) return g;
  }
  return null;
}

function paintAssemblyGuide(guide) {
  state.assemblyGuide = guide || null;
  const stepsEl = $("asm-steps");
  const jointsEl = $("asm-joints");
  if (stepsEl) stepsEl.innerHTML = "";
  if (jointsEl) jointsEl.innerHTML = "";
  if (!guide || !(guide.steps || []).length) {
    if (stepsEl) {
      const li = document.createElement("li");
      li.textContent = "Montaj sırası yok — kutu üret.";
      stepsEl.appendChild(li);
    }
    if ($("asm-step")) {
      $("asm-step").max = "0";
      $("asm-step").value = "0";
    }
    if ($("asm-step-lab")) $("asm-step-lab").textContent = "0/0";
    state.asmStep = 0;
    (state.meshes || []).forEach((g) => setPanelMaterial(g, "seated"));
    syncHandleVisibility();
    return;
  }
  const steps = guide.steps || [];
  steps.forEach((s) => {
    const li = document.createElement("li");
    li.dataset.step = String(s.step);
    li.innerHTML = "<strong>" + s.step + ". " + (s.title_tr || s.part_id) + "</strong>"
      + "<span class=\"sub\">" + (s.detail_tr || "") + "</span>";
    li.onclick = () => {
      stopAssemblyPlay();
      setAssemblyStep(s.step, true);
    };
    stepsEl.appendChild(li);
  });
  (guide.connections || []).forEach((c) => {
    const li = document.createElement("li");
    li.dataset.cid = c.connection_id || "";
    li.innerHTML = "<strong>" + (c.connection_id || "?") + "</strong> "
      + (c.part_a || "?") + " ↔ " + (c.part_b || "?")
      + "<span class=\"sub\">" + (c.joint_type || "") + (c.edge_hint ? " · " + c.edge_hint : "")
      + " · " + (c.physical_fit || "NOT_VERIFIED") + "</span>";
    li.onclick = () => {
      stopAssemblyPlay();
      highlightConnection(c);
      setStatus((c.note || (c.part_a + " ↔ " + c.part_b)) + " · fiziksel NOT_VERIFIED", "ok");
    };
    jointsEl.appendChild(li);
  });
  if ($("asm-step")) {
    $("asm-step").max = String(steps.length);
    $("asm-step").value = String(steps.length);
  }
  state.asmStep = steps.length;
  if ($("asm-step-lab")) $("asm-step-lab").textContent = steps.length + "/" + steps.length;
  syncAsmStepList(steps.length);
  // Restore a clean assembled wood pose — never leave mid-step blue/hidden debris.
  if (state.meshes && state.meshes.length) {
    applyAssemblyStep(steps.length, false);
    syncHandleVisibility();
  }
}

function syncAsmStepList(step) {
  const stepsEl = $("asm-steps");
  if (!stepsEl) return;
  stepsEl.querySelectorAll("li").forEach((li) => {
    li.classList.toggle("on", Number(li.dataset.step) === Number(step));
  });
  const jointsEl = $("asm-joints");
  if (!jointsEl || !state.assemblyGuide) return;
  const active = (state.assemblyGuide.steps || []).find((s) => s.step === Number(step));
  const joinSet = new Set((active && active.joins) || []);
  jointsEl.querySelectorAll("li").forEach((li) => {
    li.classList.toggle("on", joinSet.has(li.dataset.cid));
  });
}

function highlightConnection(conn) {
  if (!state.woodMate) {
    state.woodMate = new THREE.MeshStandardMaterial({
      color: 0xffc857, emissive: 0x5a3a00, roughness: 0.45, metalness: 0.12,
    });
  }
  state.meshes.forEach((g) => {
    const hot = matchGuidePart(g.userData.partId, conn.part_a)
      || matchGuidePart(g.userData.partId, conn.part_b);
    g.visible = true;
    g.traverse((obj) => {
      if (obj.isMesh && obj.material && obj.material.isMeshStandardMaterial) {
        obj.material = hot ? state.woodMate : state.wood;
        obj.material.transparent = false;
        obj.material.opacity = 1;
      }
    });
  });
}

function setPanelMaterial(group, kind) {
  // kind: seated | active | mate | hidden | ghost
  if (!state.woodMate) {
    state.woodMate = new THREE.MeshStandardMaterial({
      color: 0xffc857, emissive: 0x5a3a00, roughness: 0.45, metalness: 0.12,
    });
  }
  if (!state.woodGhost) {
    state.woodGhost = new THREE.MeshStandardMaterial({
      color: 0xb8956a, transparent: true, opacity: 0.28, roughness: 0.9, metalness: 0.02, depthWrite: false,
    });
  }
  if (kind === "hidden") {
    group.visible = false;
    return;
  }
  group.visible = true;
  let mat = state.wood;
  if (kind === "active") mat = state.woodHi || state.woodMate;
  else if (kind === "mate") mat = state.woodMate;
  else if (kind === "ghost") mat = state.woodGhost;
  group.traverse((obj) => {
    if (obj.isMesh && obj.material && obj.material.isMeshStandardMaterial) {
      obj.material = mat;
    }
  });
}

function applyAssemblyStep(step, animateIncoming) {
  const guide = state.assemblyGuide;
  const order = (guide && guide.assembly_order) || [];
  const n = Math.max(0, Math.min(order.length, Number(step) || 0));
  state.asmStep = n;
  if ($("asm-step")) $("asm-step").value = String(n);
  if ($("asm-step-lab")) $("asm-step-lab").textContent = n + "/" + order.length;
  syncAsmStepList(n);

  // Force assembled explode pose (incoming panel still lerps from exploded)
  if ($("explode")) {
    $("explode").value = "0";
    $("explode-lab").textContent = "0%";
  }

  const placed = new Set(order.slice(0, n));
  const activeId = n > 0 ? order[n - 1] : null;
  const activeJoins = new Set();
  if (guide && activeId) {
    const st = (guide.steps || []).find((s) => s.part_id === activeId);
    (st && st.joins || []).forEach((id) => activeJoins.add(id));
  }
  const mateParts = new Set();
  if (guide && activeId) {
    (guide.connections || []).forEach((c) => {
      if (!activeJoins.has(c.connection_id)) return;
      if (c.part_a !== activeId) mateParts.add(c.part_a);
      if (c.part_b !== activeId) mateParts.add(c.part_b);
    });
  }

  let incoming = null;
  state.meshes.forEach((group) => {
    let kind = "hidden";
    let matchedOrder = null;
    for (const pid of order) {
      if (matchGuidePart(group.userData.partId, pid)) {
        matchedOrder = pid;
        break;
      }
    }
    if (!matchedOrder) {
      kind = n >= order.length ? "seated" : "ghost";
    } else if (!placed.has(matchedOrder)) {
      kind = "hidden";
    } else if (matchedOrder === activeId) {
      kind = "active";
    } else if (mateParts.has(matchedOrder)) {
      kind = "mate";
    } else {
      kind = "seated";
    }
    setPanelMaterial(group, kind);

    if (!group.userData.baseMatrix || !group.userData.seated) return;
    const m = group.userData.baseMatrix.clone();
    if (animateIncoming && matchedOrder === activeId && group.userData.exploded) {
      incoming = group;
      const from = group.userData.exploded.clone();
      const delta0 = from.clone().sub(group.userData.seated);
      const startM = group.userData.baseMatrix.clone();
      startM.setPosition(new THREE.Vector3().setFromMatrixPosition(startM).add(delta0));
      group.matrix.copy(startM);
      group.matrixWorldNeedsUpdate = true;
    } else {
      group.matrix.copy(m);
      group.matrixWorldNeedsUpdate = true;
    }
  });

  if (activeId) {
    const st = (guide.steps || []).find((s) => s.part_id === activeId);
    setStatus(
      (st ? (st.step + ". " + st.title_tr + " — " + st.detail_tr) : activeId)
      + " · fiziksel NOT_VERIFIED",
      "ok"
    );
  } else if (n === 0) {
    setStatus("Montaj başlangıcı — henüz panel yok.", "ok");
  } else {
    setStatus("Montaj tamam (dijital). Fiziksel dry-fit NOT_VERIFIED.", "ok");
  }
  syncHandleVisibility();

  if (!incoming) return Promise.resolve();
  const from = incoming.userData.exploded.clone();
  const to = incoming.userData.seated.clone();
  const start = performance.now();
  const dur = 900;
  return new Promise((resolve) => {
    const tick = (now) => {
      if (state.asmStep !== n) {
        resolve();
        return;
      }
      const u = Math.min(1, (now - start) / dur);
      const e = 1 - Math.pow(1 - u, 3);
      const p = from.clone().lerp(to, e);
      const delta = p.clone().sub(incoming.userData.seated);
      const mm = incoming.userData.baseMatrix.clone();
      mm.setPosition(new THREE.Vector3().setFromMatrixPosition(mm).add(delta));
      incoming.matrix.copy(mm);
      incoming.matrixWorldNeedsUpdate = true;
      if (u < 1) state.asmAnim = requestAnimationFrame(tick);
      else {
        incoming.matrix.copy(incoming.userData.baseMatrix);
        state.asmAnim = null;
        resolve();
      }
    };
    state.asmAnim = requestAnimationFrame(tick);
  });
}

function setAssemblyStep(step, animate) {
  return applyAssemblyStep(step, !!animate);
}

async function playAssemblyAnimation() {
  const guide = state.assemblyGuide;
  const total = ((guide && guide.assembly_order) || []).length;
  if (!total) {
    setStatus("Önce kutu üret — montaj sırası yok.", "bad");
    return;
  }
  if (state.asmPlaying) {
    stopAssemblyPlay();
    return;
  }
  const token = (state.asmPlayToken || 0) + 1;
  state.asmPlayToken = token;
  state.asmPlaying = true;
  if ($("asm-play")) $("asm-play").textContent = "■ Dur";

  // Peek exploded layout so "incoming from outside" is readable, then assemble.
  state.meshes.forEach((g) => setPanelMaterial(g, "seated"));
  if ($("explode")) {
    $("explode").value = "55";
    $("explode-lab").textContent = "55%";
  }
  applyExplode(0.55);
  fitCamera();
  await sleep(500);
  if (!state.asmPlaying || state.asmPlayToken !== token) return;

  await setAssemblyStep(0, false);
  fitCameraSoon();
  await sleep(350);
  for (let step = 1; step <= total; step += 1) {
    if (!state.asmPlaying || state.asmPlayToken !== token) return;
    await setAssemblyStep(step, true);
    fitCameraSoon();
    if (step < total) await sleep(700);
  }
  if (!state.asmPlaying || state.asmPlayToken !== token) return;
  stopAssemblyPlay();
  await setAssemblyStep(total, false);
  fitCamera();
  setStatus("Montaj animasyonu bitti — dijital sıra. Fiziksel NOT_VERIFIED.", "ok");
}

function loadAssembly(assembly) {
  clearGhostLid();
  stopAssemblyPlay();
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
  const gap = Math.max(2, Math.min(30, Number(($("nest-gap") && $("nest-gap").value) || 6)));
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
  if ($("explode")) {
    $("explode").value = "0";
    $("explode-lab").textContent = "0%";
  }
  applyExplode(0);
  state.meshes.forEach((g) => setPanelMaterial(g, "seated"));
  rebuildResizeHandles();
  syncHandleVisibility();
  fitCamera();
  setStatus("İnce tutamaç / bölücü tut-çek · ▶ Oynat = montaj sırası.", "ok");
  $("sum-panels").textContent = String(panels.length);
  $("sum-t").textContent = thickness + " mm";
  $("sum-val").textContent = assembly.validation_state || "—";
  $("sum-sel").textContent = "—";
  $("sum-dims").textContent = "—";
  $("sum-note").textContent = assembly.note || "Kapak kenarı = boyut · bölücü = kaydır.";
  if ($("box-t") && thickness) $("box-t").value = String(thickness);
  if ($("stl-h") && thickness) $("stl-h").value = String(thickness);
  paintNestStats();
  applyLidOpenPreview();
  if (state.assemblyGuide) {
    const n = (state.assemblyGuide.assembly_order || []).length;
    setAssemblyStep(n, false);
  }
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
  syncHandleVisibility();
}

function fitCamera() {
  // Frame visible wood panels only — ignore resize handles / ghost lids.
  if (view && view.root) view.root.updateMatrixWorld(true);
  const box = new THREE.Box3();
  let any = false;
  (state.meshes || []).forEach((g) => {
    if (!g.visible) return;
    const b = new THREE.Box3().setFromObject(g);
    if (b.isEmpty()) return;
    if (!any) { box.copy(b); any = true; }
    else box.union(b);
  });
  if (!any) {
    const fallback = new THREE.Box3().setFromObject(view.root);
    if (fallback.isEmpty()) return;
    box.copy(fallback);
  }
  const size = box.getSize(new THREE.Vector3());
  const center = box.getCenter(new THREE.Vector3());
  const maxDim = Math.max(size.x, size.y, size.z, 40);
  const dist = maxDim * 1.55;
  view.controls.target.copy(center);
  view.camera.near = Math.max(0.1, maxDim / 200);
  view.camera.far = Math.max(2000, maxDim * 20);
  view.camera.updateProjectionMatrix();
  view.camera.position.set(center.x + dist * 0.95, center.y + dist * 0.72, center.z + dist * 1.05);
  view.controls.update();
}

function fitCameraSoon() {
  if (state.fitExplodeRaf) return;
  state.fitExplodeRaf = requestAnimationFrame(() => {
    state.fitExplodeRaf = null;
    fitCamera();
  });
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

function paintGate(data) {
  const status = data.final_status || (data.preview ? "PREVIEW_ONLY" : "—");
  const isPreview = !!(data.preview || data.gate_skipped || status === "PREVIEW_ONLY");
  // Live preview must not hide the last authorized download.
  const exportOk = !!state.fileId && (
    isPreview
      ? true
      : (data.export_allowed !== false && status !== "BLOCKED" && status !== "FAIL")
  );
  if ($("sum-val")) $("sum-val").textContent = status;
  if ($("sum-export")) {
    $("sum-export").textContent = exportOk
      ? (isPreview ? "son kayıt indirilebilir" : "izinli")
      : (isPreview && !state.fileId ? "önizleme — henüz kayıt yok" : "BLOCKED");
  }
  if ($("gate-badge")) {
    if (isPreview) {
      $("gate-badge").textContent = state.fileId
        ? "PREVIEW_ONLY (gate atlandı) — son kayıtlı SVG hâlâ indirilebilir."
        : "PREVIEW_ONLY — Final Gate / nest atlandı. Henüz kayıt yok.";
    } else if (status === "BLOCKED") {
      $("gate-badge").textContent = "BLOCKED — SVG/DXF yetkisiz. look_again’e bak.";
    } else if (status === "PROTOTYPE READY" || status === "DIGITAL_PROTOTYPE_READY") {
      $("gate-badge").textContent = "DIGITAL PROTOTYPE READY — fiziksel fit NOT_VERIFIED.";
    } else {
      $("gate-badge").textContent = "Gate: " + status + " · fiziksel NOT_VERIFIED.";
    }
  }
  const scoreEl = $("gate-score");
  if (scoreEl) {
    scoreEl.innerHTML = "";
    const card = data.scorecard || {};
    const rows = Object.keys(card).length
      ? Object.entries(card)
      : [
        ["preview", data.preview ? "PASS" : "—"],
        ["joints", (data.joints && data.joints.status) || "—"],
        ["final_gate", data.gate_skipped ? "SKIPPED" : status],
        ["physical_fit", "NOT_VERIFIED"],
      ];
    rows.forEach(([k, v]) => {
      const li = document.createElement("li");
      li.innerHTML = "<strong>" + k + "</strong> · " + String(v);
      scoreEl.appendChild(li);
    });
  }
  if ($("gate-looks")) {
    const looks = data.look_again || [];
    $("gate-looks").textContent = looks.length ? looks.slice(0, 8).join("\n") : "";
  }
  // Lock download buttons only when a non-preview response forbids export.
  if (!isPreview && !exportOk) {
    ["dl-svg", "dl-dxf", "open-edit"].forEach((id) => {
      const el = $(id);
      if (!el) return;
      el.classList.add("hide");
      el.removeAttribute("href");
    });
  }
  if ($("make-box")) {
    $("make-box").disabled = false;
    $("make-box").title = (!isPreview && status === "BLOCKED")
      ? "Son kayıt BLOCKED — düzeltip tekrar kaydet"
      : "";
  }
}

function paintExports(data) {
  const incoming = data.file_id || (data.assembly && data.assembly.file_id) || null;
  // Preview responses have no file_id — keep the last saved export so download links stay usable.
  if (incoming) {
    state.fileId = incoming;
    state.svgUrl = data.svg_url || ("/files/" + encodeURIComponent(incoming) + "?download=1");
    state.dxfId = data.dxf_id || null;
    state.dxfUrl = data.dxf_url || (data.dxf_id ? ("/files/" + encodeURIComponent(data.dxf_id) + "?download=1") : null);
  } else if (data.preview && state.fileId) {
    // keep previous
  } else if (!data.preview) {
    state.fileId = null;
    state.svgUrl = null;
    state.dxfId = null;
    state.dxfUrl = null;
  }
  const fileId = state.fileId;
  $("sum-file").textContent = fileId || (data.preview ? "önizleme (kayıt yok)" : "—");
  paintJoints(data);
  const svg = $("dl-svg");
  const dxf = $("dl-dxf");
  const edit = $("open-edit");
  if (fileId) {
    svg.href = state.svgUrl || ("/files/" + encodeURIComponent(fileId) + "?download=1");
    svg.setAttribute("download", fileId);
    svg.classList.remove("hide");
    edit.href = "/out/" + encodeURIComponent(fileId);
    edit.classList.remove("hide");
  } else {
    svg.classList.add("hide");
    edit.classList.add("hide");
  }
  if (state.dxfUrl || state.dxfId) {
    dxf.href = state.dxfUrl || ("/files/" + encodeURIComponent(state.dxfId) + "?download=1");
    dxf.setAttribute("download", state.dxfId || "cut.dxf");
    dxf.classList.remove("hide");
  } else if (!data.preview) {
    dxf.classList.add("hide");
  }
  if (data.stl_url || data.stl_id) {
    const stl = $("dl-stl");
    stl.href = data.stl_url || ("/files/" + encodeURIComponent(data.stl_id) + "?download=1");
    stl.classList.remove("hide");
  }
  const plan = data.plan || {};
  $("sum-plan").textContent = plan.plan_name || plan.plan || "—";
  if (plan.quota != null) $("sum-quota").textContent = (plan.used || 0) + " / " + plan.quota;
  paintSummary(data.summary);
  const guide = data.assembly_guide
    || (data.summary && data.summary.assembly_guide)
    || null;
  if (guide) {
    paintAssemblyGuide(guide);
  } else if (!data.preview) {
    // Saved/non-box payloads without a guide: clear lists once, don't wipe on every preview miss.
    paintAssemblyGuide(null);
  }
  paintGate(data);
  const saveHint = $("export-hint");
  if (saveHint) {
    if (data.preview || data.gate_skipped) {
      saveHint.textContent = "Önizleme kaydetmez / gate yok. «Kaydet ve indir» = Final Gate + SVG.";
    } else if (data.final_status === "BLOCKED" || data.export_allowed === false) {
      saveHint.textContent = "BLOCKED — indirme yok. Gate / look_again listesine bak.";
    } else if (fileId) {
      const dxfNote = (state.dxfUrl || state.dxfId) ? " SVG/DXF indirilebilir." : " SVG indirilebilir (DXF plana bağlı).";
      saveHint.textContent = "Kayıtlı: " + fileId + " —" + dxfNote;
    } else {
      saveHint.textContent = "Çıktı için «Kaydet ve indir».";
    }
  }
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
    bump_d: $("box-bump-d") ? $("box-bump-d").value : "0.5",
    handle: $("box-handle") ? $("box-handle").checked : true,
    handle_w: $("box-handle-w") ? $("box-handle-w").value : "40",
    lid_r: $("box-lid-r") ? $("box-lid-r").value : "0",
    lid_open: $("box-lid-open") ? $("box-lid-open").checked : false,
    dividers_x: $("box-dx").value,
    dividers_y: $("box-dy").value,
    shelves: $("box-shelves") ? $("box-shelves").value : "0",
    div_walls: $("box-div-walls") ? $("box-div-walls").checked : true,
    div_bottom: $("box-div-bottom") ? $("box-div-bottom").checked : true,
    bottom_lift: $("box-lift").value,
    dividerXPos: state.dividerXPos ? state.dividerXPos.slice() : null,
    dividerYPos: state.dividerYPos ? state.dividerYPos.slice() : null,
    lockedCellsX: state.lockedCellsX ? { ...state.lockedCellsX } : {},
    lockedCellsY: state.lockedCellsY ? { ...state.lockedCellsY } : {},
    material: $("box-material") ? $("box-material").value : "poplar_3mm",
    machine: $("box-machine") ? $("box-machine").value : "payas_workshop",
    nest_gap: $("nest-gap") ? $("nest-gap").value : "6",
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
  if ($("box-material") && snap.material) $("box-material").value = snap.material;
  if ($("box-machine") && snap.machine) $("box-machine").value = snap.machine;
  if ($("nest-gap") && snap.nest_gap != null) $("nest-gap").value = snap.nest_gap;
  $("box-finger").value = snap.finger;
  $("box-burn").value = snap.burn || "";
  $("box-bumps").checked = !!snap.press_fit;
  if ($("box-bump-d") && snap.bump_d != null) $("box-bump-d").value = snap.bump_d;
  if ($("box-handle") && snap.handle != null) $("box-handle").checked = !!snap.handle;
  if ($("box-handle-w") && snap.handle_w != null) $("box-handle-w").value = snap.handle_w;
  if ($("box-lid-r") && snap.lid_r != null) $("box-lid-r").value = snap.lid_r;
  if ($("box-lid-open") && snap.lid_open != null) $("box-lid-open").checked = !!snap.lid_open;
  $("box-dx").value = snap.dividers_x || 0;
  $("box-dy").value = snap.dividers_y || 0;
  if ($("box-shelves") && snap.shelves != null) $("box-shelves").value = snap.shelves;
  if ($("box-div-walls") && snap.div_walls != null) $("box-div-walls").checked = !!snap.div_walls;
  if ($("box-div-bottom") && snap.div_bottom != null) $("box-div-bottom").checked = !!snap.div_bottom;
  $("box-lift").value = snap.bottom_lift || 0;
  state.dividerXPos = Array.isArray(snap.dividerXPos) ? snap.dividerXPos.slice() : null;
  state.dividerYPos = Array.isArray(snap.dividerYPos) ? snap.dividerYPos.slice() : null;
  state.lockedCellsX = snap.lockedCellsX ? { ...snap.lockedCellsX } : {};
  state.lockedCellsY = snap.lockedCellsY ? { ...snap.lockedCellsY } : {};
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
  if ($("box-shelves")) body.shelves = Number($("box-shelves").value) || 0;
  if ($("box-handle")) body.handle = !!$("box-handle").checked;
  if ($("box-handle-w")) body.handle_w = Number($("box-handle-w").value) || 40;
  if ($("box-lid-r")) body.lid_radius = Number($("box-lid-r").value) || 0;
  if ($("box-bump-d")) body.bump_diameter = Number($("box-bump-d").value) || 0.5;
  if ($("box-div-walls")) body.divider_joint_walls = !!$("box-div-walls").checked;
  if ($("box-div-bottom")) body.divider_joint_bottom = !!$("box-div-bottom").checked;
  if ($("box-material")) body.material = $("box-material").value;
  if ($("box-machine")) body.machine = $("box-machine").value;
  if ($("nest-gap")) body.nest_gap_mm = Number($("nest-gap").value) || 6;
  // Custom divider layout from drag — only when count matches the form fields.
  const dx = body.dividers_x;
  const dy = body.dividers_y;
  if (Array.isArray(state.dividerXPos) && state.dividerXPos.length === dx && dx > 0) {
    body.divider_x_mm = state.dividerXPos.slice();
  } else {
    state.dividerXPos = null;
    if (Array.isArray(state.sx) && state.sx.length === dx + 1 && dx > 0) body.sx = state.sx.slice();
    else state.sx = null;
  }
  if (Array.isArray(state.dividerYPos) && state.dividerYPos.length === dy && dy > 0) {
    body.divider_y_mm = state.dividerYPos.slice();
  } else {
    state.dividerYPos = null;
    if (Array.isArray(state.sy) && state.sy.length === dy + 1 && dy > 0) body.sy = state.sy.slice();
    else state.sy = null;
  }
  if (state.lockedCellsX && Object.keys(state.lockedCellsX).length) {
    body.locked_cells_x = state.lockedCellsX;
  }
  if (state.lockedCellsY && Object.keys(state.lockedCellsY).length) {
    body.locked_cells_y = state.lockedCellsY;
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
    if (data.assembly) loadAssembly(data.assembly);
    paintExports(data);
    if (data.file_id) {
      history.replaceState(null, "", "/studio?file=" + encodeURIComponent(data.file_id));
    }
    if (!preview && (data.final_status === "BLOCKED" || data.export_allowed === false)) {
      setStatus("BLOCKED — indirme yok. " + ((data.look_again || [])[0] || "Gate başarısız."), "bad");
    } else {
      setStatus(
        preview
          ? "Önizleme (PREVIEW_ONLY) — gate yok. «Kaydet ve indir» ile yetkilendir."
          : (data.file_id ? ("Kayıtlı: " + (data.final_status || "OK") + " — SVG indir.") : "Üretim bitti."),
        "ok"
      );
    }
    if (!preview && options.autoDownload && data.file_id && data.export_allowed !== false) {
      const href = data.svg_url || ("/files/" + encodeURIComponent(data.file_id) + "?download=1");
      const a = document.createElement("a");
      a.href = href;
      a.download = data.file_id;
      a.rel = "noopener";
      document.body.appendChild(a);
      a.click();
      a.remove();
    }
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
  stopAssemblyPlay();
  // Instant optimistic lid so the viewport reacts before the server returns.
  showOptimisticLid();
  setLoading(true, "Kapak / ölçü güncelleniyor…");
  const delay = immediate ? 40 : 220;
  state.rebuildTimer = setTimeout(() => {
    // Do NOT pushUndo here — live preview would flood the undo stack every keystroke.
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
    if (data.assembly) loadAssembly(data.assembly);
    paintExports(data);
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
    const panels = data.assembly && data.assembly.panels;
    if (panels && panels.length) {
      loadAssembly(data.assembly);
    } else {
      clearMeshes();
      $("sum-note").textContent = (data.summary && data.summary.maker)
        ? ("Maker: " + data.summary.maker + " · AI: hayır")
        : "Parametrik maker · AI yok";
    }
    paintExports(data);
    if (data.file_id) {
      history.replaceState(null, "", "/studio?file=" + encodeURIComponent(data.file_id));
    }
    const label = (data.summary && data.summary.maker) || "maker";
    $("sum-plan").textContent = "parametric_maker";
    $("sum-val").textContent = data.final_status || "DIGITAL_PROTOTYPE";
    if (data.final_status === "BLOCKED" || data.export_allowed === false) {
      setStatus(
        "BLOCKED — " + label + " indirme yok. " + ((data.look_again || [])[0] || "Gate başarısız."),
        "bad"
      );
    } else if (panels && panels.length) {
      setStatus("Parametrik " + label + " hazır — AI yok. Fiziksel NOT_VERIFIED.", "ok");
    } else {
      setStatus("SVG/DXF hazır (düz nest). 3D montaj bu maker için zorunlu değil.", "ok");
    }
  } finally {
    setLoading(false);
    if (btn) btn.disabled = false;
  }
}

function currentTheme() {
  const t = document.documentElement.getAttribute("data-theme");
  return t === "light" ? "light" : "dark";
}

function applyTheme(theme) {
  const next = theme === "light" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  try { localStorage.setItem("lasermcp-studio-theme", next); } catch (_) { /* ignore */ }
  const meta = document.getElementById("meta-theme-color");
  if (meta) meta.setAttribute("content", next === "light" ? "#f3f1ec" : "#0f1419");
  const btn = $("theme-toggle");
  if (btn) {
    btn.textContent = next === "light" ? "Açık" : "Koyu";
    btn.setAttribute("aria-pressed", next === "dark" ? "true" : "false");
    btn.title = next === "light" ? "Koyu temaya geç" : "Açık temaya geç";
  }
  // Soften the 3D clear color with the stage wash.
  if (view && view.renderer) {
    view.renderer.setClearColor(next === "light" ? 0xd9d3c8 : 0x0f1419, 1);
  }
}

function wireUi() {
  applyTheme(currentTheme());
  if ($("theme-toggle")) {
    $("theme-toggle").onclick = () => {
      applyTheme(currentTheme() === "dark" ? "light" : "dark");
    };
  }
  document.querySelectorAll(".tabs button").forEach((btn) => {
    btn.onclick = () => {
      document.querySelectorAll(".tabs button").forEach((b) => b.classList.remove("on"));
      btn.classList.add("on");
      document.querySelectorAll(".pane").forEach((p) => p.classList.remove("on"));
      const pane = $("pane-" + btn.dataset.tab);
      if (pane) pane.classList.add("on");
      if (btn.dataset.tab === "makers") syncMakerFields();
      if (btn.dataset.tab === "calibrate") loadCalibrations().catch(() => {});
      if (btn.dataset.tab === "history") loadProjectHistory().catch(() => {});
    };
  });
  $("box-lid").onchange = () => {
    pushUndo();
    state.lid = $("box-lid").value;
    scheduleRebuild(true); // lid change → immediate preview + overlay
  };
  if ($("box-lid-open")) {
    $("box-lid-open").onchange = () => applyLidOpenPreview();
  }
  [
    "box-x", "box-y", "box-h", "box-t", "box-finger", "box-burn",
    "box-dx", "box-dy", "box-lift", "box-unit", "box-dims",
    "box-handle-w", "box-lid-r", "box-bump-d",
  ].forEach((id) => {
    const el = $(id);
    if (!el) return;
    const applyFields = () => {
      if (id === "box-dx") {
        state.dividerXPos = null;
        state.sx = null;
        state.lockedCellsX = {};
      }
      if (id === "box-dy") {
        state.dividerYPos = null;
        state.sy = null;
        state.lockedCellsY = {};
      }
    };
    el.addEventListener("change", () => {
      applyFields();
      pushUndo();
      scheduleRebuild(true);
    });
    el.addEventListener("input", () => {
      if (id === "box-burn") return;
      applyFields();
      scheduleRebuild(); // live preview — undo only on change/commit
    });
  });
  $("box-bumps").onchange = () => { pushUndo(); scheduleRebuild(true); };
  ["box-handle", "box-div-walls", "box-div-bottom"].forEach((id) => {
    if ($(id)) $(id).onchange = () => { pushUndo(); scheduleRebuild(true); };
  });
  $("explode").oninput = () => {
    stopAssemblyPlay();
    // Restore all panels visible when scrubbing explode
    state.meshes.forEach((g) => setPanelMaterial(g, "seated"));
    const t = Number($("explode").value) / 100;
    $("explode-lab").textContent = Math.round(t * 100) + "%";
    applyExplode(t);
    fitCameraSoon();
  };
  $("explode").onchange = () => {
    applyExplode(Number($("explode").value) / 100);
    fitCamera();
  };
  if ($("asm-play")) $("asm-play").onclick = () => playAssemblyAnimation();
  if ($("asm-prev")) {
    $("asm-prev").onclick = () => {
      stopAssemblyPlay();
      setAssemblyStep(Math.max(0, (state.asmStep || 0) - 1), true);
    };
  }
  if ($("asm-next")) {
    $("asm-next").onclick = () => {
      stopAssemblyPlay();
      const max = ((state.assemblyGuide && state.assemblyGuide.assembly_order) || []).length;
      setAssemblyStep(Math.min(max, (state.asmStep || 0) + 1), true);
    };
  }
  if ($("asm-step")) {
    $("asm-step").oninput = () => {
      stopAssemblyPlay();
      setAssemblyStep(Number($("asm-step").value) || 0, false);
    };
  }
  $("make-box").onclick = () => {
    pushUndo();
    clearGhostLid();
    makeBox({ preview: false, autoDownload: true }); // full SVG/DXF + trigger download
  };
  function bumpCount(id, delta, lo, hi) {
    const el = $(id);
    if (!el) return;
    pushUndo();
    const next = Math.max(lo, Math.min(hi, (Number(el.value) || 0) + delta));
    el.value = String(next);
    if (id === "box-dx") { state.dividerXPos = null; state.sx = null; state.lockedCellsX = {}; }
    if (id === "box-dy") { state.dividerYPos = null; state.sy = null; state.lockedCellsY = {}; }
    scheduleRebuild(true);
  }
  if ($("dx-plus")) $("dx-plus").onclick = () => bumpCount("box-dx", 1, 0, 8);
  if ($("dx-minus")) $("dx-minus").onclick = () => bumpCount("box-dx", -1, 0, 8);
  if ($("dy-plus")) $("dy-plus").onclick = () => bumpCount("box-dy", 1, 0, 8);
  if ($("dy-minus")) $("dy-minus").onclick = () => bumpCount("box-dy", -1, 0, 8);
  if ($("sh-plus")) $("sh-plus").onclick = () => bumpCount("box-shelves", 1, 0, 6);
  if ($("sh-minus")) $("sh-minus").onclick = () => bumpCount("box-shelves", -1, 0, 6);
  if ($("box-shelves")) {
    $("box-shelves").addEventListener("change", () => scheduleRebuild(true));
    $("box-shelves").addEventListener("input", () => scheduleRebuild());
  }
  if ($("dl-svg")) {
    $("dl-svg").addEventListener("click", (ev) => {
      if (state.fileId) return;
      ev.preventDefault();
      setStatus("Önce «Kaydet ve indir» ile dosyayı kaydet.", "bad");
      makeBox({ preview: false, autoDownload: true }).catch((e) => setStatus(String(e), "bad"));
    });
  }
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
      paintNestStats();
      if (state.assembly) loadAssembly(state.assembly); // re-pack flat layout with new gap
    };
  }
  if ($("box-material")) $("box-material").onchange = onMaterialChange;
  if ($("box-machine")) $("box-machine").onchange = onMachineChange;
  if ($("make-coupon")) $("make-coupon").onclick = () => makeCoupon().catch((e) => setStatus(String(e), "bad"));
  if ($("cal-save")) $("cal-save").onclick = () => saveCalibration().catch((e) => setStatus(String(e), "bad"));
  if ($("cal-apply")) $("cal-apply").onclick = () => applyCalibrationBurn();
  if ($("hist-refresh")) $("hist-refresh").onclick = () => loadProjectHistory().catch((e) => setStatus(String(e), "bad"));
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
    if ($("dim-pop").dataset.mode === "cell-lock") {
      pushUndo();
      state.dividerXPos = null;
      state.dividerYPos = null;
      if ($("dim-pop").dataset.cellX != null) {
        const ix = Number($("dim-pop").dataset.cellX);
        const w = Math.max(8, Number($("dim-pop-cx").value) || 8);
        state.lockedCellsX = { ...(state.lockedCellsX || {}), [ix]: w };
        state.sx = null;
      }
      if ($("dim-pop").dataset.cellY != null) {
        const iy = Number($("dim-pop").dataset.cellY);
        const d = Math.max(8, Number($("dim-pop-cy").value) || 8);
        state.lockedCellsY = { ...(state.lockedCellsY || {}), [iy]: d };
        state.sy = null;
      }
      hideDimPop();
      scheduleRebuild(true);
      setStatus("Hücre kilitlendi — kalan hücreler eşit dağıtılır.", "ok");
      return;
    }
    const field = $("dim-pop").dataset.field;
    const val = $("dim-pop-val").value;
    if (field) $(field).value = val;
    hideDimPop();
    pushUndo();
    scheduleRebuild();
  };
  window.addEventListener("keydown", (ev) => {
    if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === "z") {
      ev.preventDefault();
      $("undo-box").click();
      return;
    }
    if (ev.key === "Delete" || ev.key === "Backspace") {
      const tag = (ev.target && ev.target.tagName) || "";
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if (!state.selected || !state.selected.userData.divider) return;
      ev.preventDefault();
      mergeSelectedDivider();
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

function mergeSelectedDivider() {
  const div = state.selected && state.selected.userData.divider;
  if (!div) return;
  pushUndo();
  const axis = div.axis;
  const idx = div.index;
  const positions = (axis === "x"
    ? (state.dividerXPos || (state.summary && state.summary.divider_x_pos) || [])
    : (state.dividerYPos || (state.summary && state.summary.divider_y_pos) || [])).map(Number);
  if (idx < 0 || idx >= positions.length) return;
  positions.splice(idx, 1);
  if (axis === "x") {
    state.dividerXPos = positions.length ? positions : null;
    state.sx = null;
    state.lockedCellsX = {};
    $("box-dx").value = String(positions.length);
  } else {
    state.dividerYPos = positions.length ? positions : null;
    state.sy = null;
    state.lockedCellsY = {};
    $("box-dy").value = String(positions.length);
  }
  selectPanel(null);
  hideDimPop();
  scheduleRebuild(true);
  setStatus("Bölücü silindi — hücreler birleşti.", "ok");
}

function applyLidOpenPreview() {
  const open = $("box-lid-open") && $("box-lid-open").checked;
  const lid = ($("box-lid") && $("box-lid").value) || "open";
  if (!open || lid === "open") {
    clearGhostLid();
    return;
  }
  showOptimisticLid();
}

async function loadFile(fileId) {
  setStatus("Montaj yükleniyor…");
  const { data } = await api("/api/assembly/" + encodeURIComponent(fileId));
  if (!data.success || !(data.panels || []).length) {
    setStatus((data.look_again || []).join(" ") || "Kayıtlı montaj yok; yeni parametrik kutu üretiliyor…", "bad");
    await makeBox();
    return;
  }
  loadAssembly(data);
  paintExports({
    file_id: data.file_id || fileId,
    svg_url: data.svg_url,
    dxf_id: data.dxf_id,
    dxf_url: data.dxf_url,
  });
}

async function makeCoupon() {
  setLoading(true, "Kerf coupon üretiliyor…");
  setStatus("Coupon (100 mm bar) kesime hazırlanıyor…");
  try {
    const body = {
      thickness: Number($("box-t").value) || 3,
      material: ($("box-material") && $("box-material").value) || "poplar_3mm",
      machine: ($("box-machine") && $("box-machine").value) || "payas_workshop",
    };
    if ($("box-burn") && $("box-burn").value !== "") body.burn = Number($("box-burn").value);
    const { data } = await api("/api/studio/coupon", { method: "POST", body: JSON.stringify(body) });
    paintExports(data);
    if (!data.success) {
      setStatus((data.look_again || []).join(" ") || "Coupon üretilemedi.", "bad");
      return;
    }
    if (data.file_id) {
      history.replaceState(null, "", "/studio?file=" + encodeURIComponent(data.file_id));
    }
    $("cal-note").textContent =
      "Coupon hazır — kes, 100 mm çubuğu ölç, mm gir, kaydet. " + ((data.look_again || [])[0] || "");
    setStatus(data.file_id ? "Coupon SVG hazır — indir / kes / ölç." : "Coupon üretildi.", "ok");
    if (data.export_allowed !== false && data.file_id) {
      const a = document.createElement("a");
      a.href = data.svg_url || ("/files/" + encodeURIComponent(data.file_id) + "?download=1");
      a.download = data.file_id;
      a.rel = "noopener";
      document.body.appendChild(a);
      a.click();
      a.remove();
    }
  } finally {
    setLoading(false);
  }
}

async function loadCalibrations() {
  const { data } = await api("/api/studio/calibrate");
  const list = $("cal-list");
  if (!list) return;
  list.innerHTML = "";
  const rows = (data && data.rows) || [];
  if (!rows.length) {
    const li = document.createElement("li");
    li.textContent = "Kayıt yok — coupon kesip ölçülen çubuğu gir.";
    list.appendChild(li);
    return;
  }
  rows.slice().reverse().forEach((r) => {
    const li = document.createElement("li");
    li.innerHTML = "<strong>" + (r.material || "?") + "</strong> @ " + (r.machine || "?")
      + "<span class=\"sub\">bar " + (r.measured_bar_mm != null ? r.measured_bar_mm : "?")
      + " mm → burn " + (r.burn != null ? r.burn : "?") + " · " + (r.at || "") + "</span>";
    li.onclick = () => {
      if (r.burn != null && $("box-burn")) $("box-burn").value = String(r.burn);
      if (r.material && $("box-material")) $("box-material").value = r.material;
      if (r.machine && $("box-machine")) $("box-machine").value = r.machine;
      state._calBurn = r.burn;
      setStatus("Kalibrasyon seçildi — burn " + r.burn + " mm (fiziksel dry-fit NOT_VERIFIED).", "ok");
    };
    list.appendChild(li);
  });
}

async function saveCalibration() {
  const measured = Number(($("cal-bar") && $("cal-bar").value) || "");
  if (!(measured >= 96 && measured <= 104)) {
    setStatus("Ölçülen çubuk 96–104 mm arası olmalı.", "bad");
    return;
  }
  const body = {
    measured_bar_mm: measured,
    material: ($("box-material") && $("box-material").value) || "poplar_3mm",
    machine: ($("box-machine") && $("box-machine").value) || "payas_workshop",
  };
  const { data } = await api("/api/studio/calibrate", { method: "POST", body: JSON.stringify(body) });
  if (!data.success) {
    setStatus((data.look_again || []).join(" ") || "Kalibrasyon kaydedilmedi.", "bad");
    await loadCalibrations();
    return;
  }
  state._calBurn = data.suggested_burn;
  if (data.suggested_burn != null) {
    $("cal-note").textContent = "Önerilen burn " + data.suggested_burn + " mm — «Burn’u kutuya uygula».";
  }
  setStatus((data.look_again || [])[0] || "Kalibrasyon kaydedildi.", "ok");
  await loadCalibrations();
}

function applyCalibrationBurn() {
  const burn = state._calBurn;
  if (burn == null || burn === "") {
    setStatus("Önce ölçüm kaydet veya listeden kalibrasyon seç.", "bad");
    return;
  }
  pushUndo();
  $("box-burn").value = String(burn);
  scheduleRebuild(true);
  setStatus("Burn " + burn + " mm kutu formuna yazıldı — fiziksel fit NOT_VERIFIED.", "ok");
}

async function loadProjectHistory() {
  const list = $("hist-list");
  if (!list) return;
  if (state.histAbort) {
    try { state.histAbort.abort(); } catch (_) { /* ignore */ }
  }
  const ac = new AbortController();
  state.histAbort = ac;
  state.histLoading = true;
  if ($("hist-note")) $("hist-note").textContent = "Yükleniyor…";
  if ($("hist-refresh")) $("hist-refresh").disabled = true;
  try {
    const { data } = await api("/api/studio/projects?limit=80", { signal: ac.signal });
    if (ac.signal.aborted) return;
    list.innerHTML = "";
    const projects = (data && data.projects) || [];
    if (!projects.length) {
      const li = document.createElement("li");
      li.textContent = "Proje yok.";
      list.appendChild(li);
      if ($("hist-note")) $("hist-note").textContent = "«Kaydet ve indir» sonrası burada görünür.";
      return;
    }
    projects.forEach((p) => {
      const latest = p.latest || {};
      const li = document.createElement("li");
      li.innerHTML = "<strong>" + (p.name || p.id) + "</strong>"
        + "<span class=\"sub\">v" + (latest.n || p.versions || "?")
        + " · " + (latest.final_status || "—")
        + " · " + (p.updated || "")
        + (latest.file_id ? (" · " + latest.file_id) : "") + "</span>";
      li.onclick = () => {
        const fid = latest.file_id;
        if (!fid) {
          setStatus("Bu sürümde file_id yok.", "bad");
          return;
        }
        history.replaceState(null, "", "/studio?file=" + encodeURIComponent(fid));
        loadFile(fid).catch((e) => setStatus(String(e), "bad"));
      };
      list.appendChild(li);
    });
    if ($("hist-note")) {
      $("hist-note").textContent = projects.length + " son proje (limit 80) — tıkla = 3D aç.";
    }
  } catch (err) {
    if (ac.signal.aborted || (err && err.name === "AbortError")) return;
    setStatus(String(err), "bad");
    if ($("hist-note")) $("hist-note").textContent = "Geçmiş yüklenemedi.";
  } finally {
    if (state.histAbort === ac) state.histAbort = null;
    state.histLoading = false;
    if ($("hist-refresh")) $("hist-refresh").disabled = false;
  }
}

async function loadProfiles() {
  try {
    const { data } = await api("/api/studio/profiles");
    const mats = (data && data.materials) || [];
    const macs = (data && data.machines) || [];
    const matEl = $("box-material");
    const macEl = $("box-machine");
    if (matEl && mats.length) {
      const cur = matEl.value;
      matEl.innerHTML = "";
      mats.forEach((m) => {
        const opt = document.createElement("option");
        opt.value = m.id;
        opt.textContent = m.name || m.id;
        opt.dataset.thickness = m.thickness != null ? String(m.thickness) : "";
        opt.dataset.kerf = m.kerf != null ? String(m.kerf) : "";
        matEl.appendChild(opt);
      });
      matEl.value = mats.some((m) => m.id === cur) ? cur : (mats[0].id || "poplar_3mm");
    }
    if (macEl && macs.length) {
      const cur = macEl.value;
      macEl.innerHTML = "";
      macs.forEach((m) => {
        const opt = document.createElement("option");
        opt.value = m.id;
        opt.textContent = (m.name || m.id)
          + (m.bed_w && m.bed_h ? (" · " + m.bed_w + "×" + m.bed_h) : "");
        if (m.gap_mm != null) opt.dataset.gap = String(m.gap_mm);
        macEl.appendChild(opt);
      });
      macEl.value = macs.some((m) => m.id === cur) ? cur : (macs[0].id || "payas_workshop");
    }
  } catch (_) {
    /* keep hardcoded options */
  }
}

function onMaterialChange() {
  const matEl = $("box-material");
  if (!matEl) return;
  const opt = matEl.selectedOptions && matEl.selectedOptions[0];
  if (opt && opt.dataset.thickness && $("box-t")) {
    $("box-t").value = opt.dataset.thickness;
  }
  // Kerf suggestion only — never invent verified; leave burn empty unless user sets it.
  if (opt && opt.dataset.kerf) {
    setStatus("Profil kerf önerisi " + opt.dataset.kerf + " mm — ölçmeden burn alanına yazma; fiziksel NOT_VERIFIED.", "ok");
  }
  pushUndo();
  scheduleRebuild(true);
}

function onMachineChange() {
  const macEl = $("box-machine");
  if (!macEl) return;
  const opt = macEl.selectedOptions && macEl.selectedOptions[0];
  if (opt && opt.dataset.gap && $("nest-gap")) {
    $("nest-gap").value = opt.dataset.gap;
  }
  pushUndo();
  scheduleRebuild(true);
}

async function boot() {
  buildScene();
  wireUi();
  await loadProfiles();
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
