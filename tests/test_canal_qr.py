import sys
import unittest
from unittest import mock
from xml.etree import ElementTree

from privacidad.canal import qr

try:
    import segno
except ImportError:
    segno = None

URL = "https://canal.ejemplo.cl/canal/comercial-los-robles/firma"


@unittest.skipIf(segno is None, "segno no está instalada aquí (sí en GitHub Actions)")
class TestQrConSegno(unittest.TestCase):
    def test_devuelve_un_svg_con_el_titulo_accesible(self):
        svg = qr.svg_qr(URL, "Código QR del canal de Los Robles")
        self.assertIn("<svg", svg)
        self.assertIn("Código QR del canal de Los Robles", svg)

    def test_mismo_enlace_mismo_codigo(self):
        self.assertEqual(qr.svg_qr(URL, "a"), qr.svg_qr(URL, "a"))

    def test_otro_enlace_otro_codigo(self):
        self.assertNotEqual(qr.svg_qr(URL, "a"), qr.svg_qr(URL + "x", "a"))

    def test_es_xml_valido_con_raiz_svg(self):
        raiz = ElementTree.fromstring(qr.svg_qr(URL, "a").encode("utf-8"))
        self.assertTrue(raiz.tag.endswith("svg"))


class TestQrSinSegno(unittest.TestCase):
    def test_se_usa_segno_con_los_parametros_esperados(self):
        falso = mock.MagicMock()
        falso.make_qr.return_value.save.side_effect = lambda salida, **kw: salida.write(b"<svg/>")
        with mock.patch.dict(sys.modules, {"segno": falso}):
            self.assertEqual(qr.svg_qr(URL, "titulo"), "<svg/>")
        falso.make_qr.assert_called_once_with(URL, error="m")
        kwargs = falso.make_qr.return_value.save.call_args.kwargs
        self.assertEqual(kwargs["kind"], "svg")
        self.assertEqual(kwargs["border"], 4)
        self.assertEqual(kwargs["title"], "titulo")

    def test_si_falta_segno_el_mensaje_dice_que_hacer(self):
        with (
            mock.patch.dict(sys.modules, {"segno": None}),
            self.assertRaises(RuntimeError) as ctx,
        ):
            qr.svg_qr(URL, "titulo")
        self.assertIn("pip install", str(ctx.exception))
