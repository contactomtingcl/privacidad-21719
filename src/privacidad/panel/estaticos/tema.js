// Aplica el tema guardado antes de pintar la página, para que no parpadee.
(function () {
  var tema = null;
  try { tema = window.localStorage.getItem("panel-tema"); } catch (e) { /* almacenamiento bloqueado */ }
  if (tema === "claro" || tema === "oscuro") {
    document.documentElement.setAttribute("data-tema", tema);
  }
})();
