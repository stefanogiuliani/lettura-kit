"""La guardia sull'espansione: distinguere «grande» da «fatto per espandersi».

Perche' questa distinzione e' il primo test e non un dettaglio: le due situazioni
chiedono due AZIONI diverse a chi ha ricevuto il file. A un estratto vero troppo
grande si risponde «spezzalo e ricaricalo»; a un file ostile no, si richiede al
mittente. Una guardia che sapesse solo rifiutare manderebbe l'utente a spezzare
una bomba.
"""
import io
import random
import zipfile
from unittest import mock

import pytest

from lettura import espansione

from lettura.espansione import controlla_espansione

TETTO = 1024 * 1024  # 1 MB: in prova i tetti sono piccoli, in produzione sono parametri


def _zip_con(contenuto: bytes) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("dentro.bin", contenuto)
    return buf.getvalue()


def test_distingue_il_file_ostile_da_quello_solo_grande():
    # Due megabyte di zeri: si comprimono quasi a nulla -> rapporto enorme.
    bomba = _zip_con(b"\0" * (2 * TETTO))
    # Due megabyte DAVVERO incomprimibili: dichiarato uguale, ma rapporto ~1x.
    #
    # ⚠️ Il fixture ovvio non funziona, e vale la pena dirlo perche' costa un'ora:
    # `bytes(range(256))` ripetuto SEMBRA casuale ma e' un motivo regolare, e deflate
    # lo comprime 245x — cioe' sopra la soglia dell'ostile. Misurato qui, 01/09/2026:
    #     zeri                  972x
    #     range(256) ripetuto   245x   <- passa per bomba, e non lo e'
    #     random deterministico   1,0x
    # `Random(seed)` tiene il test riproducibile senza dipendere da `os.urandom`.
    grande = _zip_con(random.Random(1).randbytes(2 * TETTO))

    esito_bomba = controlla_espansione(bomba, tetto_bytes=TETTO)
    esito_grande = controlla_espansione(grande, tetto_bytes=TETTO)

    # Nessuno dei due passa: entrambi dichiarano piu' del tetto.
    assert not esito_bomba.ok
    assert not esito_grande.ok

    # Ma il MOTIVO e' diverso, ed e' l'unica cosa che conta qui.
    assert esito_bomba.motivo == "ostile"
    assert esito_grande.motivo == "troppo_grande"


def test_cio_che_non_e_uno_zip_passa_senza_rumore():
    """Un .csv, un .xls vero, un file troncato: qui NON si giudicano.

    Non e' indulgenza: la guardia sa rispondere a «quanto diventa da scompattato»,
    e su un non-zip quella domanda non ha risposta. Dire «rifiutato» qui manderebbe
    l'utente a discutere di dimensioni mentre il problema e' il formato — che e' la
    diagnosi che sa dare il parser, dopo.
    """
    esito = controlla_espansione(b"col1,col2\n1,2\n", tetto_bytes=TETTO)

    assert esito.ok
    assert esito.motivo is None
    assert esito.dichiarato is None


def test_uno_zip_corrotto_in_modo_esotico_non_fa_esplodere_la_guardia():
    """`zipfile` non solleva solo `BadZipFile`.

    Con la «version needed to extract» fuori scala solleva `NotImplementedError`.
    Non e' teoria: fuzzando qui il 01/09/2026 uno zip valido da 119 byte, tutti i
    952 flip di un bit danno 283 `BadZipFile` e **5 `NotImplementedError`**. Il flip
    qui sotto e' uno di quei cinque, tenuto fisso per essere riproducibile.

    Elencare i tipi noti significa scoprire il prossimo in produzione, e il prezzo e'
    asimmetrico: non saper leggere la directory centrale vuol dire non saper giudicare,
    e chi non sa giudicare deve lasciar passare al parser — non morire.
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("d.bin", b"ciao" * 100)
    corrotto = bytearray(buf.getvalue())
    corrotto[52] ^= 1 << 6  # -> "zip file version 8.4"

    esito = controlla_espansione(bytes(corrotto), tetto_bytes=TETTO)

    assert esito.ok
    assert esito.dichiarato is None


def test_memoryerror_non_viene_inghiottito_dalla_difesa():
    """⛔ Il difetto che questo modulo esiste per evitare, rifatto DENTRO la difesa.

    `MemoryError` e' sottoclasse di `Exception`: l'`except` largo del test qui sopra
    — quello che serve e non si puo' restringere — se lo prende. E allora un file
    troppo grosso per la memoria uscirebbe come «non e' uno zip giudicabile»,
    cioe' passerebbe oltre e finirebbe al parser, che direbbe «formato non
    riconosciuto». L'utente andrebbe a discutere del FORMATO mentre il problema
    e' la TAGLIA — un messaggio che manda a cercare nel posto sbagliato.

    Chi chiama deve poter distinguere. Quindi `MemoryError` risale.
    """
    # Il MemoryError deve nascere DENTRO la lettura dello zip, cioe' dentro il `try`.
    # Un primo tentativo lo faceva scattare in `len(data)` — fuori dal try — e il test
    # passava senza provare niente. Qui si sostituisce la lettura, che e' esattamente
    # il punto in cui in produzione la memoria finisce.
    with mock.patch.object(espansione.zipfile, "ZipFile", side_effect=MemoryError):
        with pytest.raises(MemoryError):
            controlla_espansione(b"PK\x03\x04qualsiasi", tetto_bytes=TETTO)


def test_giudica_anche_un_file_su_disco(tmp_path):
    """Chi ha un PERCORSO non deve caricarsi il file in memoria per farlo giudicare.

    Non e' una comodita': un chiamante che riceve upload li scrive in streaming e non
    tiene mai il file intero in RAM — ed e' esattamente il rischio da cui questa guardia
    protegge. Chiedergli i `bytes` per controllarli sarebbe far correre il rischio per
    poterlo misurare.

    La directory centrale si legge senza decomprimere ed e' O(numero di voci), quindi
    regge anche su una share di rete.
    """
    bomba = tmp_path / "estratto.xlsx"
    bomba.write_bytes(_zip_con(b"\0" * (2 * TETTO)))

    esito = controlla_espansione(bomba, tetto_bytes=TETTO)

    assert not esito.ok
    assert esito.motivo == "ostile"


def test_un_argomento_che_non_so_leggere_e_un_errore_non_un_via_libera():
    """⛔ Un cancello che si apre quando non capisce e' peggio di nessun cancello.

    La distinzione: un file che non e' uno zip PASSA — sara' il parser a dire che il
    formato non e' riconosciuto, ed e' la diagnosi giusta. Ma un ARGOMENTO che la guardia
    non sa leggere e' un errore di chi chiama, e deve gridare.

    Non e' teorico: prima che l'ingresso su percorso esistesse, passare un `Path` finiva
    nell'except largo e l'esito era `ok=True`. Su una bomba. Il difetto e' stato visto
    solo perche' il test sul percorso e' stato scritto prima del codice.
    """
    with pytest.raises(TypeError):
        controlla_espansione(12345, tetto_bytes=TETTO)
