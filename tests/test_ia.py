import unittest

from ora_privacidad.ia import costo_usd


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
