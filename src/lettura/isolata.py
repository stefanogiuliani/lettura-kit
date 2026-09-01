"""Esegue un lavoro in un PROCESSO FIGLIO, per non morire insieme a lui.

La guardia sull'espansione ferma le forme che sappiamo riconoscere. Questo modulo e'
l'altra meta': regge cio' che non abbiamo previsto — e contro l'ignoto non serve una
regola piu' furba, serve che morire non costi l'app.

Il caso reale che lo giustifica: una cache per pagina dentro una libreria di lettura
PDF, che nessuno aveva immaginato e che non si sarebbe fermata con una regola in piu'.

Due proprieta' che la sola guardia non da':
  · il tetto dell'app non e' mai la cosa che cede: il caso peggiore diventa un errore
    su un caricamento;
  · la memoria torna. Dopo una lettura pesante in-process la RSS non scende piu';
    con il figlio la rende il sistema operativo.
"""
from __future__ import annotations

import pickle
import subprocess
import sys
import threading
import time


class MemoriaEsaurita(RuntimeError):
    """Il figlio ha sfondato il tetto. E' un'AFFERMAZIONE, non il ripiego per ogni
    morte: se lo fosse, manderebbe a spezzare un file che non ha niente di grande."""


class LetturaFallita(RuntimeError):
    """Il figlio e' morto per un motivo suo. Porta con se' il perche'."""


# Il figlio e' un processo NUOVO, non un fork: non eredita ne' il loop asyncio, ne' le
# connessioni, ne' i monkeypatch di un test. Puo' solo IMPORTARE — ed e' il vincolo che
# decide l'API: il lavoro si passa come "modulo:funzione", non come callable.
_AVVIO = """
import pickle, sys, importlib
istruzioni = pickle.load(sys.stdin.buffer)
try:
    import resource
    mb = istruzioni["limite_mb"] * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (mb, mb))
except Exception:
    # Su macOS `setrlimit` risponde «current limit exceeds maximum limit» e non si puo'
    # impostare. Non e' un guasto: e' il motivo per cui i tetti sono DUE. Qui resta la
    # sorveglianza del padre, che funziona ovunque.
    pass
sys.path[:0] = istruzioni["path"]
modulo, funzione = istruzioni["bersaglio"].split(":")
esito = getattr(importlib.import_module(modulo), funzione)(*istruzioni["args"])
sys.stdout.buffer.write(pickle.dumps(esito))
"""

_CAMPIONE_S = 0.02


def _rss_mb(pid: int) -> float:
    """RSS via `ps`, che c'e' su macOS e su Linux. Zero dipendenze di proposito: questa
    libreria entra in dieci app, e ognuna paga cio' che si tira dietro."""
    try:
        out = subprocess.run(["ps", "-o", "rss=", "-p", str(pid)],
                             capture_output=True, text=True, timeout=5).stdout.strip()
        return int(out) / 1024 if out else 0.0
    except Exception:
        return 0.0


def esegui_isolato(bersaglio: str, *args, limite_mb: int):
    """Chiama `modulo:funzione` in un figlio con un tetto di memoria suo.

    ⚠️ I due tetti non si coprono a vicenda, e servono entrambi:
      · `RLIMIT_AS` e' duro e istantaneo, ma vive solo dove il sistema lo concede;
      · la sorveglianza sulla RSS funziona ovunque ma CAMPIONA, quindi una singola
        allocazione enorme la scavalcherebbe di colpo.
    """
    p = subprocess.Popen(
        [sys.executable, "-c", _AVVIO],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    sfondato = threading.Event()

    def sorveglia() -> None:
        while p.poll() is None:
            if _rss_mb(p.pid) > limite_mb:
                sfondato.set()
                p.kill()
                return
            time.sleep(_CAMPIONE_S)

    guardia = threading.Thread(target=sorveglia, daemon=True)
    guardia.start()
    uscita, errore = p.communicate(
        pickle.dumps({"bersaglio": bersaglio, "args": args,
                      "path": list(sys.path), "limite_mb": limite_mb})
    )
    guardia.join(timeout=1)

    # ⚠️ L'ordine conta. «Memoria» si dice solo quando lo si SA: o l'ha visto la
    # sorveglianza, o il figlio e' stato ucciso da un segnale (il SIGKILL dell'OOM
    # killer, che non lascia traccia applicativa). Tutto il resto e' un guasto suo, e
    # va riportato con il suo perche' — non travestito da problema di taglia.
    if sfondato.is_set() or p.returncode is not None and p.returncode < 0:
        raise MemoriaEsaurita(
            f"{bersaglio} ha superato il tetto di {limite_mb} MB e il processo di "
            "lettura e' stato fermato. Il chiamante e' vivo: decide lui cosa dire."
        )
    if p.returncode != 0 or not uscita:
        raise LetturaFallita(
            f"{bersaglio} non e' arrivato in fondo (uscita {p.returncode}). "
            f"{errore.decode(errors='replace').strip()[-500:]}"
        )
    return pickle.loads(uscita)
