(function () {
  const signin = document.getElementById("nav-signin");
  const google = document.getElementById("nav-google");
  const midGoogle = document.getElementById("mid-google");
  const connect = document.getElementById("nav-connect");
  const profile = document.getElementById("nav-profile");
  const signinNote = document.getElementById("signin-note");
  let lang = "tr";
  try { lang = localStorage.getItem("lmcp_lang") || "tr"; } catch (_) {}
  let busy = null;
  function resetSignin() {
    if (!busy) return;
    busy.removeAttribute("aria-busy");
    busy.removeAttribute("aria-disabled");
    busy = null;
  }
  window.addEventListener("pageshow", resetSignin);
  document.addEventListener("click", async function (event) {
    const link = event.target.closest("a.btn-google, a#nav-signin, a[data-google-signin], a[href^='/auth/google']");
    if (!link || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    if (busy) return;
    busy = link;
    link.setAttribute("aria-busy", "true");
    link.setAttribute("aria-disabled", "true");
    let note = document.getElementById("signin-feedback");
    if (!note) {
      note = document.createElement("p");
      note.id = "signin-feedback";
      note.setAttribute("role", "status");
      note.setAttribute("aria-live", "polite");
    }
    link.insertAdjacentElement("afterend", note);
    note.textContent = lang === "en" ? "Opening Google…" : "Google açılıyor…";
    const url = new URL(link.href, location.origin);
    const pageNext = ["/account", "/auth/callback"].includes(location.pathname)
      ? new URLSearchParams(location.search).get("next") : "";
    const next = url.searchParams.get("next") || pageNext || "/dashboard";
    const controller = new AbortController();
    const timer = setTimeout(function () { controller.abort(); }, 15000);
    try {
      const response = await fetch("/api/auth/start?next=" + encodeURIComponent(next), {
        credentials: "same-origin", signal: controller.signal
      });
      const data = await response.json();
      if (!response.ok || !data.url) throw new Error("signin");
      location.assign(data.url);
    } catch (_) {
      note.textContent = lang === "en"
        ? "Sign-in could not start. Please try again."
        : "Giriş başlatılamadı. Lütfen tekrar dene.";
      resetSignin();
    } finally { clearTimeout(timer); }
  });
  const jobs = lang === "en" ? "jobs" : "iş";
  fetch("/api/account", { credentials: "same-origin" })
    .then(function (r) { return r.json(); })
    .then(function (data) {
      if (!data || !data.user) return;
      document.body.classList.add("signed-in");
      if (signin) signin.classList.add("hide");
      if (google) google.classList.add("hide");
      if (midGoogle) midGoogle.classList.add("hide");
      if (connect) connect.classList.add("hide");
      if (signinNote) signinNote.classList.add("hide");
      document.querySelectorAll(".guest-only, .btn-google, #google").forEach(function (el) {
        el.classList.add("hide");
      });
      document.querySelectorAll(".signed-only").forEach(function (el) {
        el.classList.remove("hide");
      });
      if (!profile) return;
      profile.classList.remove("hide");
      const email = data.user.email || "";
      const given = String(data.user.name || "").trim();
      const local = (email.split("@")[0] || "hesap").replace(/[._]+/g, " ");
      const label = given && given.indexOf("@") < 0 ? given : local;
      const ava = profile.querySelector(".ava");
      const who = profile.querySelector(".who");
      const use = profile.querySelector(".use");
      if (ava) ava.textContent = label.replace(/[^A-Za-z0-9ğüşöçıİĞÜŞÖÇ]/g, "").slice(0, 2).toUpperCase() || "LM";
      if (who) {
        who.textContent = label;
        who.title = email;
      }
      const n = (data.usage && (data.usage.month || data.usage.total)) || 0;
      if (use) {
        if (n > 0) use.textContent = n + " " + jobs;
        else use.remove();
      }
    })
    .catch(function () {});
})();
