import unittest

from privacidad.ia import costo_usd


class TestCosto(unittest.TestCase):
    def test_haiku_tramo_normal(self):
        self.assertAlmostEqual(costo_usd("claude-haiku-5-5", 100_000, 0), 0.01)
        self.assertAlmostEqual(costo_usd("claude-haiku-5-5", 0, 1_000_000), 0.50)

    def test_haiku_sobre_el_limite(self):
        # Un prompt de más de 100.000 tokens paga la tarifa alta: US$0,50 por millón.
        self.assertAlmostEqual(costo_usd("claude-haiku-5-5", 200_000, 0), 0.10)

    def test_sonnet(self):
        self.assertAlmostEqual(costo_usd("claude-sonnet-5-5", 1000, 500), 0.007)


if __name__ == "__main__":
    unittest.main()


class _ErrorSolicitud(Exception):
    pass


class _APIFalsa:
    """Imita anthropic.Anthropic().messages: rechaza tool_choice forzado una vez."""

    def __init__(self):
        self.llamadas = []
        self.messages = self

    def create(self, **kw):
        self.llamadas.append(kw)
        if "tool_choice" in kw:
            raise _ErrorSolicitud('tool_choice: type "tool" and "any" are not supported')
        from types import SimpleNamespace as N

        bloque = N(type="tool_use", name="x", input={"ok": True})
        return N(model=kw["model"], content=[bloque], usage=N(input_tokens=10, output_tokens=5))


class TestReintentoSinEleccionForzada(unittest.TestCase):
    def test_reintenta_con_instruccion_y_recuerda_el_modelo(self):
        from privacidad.ia.cliente import ClienteIA

        cliente = ClienteIA.__new__(ClienteIA)
        cliente._api = _APIFalsa()
        cliente._registro = None
        cliente._sin_eleccion_forzada = set()
        args = dict(
            modelo="claude-sonnet-5-5",
            sistema="S",
            mensajes=[{"role": "user", "content": "hola"}],
            herramientas=[{"name": "x"}],
            forzar_herramienta="x",
        )
        r = cliente.llamar(**args)
        self.assertEqual(r.bloques_herramienta, [{"nombre": "x", "entrada": {"ok": True}}])
        self.assertIn("«x»", cliente._api.llamadas[1]["system"])
        cliente.llamar(**args)  # la segunda vez ya no intenta forzar
        self.assertEqual(len(cliente._api.llamadas), 3)
