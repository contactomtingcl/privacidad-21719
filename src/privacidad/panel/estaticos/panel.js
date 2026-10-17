// Panel del delegado: mejoras progresivas. Sin este archivo todo funciona igual (formularios y
// enlaces normales); con él, los relojes avanzan solos, el tema se recuerda y la huella se copia.
(function () {
  "use strict";

  document.documentElement.classList.add("js-listo");

  function dos(n) { return (n < 10 ? "0" : "") + n; }

  // Relojes: elementos con data-vence (ISO 8601). Si además tienen data-total (segundos), el
  // anillo [data-anillo] se vacía en proporción al tiempo que queda.
  function actualizarRelojes() {
    var ahora = Date.now();
    document.querySelectorAll("[data-vence]").forEach(function (el) {
      var vence = Date.parse(el.getAttribute("data-vence"));
      if (isNaN(vence)) { return; }
      var resta = Math.max(0, Math.floor((vence - ahora) / 1000));
      var h = Math.floor(resta / 3600), m = Math.floor((resta % 3600) / 60), s = resta % 60;
      var lectura = el.querySelector("[data-lectura]");
      if (lectura) {
        lectura.textContent = resta === 0 ? "Vencido" :
          (h >= 48 ? Math.floor(h / 24) + " días" : h + ":" + dos(m) + ":" + dos(s));
      }
      var anillo = el.querySelector("[data-anillo]");
      var total = parseFloat(el.getAttribute("data-total") || "0");
      if (anillo && total > 0) {
        var largo = parseFloat(anillo.getAttribute("data-largo"));
        anillo.setAttribute("stroke-dasharray", (largo * Math.min(1, resta / total)).toFixed(1) + " " + largo);
      }
    });
  }

  function cambiarTema() {
    var actual = document.documentElement.getAttribute("data-tema") === "claro" ? "claro" : "oscuro";
    var nuevo = actual === "claro" ? "oscuro" : "claro";
    document.documentElement.setAttribute("data-tema", nuevo);
    try { window.localStorage.setItem("panel-tema", nuevo); } catch (e) { /* sin almacenamiento */ }
    rotularTema();
  }

  // El botón de tema (en el menú lateral) dice lo que hará según el tema actual.
  function rotularTema() {
    var boton = document.querySelector("[data-cambiar-tema]");
    if (!boton) { return; }
    var claro = document.documentElement.getAttribute("data-tema") === "claro";
    var texto = boton.querySelector("[data-tema-texto]");
    if (texto) { texto.textContent = claro ? "Usar tema oscuro" : "Usar tema claro"; }
  }

  document.addEventListener("click", function (evento) {
    var menu = evento.target.closest("[data-menu]");
    if (menu) {
      var nav = menu.closest(".menu");
      var abierto = nav.classList.toggle("abierto");
      menu.setAttribute("aria-expanded", abierto ? "true" : "false");
      menu.textContent = abierto ? "Cerrar menú" : "Menú";
      return;
    }
    var objetivo = evento.target.closest("[data-cambiar-tema], [data-copiar], [data-imprimir]");
    if (!objetivo) { return; }
    if (objetivo.hasAttribute("data-cambiar-tema")) { cambiarTema(); return; }
    if (objetivo.hasAttribute("data-imprimir")) { window.print(); return; }
    var texto = objetivo.getAttribute("data-copiar");
    if (navigator.clipboard) {
      navigator.clipboard.writeText(texto).then(function () {
        objetivo.textContent = objetivo.getAttribute("data-copiado") || "Huella copiada";
      }, function () { /* sin permiso: queda visible para copiarla a mano */ });
    }
  });

  rotularTema();

  actualizarRelojes();
  window.setInterval(actualizarRelojes, 1000);
})();
