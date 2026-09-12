(function () {
  const signin = document.getElementById("nav-signin");
  const google = document.getElementById("nav-google");
  const midGoogle = document.getElementById("mid-google");
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
      profile.classList.remove("hide");
      const who = profile.querySelector(".who");
      const use = profile.querySelector(".use");
      if (who) who.textContent = data.user.email || data.user.name || "hesap";
      const n = (data.usage && (data.usage.month || data.usage.total)) || 0;
      if (use) use.textContent = n + " " + jobs;
    })
    .catch(function () {});
})();
