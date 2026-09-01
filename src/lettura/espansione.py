"""Giudica quanto un archivio DICHIARA di diventare, prima di aprirlo."""
from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass


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


def _dichiarato(data: bytes) -> int | None:
    """`None` se non e' uno zip giudicabile."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
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
    data: bytes, *, tetto_bytes: int, rapporto_sospetto: float = 100
) -> Esito:
    dichiarato = _dichiarato(data)
    if dichiarato is None:
        return Esito(True, None, None, None)
    rapporto = dichiarato / max(len(data), 1)
    if dichiarato <= tetto_bytes:
        return Esito(True, None, dichiarato, rapporto)
    motivo = "ostile" if rapporto > rapporto_sospetto else "troppo_grande"
    return Esito(False, motivo, dichiarato, rapporto)
