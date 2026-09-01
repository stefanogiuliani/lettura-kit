"""Leggere in un processo figlio con un tetto suo.

Perche' esiste, in una riga: la guardia sull'espansione ferma le forme che sappiamo
riconoscere; questo regge cio' che non abbiamo previsto. Contro l'ignoto non serve
una regola piu' furba — serve che morire non costi l'app.
"""
import pytest

from lettura.isolata import MemoriaEsaurita, esegui_isolato


def test_il_risultato_del_figlio_torna_al_padre():
    assert esegui_isolato("lavori:raddoppia", 21, limite_mb=200) == 42


def test_il_figlio_che_sfonda_il_tetto_non_porta_giu_il_padre():
    """Il caso peggiore diventa un errore tipizzato, non un SIGKILL sull'app.

    ⚠️ Questo test e' PIU' severo su macOS che su Linux, ed e' un bene. `RLIMIT_AS`
    e' duro e istantaneo ma su macOS `setrlimit` risponde «current limit exceeds
    maximum limit» e non si puo' impostare: qui a reggere e' solo la sorveglianza
    sulla RSS. Se passa in sviluppo, il tetto duro su Linux e' in piu', non al posto.
    """
    with pytest.raises(MemoriaEsaurita):
        esegui_isolato("lavori:divora", 600, limite_mb=150)

    # E il padre e' ancora qui: se non lo fosse, questa riga non girerebbe.
    assert esegui_isolato("lavori:raddoppia", 21, limite_mb=200) == 42


def test_un_guasto_qualunque_non_viene_spacciato_per_memoria():
    """⛔ La forma di guasto che questa libreria esiste per non ripetere.

    Se ogni morte del figlio diventa «memoria esaurita», chi riceve il messaggio va a
    spezzare un file che non ha niente di grande — mentre il problema era una colonna
    mancante: un messaggio che manda a cercare nel posto sbagliato. Dire «memoria»
    dev'essere una AFFERMAZIONE, non il ripiego per tutto cio' che non ha funzionato.
    """
    with pytest.raises(Exception) as caduta:
        esegui_isolato("lavori:esplode", 1, limite_mb=200)

    assert not isinstance(caduta.value, MemoriaEsaurita)
