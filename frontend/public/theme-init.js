(function () {
  var stored = null;
  try {
    stored = localStorage.getItem("ragassist-theme");
  } catch (e) {}
  var dark = stored === "dark" || (stored !== "light" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
})();
