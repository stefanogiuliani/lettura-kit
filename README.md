# lettura-kit

Apre file tabellari che arrivano da fuori senza farsi male. **Le guardie, non il dominio.**

## Il confine, che e' nel nome

| la libreria | il tuo repo |
|---|---|
| aprire il file senza esplodere | quali colonne ti servono |
| i tetti contro l'espansione | che dialetto e' questo file |
| `read_only` + `data_only`, dimensioni corrotte | dove sta l'header *in questo formato* |
| il BOM, l'`.xls` travestito, la riga vuota che finisce il foglio | cosa fai dei dati |

Si chiama `lettura` e non `tabelle` apposta: possiede **la lettura**, non cio' che leggi.
Se ti viene voglia di aggiungerci la normalizzazione delle colonne, il nome ti sta dicendo
di no.

## La libreria non scrive i messaggi

Restituisce un verdetto — *cosa* e' successo — e chi chiama sceglie *cosa dire*. La frase
giusta dipende dal flusso di chi la usa (chi ha mandato il file, dove resta, a chi si
richiede), non dal formato.

```python
from lettura.espansione import controlla_espansione

# i byte, oppure un percorso — chi riceve upload in streaming non ha i byte,
# e chiederglieli significherebbe fargli correre il rischio per misurarlo
esito = controlla_espansione(percorso_o_byte, tetto_bytes=150 * 1024 * 1024)
if not esito.ok:
    if esito.motivo == "ostile":
        # si espande 642x: non e' un file grande, e' fatto per espandersi
        ...
    else:  # "troppo_grande"
        # un estratto vero: si risponde «spezzalo», non «richiedilo al mittente»
        ...
```

Distinguere i due casi e' il punto, non un dettaglio: sono **due azioni diverse** per chi
ha ricevuto il file. Una guardia che sapesse solo rifiutare manderebbe l'utente a spezzare
una bomba.

## I numeri sono parametri

Non costanti globali. Ogni tetto e' tarato su misure di UN caso d'uso: quelli che trovi
come default (150 MB dichiarati, rapporto 100, 200.000 righe) vengono da un applicativo che
riceve estratti conto, dove i file veri stanno fra 5 e 11 volte la dimensione compressa e
le bombe misurate a 642. Sono default, non la verita'. Ogni chiamante porta i propri, con
la propria misura che li giustifica.

## Perché esiste

Le guardie contro l'input non fidato tendono a nascere una volta per applicazione, ognuna
imparando un sottoinsieme diverso: chi si difende dalle zip bomb non gestisce il BOM, chi
gestisce il BOM non sa che un foglio dichiara un milione di righe. Nessuna le ha tutte, e
**la copia le perde**: nel travaso sopravvive il codice e si perde il commento che
spiegava perché quella riga c'è.

Questa libreria è il tentativo di tenerle in un posto solo — con dentro le misure, che
sono la parte che non si può riderivare a mente.

## L'altra metà: leggere in un processo figlio

`controlla_espansione` ferma le forme che sappiamo riconoscere. `esegui_isolato` regge
**ciò che non abbiamo previsto** — e contro l'ignoto non serve una regola più furba, serve
che morire non costi l'app.

```python
from lettura.isolata import esegui_isolato, MemoriaEsaurita, LetturaFallita

righe = esegui_isolato("mio_modulo:leggi", dati, limite_mb=900)
```

Il figlio è un processo **nuovo**, non un fork: non eredita il loop asyncio, né le
connessioni, né i monkeypatch di un test. Può solo *importare* — ed è il vincolo che decide
l'API: il lavoro si passa come `"modulo:funzione"`, non come callable.

**I tetti sono due perché nessuno copre l'altro.** `RLIMIT_AS` è duro e istantaneo ma vive
solo dove il sistema lo concede (su macOS `setrlimit` rifiuta); la sorveglianza sulla RSS
funziona ovunque ma **campiona**, quindi una singola allocazione enorme la scavalca.

**E «memoria» si dice solo quando lo si sa.** `MemoriaEsaurita` esce dalla sorveglianza o da
un segnale; ogni altro guasto del figlio esce come `LetturaFallita` **col suo perché**. Se
ogni morte diventasse «memoria esaurita», manderebbe a spezzare un file che non ha niente di
grande mentre mancava una colonna.
