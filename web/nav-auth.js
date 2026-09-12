(function () {
  const signin = document.getElementById("nav-signin");
  const google = document.getElementById("nav-google");
  const midGoogle = document.getElementById("mid-google");
  const connect = document.getElementById("nav-connect");
  const profile = document.getElementById("nav-profile");
  if (!profile) return;
  const lang = localStorage.getItem("lmcp_lang") || "tr";
  const jobs = lang === "en" ? "jobs" : "iş";
  fetch("/api/account", { credentials: "same-origin" })
    .then(function (r) { return r.json(); })
    .then(function (data) {
      if (!data || !data.user) return;
      if (signin) signin.classList.add("hide");
      if (google) google.classList.add("hide");
      if (midGoogle) midGoogle.classList.add("hide");
      if (connect) connect.classList.add("hide");
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
