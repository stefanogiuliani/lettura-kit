"""Funzioni che il PROCESSO FIGLIO importa per conto suo.

Stanno in un modulo a parte, e non nel file di test, perche' il figlio e' un processo
NUOVO: non eredita niente: ne' le closure, ne' i monkeypatch, ne' lo stato di pytest.
Puo' solo importare. E' il vincolo che decide l'API.
"""


def raddoppia(n: int) -> int:
    return n * 2


def divora(mb: int) -> int:
    """Alloca `mb` megabyte e li tiene: serve a far sfondare il tetto al figlio."""
    zavorra = bytearray(mb * 1024 * 1024)
    return len(zavorra)


def esplode(_):
    """Un guasto qualunque, che NON e' la memoria."""
    raise ValueError("la colonna 'Importo' non c'e'")
