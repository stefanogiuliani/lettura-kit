"""Giudica quanto un archivio DICHIARA di diventare, prima di aprirlo."""
from __future__ import annotations

import io
import os
import zipfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Esito:
    """Il verdetto. `motivo` e' `None` quando `ok`.

    La libreria NON scrive il messaggio: dice cos'e' successo, e chi chiama sceglie
    cosa dire — perche' la frase giusta dipende dal suo flusso (chi ha mandato il
    file, dove resta, a chi si richiede), non dal formato.
    """

    ok: bool
    motivo: str | None
    dichiarato: int | None
    rapporto: float | None


def _sorgente(origine):
    """(cosa dare a `ZipFile`, dimensione compressa). Solleva se non so cos'e'.

    ⚠️ Solleva di proposito, e la distinzione e' importante: un file che NON e' uno zip
    passa (sara' il parser a dire che non e' riconosciuto), ma un ARGOMENTO che non so
    leggere e' un errore di chi chiama. Prima che questa funzione esistesse, un `Path`
    finiva nell'except largo e la guardia rispondeva «tutto bene» su una bomba: un
    cancello che si apre quando non capisce e' peggio di nessun cancello.
    """
    if isinstance(origine, (bytes, bytearray, memoryview)):
        return io.BytesIO(bytes(origine)), len(origine)
    if isinstance(origine, (str, Path)):
        return Path(origine), os.path.getsize(origine)
    raise TypeError(f"non so leggere {type(origine).__name__}: servono bytes o un percorso")


def _dichiarato(sorgente) -> int | None:
    """`None` se non e' uno zip giudicabile."""
    try:
        with zipfile.ZipFile(sorgente) as z:
            return sum(i.file_size for i in z.infolist())
    except MemoryError:
        # ⛔ `MemoryError` E' sottoclasse di `Exception`, quindi l'except qui sotto se
        # lo prenderebbe: sarebbe lo stesso difetto che questa guardia esiste per
        # evitare, rifatto dentro la guardia. Chi chiama deve poter distinguere
        # «non ci sta in memoria» da «non e' uno zip»: sono due frasi diverse per chi
        # ha mandato il file. Risale.
        raise
    except Exception:
        # Largo di proposito. Fuzzando uno zip valido da 119 byte, i 952 flip di un
        # bit danno 283 `BadZipFile` e 5 `NotImplementedError` («zip file version
        # 8.4»). Elencare i tipi noti significa scoprire il prossimo in produzione, e
        # il prezzo e' asimmetrico: non saper leggere la directory centrale vuol dire
        # non saper giudicare, e chi non sa giudicare lascia passare al parser — non
        # muore.
        return None


def controlla_espansione(
    origine: bytes | str | Path, *, tetto_bytes: int, rapporto_sospetto: float = 100
) -> Esito:
    """`origine` sono i byte, oppure un percorso.

    Il percorso non e' una comodita': chi riceve upload li scrive in streaming e non
    tiene mai il file intero in RAM — che e' il rischio da cui questa guardia protegge.
    Chiedergli i `bytes` significherebbe fargli correre il rischio per poterlo misurare.
    La directory centrale si legge senza decomprimere, quindi anche su una share di rete
    costa quanto le voci, non quanto il file.
    """
    sorgente, compressi = _sorgente(origine)
    dichiarato = _dichiarato(sorgente)
    if dichiarato is None:
        return Esito(True, None, None, None)
    rapporto = dichiarato / max(compressi, 1)
    if dichiarato <= tetto_bytes:
        return Esito(True, None, dichiarato, rapporto)
    motivo = "ostile" if rapporto > rapporto_sospetto else "troppo_grande"
    return Esito(False, motivo, dichiarato, rapporto)
