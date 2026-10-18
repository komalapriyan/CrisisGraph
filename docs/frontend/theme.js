// system | light | dark. Applied before first paint (loaded in <head>).
(function () {
  var K = "cg_theme", d = document.documentElement;
  function get() { try { return localStorage.getItem(K) || "system"; } catch (e) { return "system"; } }
  window.setTheme = function (m) { try { localStorage.setItem(K, m); } catch (e) {} d.dataset.theme = m; label(); dispatchEvent(new Event("themechange")); };
  function label() { var b = document.getElementById("theme"); if (b) b.textContent = "Theme: " + get(); }
  d.dataset.theme = get();
  document.addEventListener("DOMContentLoaded", function () {
    var b = document.getElementById("theme"); if (!b) return; label();
    b.onclick = function () { var o = ["system", "light", "dark"]; setTheme(o[(o.indexOf(get()) + 1) % 3]); };
  });
})();
