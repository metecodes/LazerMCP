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
  if (leaf.includes("divider")) return "other";
  return "other";
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
  if (!state.ghostLid || !view.root) return;
  view.root.remove(state.ghostLid);
  state.ghostLid.traverse((obj) => {
    if (obj.geometry) obj.geometry.dispose();
  });
  state.ghostLid = null;
}

function showOptimisticLid() {
  clearGhostLid();
  const lid = ($("box-lid") && $("box-lid").value) || "open";
  if (lid === "open") return;
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
      color: 0x3d8bfd,
      transparent: true,
      opacity: 0.45,
      roughness: 0.7,
      metalness: 0.05,
      depthWrite: false,
    });
  }
  const doors = lid === "double_door" ? 2 : 1;
  const group = new THREE.Group();
  group.userData.ghost = true;
  if (doors === 1) {
    const geom = new THREE.BoxGeometry(xi, yi, t);
    const mesh = new THREE.Mesh(geom, state.woodGhost);
    mesh.position.set(xi / 2, yi / 2, hi + t / 2);
    group.add(mesh);
  } else {
    const half = (xi - t) / 2;
    const left = new THREE.Mesh(new THREE.BoxGeometry(half, yi, t), state.woodGhost);
    left.position.set(half / 2, yi / 2, hi + t / 2);
    const right = new THREE.Mesh(new THREE.BoxGeometry(half, yi, t), state.woodGhost);
    right.position.set(half + t + half / 2, yi / 2, hi + t / 2);
    group.add(left);
    group.add(right);
  }
  // Align ghost with typical assembly origin (bottom front-left-ish)
  group.position.set(-xi / 2, -yi / 2, 0);
  view.root.add(group);
  state.ghostLid = group;
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
  canvas.addEventListener("pointerdown", (ev) => {
    if (ev.button !== 0) return;
    const rect = canvas.getBoundingClientRect();
    mouse.x = ((ev.clientX - rect.left) / rect.width) * 2 - 1;
    mouse.y = -((ev.clientY - rect.top) / rect.height) * 2 + 1;
    ray.setFromCamera(mouse, camera);
    const hits = ray.intersectObjects(state.meshes, true);
    if (!hits.length) {
      selectPanel(null);
      hideDimPop();
      return;
    }
    let obj = hits[0].object;
    while (obj && !obj.userData.partId) obj = obj.parent;
    if (obj) {
      selectPanel(obj);
      openDimPop(obj, ev.clientX, ev.clientY);
    }
  });

  function frame() {
    controls.update();
    renderer.render(scene, camera);
    requestAnimationFrame(frame);
  }
  frame();
}

function clearMeshes() {
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
  fitCamera();
  setStatus("Zoom ile incele. Panele tıkla. Ölçü → yalnız temas eden paneller yenilenir; kalınlık sabit.", "ok");
  $("sum-panels").textContent = String(panels.length);
  $("sum-t").textContent = thickness + " mm";
  $("sum-val").textContent = assembly.validation_state || "—";
  $("sum-sel").textContent = "—";
  $("sum-dims").textContent = "—";
  $("sum-note").textContent = assembly.note || "";
  if ($("box-t") && thickness) $("box-t").value = String(thickness);
  if ($("stl-h") && thickness) $("stl-h").value = String(thickness);
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

function paintExports(data) {
  const fileId = data.file_id || (data.assembly && data.assembly.file_id);
  state.fileId = fileId;
  $("sum-file").textContent = fileId || "—";
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
  const delay = immediate ? 80 : 280;
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
  const usd = (mcp.usd && mcp.usd.total != null) ? mcp.usd.total : null;
  const tok = (mcp.tokens && mcp.tokens.input_total) || 0;
  const q = (studio.quota) || {};
  el.textContent =
    "Stüdyo AI API: $0 (yerel). " +
    "Aynı prompt MCP/" + (mcp.model_label || "model") + " ≈ $" +
    (usd != null ? Number(usd).toFixed(5) : "?") +
    " (~" + tok + " in tok). " +
    "Kota: " + (q.used != null ? q.used + "/" + (q.limit || "?") : "—") +
    " · " + (data.recommendation || "");
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

function wireUi() {
  document.querySelectorAll(".tabs button").forEach((btn) => {
    btn.onclick = () => {
      document.querySelectorAll(".tabs button").forEach((b) => b.classList.remove("on"));
      btn.classList.add("on");
      document.querySelectorAll(".pane").forEach((p) => p.classList.remove("on"));
      $("pane-" + btn.dataset.tab).classList.add("on");
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
    el.addEventListener("change", scheduleRebuild);
    el.addEventListener("input", () => {
      if (id === "box-burn") return;
      scheduleRebuild();
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
  if ($("ai-file")) $("ai-file").onchange = () => { onAiFileChange().catch((e) => setStatus(String(e), "bad")); };
  if ($("ai-cost-btn")) $("ai-cost-btn").onclick = () => estimateAiCost().catch((e) => setStatus(String(e), "bad"));
  if ($("ai-prompt")) {
    $("ai-prompt").addEventListener("input", scheduleAiCost);
  }
  if ($("ai-model")) $("ai-model").onchange = scheduleAiCost;
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
