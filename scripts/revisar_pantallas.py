# ruff: noqa: E501 - el JavaScript de la medición va en líneas largas
"""Revisión automática de las pantallas de la demo: estado HTTP, errores de JavaScript,
desplazamiento lateral y contraste de cada texto (WCAG AA: 4,5:1, o 3:1 en texto grande).

Recorre todas las pantallas en cuatro vistas (computador y celular, tema claro y oscuro).
Requiere Playwright con Chromium y la demo corriendo:

    python -m privacidad.canal servir --demo --datos casos-demo --puerto 8080
    python scripts/revisar_pantallas.py http://localhost:8080 capturas/

Escribe una captura por pantalla e `informe.json`, y lista en pantalla solo lo que falla.
Usado en la revisión del 17 de octubre de 2026.
"""

import json
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

B = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://localhost:8080"
OUT = sys.argv[2] if len(sys.argv) > 2 else "capturas"
Path(OUT).mkdir(parents=True, exist_ok=True)
CONTRASTE_JS = r"""
() => {
  function rgb(s){const m=s.match(/rgba?\(([^)]+)\)/); if(!m) return null; const p=m[1].split(',').map(x=>parseFloat(x)); return {r:p[0],g:p[1],b:p[2],a:p.length>3?p[3]:1};}
  function lum(c){const f=v=>{v/=255;return v<=0.03928?v/12.92:Math.pow((v+0.055)/1.055,2.4)}; return 0.2126*f(c.r)+0.7152*f(c.g)+0.0722*f(c.b);}
  function blend(top,bot){const a=top.a; return {r:top.r*a+bot.r*(1-a),g:top.g*a+bot.g*(1-a),b:top.b*a+bot.b*(1-a),a:1};}
  function fondo(el){const capas=[]; let e=el; while(e){const cs=getComputedStyle(e); const c=rgb(cs.backgroundColor); if(cs.backgroundImage && cs.backgroundImage!=='none') return {img:true}; if(c&&c.a>0){capas.push(c); if(c.a>=1) break;} e=e.parentElement;} let base={r:255,g:255,b:255,a:1}; if(capas.length && capas[capas.length-1].a>=1) base=capas.pop(); for(let i=capas.length-1;i>=0;i--) base=blend(capas[i],base); return base;}
  const fallos=[]; const vistos=new Set();
  const walker=document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let n; while(n=walker.nextNode()){
    const t=n.textContent.trim(); if(!t) continue; const el=n.parentElement; if(!el) continue;
    const r=el.getBoundingClientRect(); if(r.width===0||r.height===0) continue;
    const cs=getComputedStyle(el); if(cs.visibility==='hidden'||parseFloat(cs.opacity)===0) continue;
    if(el.closest('[disabled],[aria-hidden="true"],.sr-only,.visually-hidden')) continue;
    let fg=rgb(cs.color); const bg=fondo(el); if(!fg||bg.img) continue;
    if(fg.a<1) fg=blend(fg,bg);
    const L1=lum(fg),L2=lum(bg); const ratio=(Math.max(L1,L2)+0.05)/(Math.min(L1,L2)+0.05);
    const px=parseFloat(cs.fontSize), w=parseInt(cs.fontWeight)||400; const grande=px>=24||(px>=18.66&&w>=700);
    const min=grande?3:4.5;
    if(ratio<min){const k=cs.color+'|'+JSON.stringify(bg)+'|'+el.tagName+'.'+el.className; if(vistos.has(k)) continue; vistos.add(k);
      fallos.push({texto:t.slice(0,50), ratio:Math.round(ratio*100)/100, min, color:cs.color, fondo:`rgb(${Math.round(bg.r)},${Math.round(bg.g)},${Math.round(bg.b)})`, el:el.tagName.toLowerCase()+(el.className?'.'+String(el.className).split(' ').join('.'):''), px});}
  }
  return {fallos, ancho: document.documentElement.scrollWidth, vista: document.documentElement.clientWidth};
}
"""
informe = []


def revisar(pg, url, nombre, tag):
    errores = []
    pg.on("pageerror", lambda e: errores.append(str(e)))
    r = pg.goto(url)
    pg.wait_for_timeout(250)
    res = pg.evaluate(CONTRASTE_JS)
    estado = r.status if r else None
    informe.append(
        {
            "pagina": nombre,
            "vista": tag,
            "estado": estado,
            "desborde": res["ancho"] > res["vista"] + 1,
            "ancho": res["ancho"],
            "fallos": res["fallos"],
            "errores_js": errores,
        }
    )
    pg.screenshot(path=f"{OUT}/{tag}-{nombre}.png", full_page=True)


with sync_playwright() as p:
    b = p.chromium.launch()
    for tag, vp, tema in [
        ("pc-oscuro", {"width": 1280, "height": 900}, "oscuro"),
        ("pc-claro", {"width": 1280, "height": 900}, "claro"),
        ("cel-claro", {"width": 390, "height": 844}, "claro"),
        ("cel-oscuro", {"width": 390, "height": 844}, "oscuro"),
    ]:
        ctx = b.new_context(viewport=vp)
        ctx.add_init_script(f"try{{localStorage.setItem('panel-tema','{tema}')}}catch(e){{}}")
        pg = ctx.new_page()
        mensajes = []
        pg.on("console", lambda m: mensajes.append(m.text) if m.type == "error" else None)
        pg.goto(B + "/panel/")
        html = pg.content()
        casos = list(dict.fromkeys(re.findall(r'/panel/caso/([A-Za-z0-9_-]+)"', html)))
        paginas = [
            ("bandeja", "/panel/"),
            ("canal", "/panel/canal"),
            ("simulador", "/panel/simulador"),
            ("proveedores", "/panel/proveedores"),
            ("inventario", "/panel/inventario"),
            ("evidencia", "/panel/evidencia"),
        ]
        for i, c in enumerate(casos):
            paginas.append((f"caso{i}", f"/panel/caso/{c}"))
        if tag == "pc-oscuro" or tag == "cel-claro":
            for i, c in enumerate(casos[:3]):
                paginas += [
                    (f"caso{i}-agencia", f"/panel/caso/{c}/borrador/agencia"),
                    (f"caso{i}-anci", f"/panel/caso/{c}/borrador/anci"),
                ]
        pg.goto(B + "/panel/inventario")
        inv = list(
            dict.fromkeys(re.findall(r'/panel/inventario/([A-Za-z0-9_-]{8,})"', pg.content()))
        )
        for i, a in enumerate(inv):
            paginas.append((f"actividad{i}", f"/panel/inventario/{a}"))
        pg.goto(B + "/panel/canal")
        enlaces = list(
            dict.fromkeys(re.findall(r'href="(https?://[^"]*/canal/[^"]+)"', pg.content()))
        )
        pg.goto(B + "/panel/proveedores")
        prov = list(
            dict.fromkeys(re.findall(r'href="(https?://[^"]*/proveedor/[^"]+)"', pg.content()))
        )
        for nombre, ruta in paginas:
            revisar(pg, B + ruta, nombre, tag)
        for i, e in enumerate(enlaces[:1]):
            revisar(
                pg,
                e.replace("https://", "http://").split("://", 1)[0] + "://" + e.split("://", 1)[1],
                f"formulario{i}",
                tag,
            )
        for i, e in enumerate(prov[:1]):
            revisar(pg, e, f"proveedor{i}", tag)
        informe.append(
            {
                "vista": tag,
                "consola": mensajes[:20],
                "casos": len(casos),
                "enlaces": enlaces[:1],
                "prov": prov[:1],
            }
        )
        ctx.close()
    b.close()
json.dump(informe, open(f"{OUT}/informe.json", "w"), ensure_ascii=False, indent=1)
for x in informe:
    if "pagina" in x:
        if x["estado"] != 200 or x["desborde"] or x["fallos"] or x["errores_js"]:
            print(
                x["vista"],
                x["pagina"],
                x["estado"],
                "desborde" if x["desborde"] else "",
                x["ancho"],
                len(x["fallos"]),
                x["errores_js"][:2],
            )
    else:
        print("==", x)
