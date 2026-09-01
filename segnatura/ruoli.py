"""I ruoli riconoscibili, e il vocabolario per riconoscerli dal titolo.

Il vocabolario e' il segnale piu' banale e, quando c'e', il piu' forte: se
l'intestazione dice «Bibliografia», e' bibliografia. Sta qui invece che sparso
nel codice perche' aggiungere una lingua dev'essere una voce in piu' in un
dizionario, non una modifica al classificatore.

Due regole imparate a caro prezzo, e da non violare:

1. **confronto per parola, mai per sottostringa.** `toc` dentro `ottocento`,
   `dedica` dentro `dedicato`. E' il bug che ha colpito sia Sibilla sia Archilles.
2. **prefazione, introduzione e postfazione NON sono apparato.** Sono testo
   d'autore, spesso il piu' denso del libro. Hanno un ruolo proprio.
"""
from __future__ import annotations

import re
import unicodedata

# ---------------------------------------------------------------- i ruoli
CORPO = "corpo"                    # il testo del libro
NOTA = "nota"                      # apparato di note
BIBLIOGRAFIA = "bibliografia"
INDICE_ANALITICO = "indice_analitico"
SOMMARIO = "sommario"              # l'indice dei capitoli
PARATESTO = "paratesto"            # copertina, copyright, colophon, backlist
SOGLIA = "soglia"                  # prefazione, introduzione, postfazione
APPENDICE = "appendice"
INCERTO = "incerto"

# Il ruolo descrive che cosa una sezione e'; l'uso stabilisce cosa farne.
# Tenerli separati evita di trasformare una decisione di prodotto in una
# tassonomia: una prefazione resta `soglia`, ma e' testo principale.
TESTO_PRINCIPALE = "testo_principale"
SU_RICHIESTA = "su_richiesta"
ESCLUSO = "escluso"

# Politica predefinita per un archivio interrogabile.
CERCABILI = {CORPO, SOGLIA, APPENDICE}
CERCABILI_A_RICHIESTA = {NOTA}
NON_CERCABILI = {BIBLIOGRAFIA, INDICE_ANALITICO, SOMMARIO, PARATESTO}


def uso(ruolo: str) -> str:
    """Restituisce la politica d'indicizzazione predefinita per un ruolo."""
    if ruolo in CERCABILI:
        return TESTO_PRINCIPALE
    if ruolo in CERCABILI_A_RICHIESTA:
        return SU_RICHIESTA
    return ESCLUSO


PARATESTO_CERCABILE = (
    "dedica", "ringraziamenti", "epigrafe", "avvertenza dell'editore",
    "dedication", "acknowledgements", "acknowledgments", "epigraph",
    "widmung", "danksagung", "epigraph",
    "dedicace", "remerciements", "epigraphe",
    "dedicatoria", "agradecimientos", "epigrafe",
)
PARATESTO_CERCABILE_EPUB = {"dedication", "acknowledgments", "epigraph"}
PARATESTO_CERCABILE_ARIA = {
    "doc-dedication", "doc-acknowledgments", "doc-epigraph",
}

# Intestazioni editoriali che, quando compaiono esattamente ai margini del
# volume, descrivono schede promozionali e non capitoli dell'opera. Restano
# separate dal vocabolario generale: li' una frase puo' comparire dentro un
# titolo piu' lungo, qui l'uguaglianza deve essere esatta.
PARATESTO_CREDITI_IMMAGINI_ESATTO = (
    "referenze fotografiche", "crediti fotografici",
    "referenze iconografiche", "crediti iconografici",
    "fonti fotografiche", "fonti iconografiche", "crediti delle immagini",
    "photo credits", "photographic credits", "image credits",
    "picture credits", "illustration credits",
    "bildnachweis", "bildnachweise", "fotonachweis", "fotonachweise",
    "credits photographiques", "credits iconographiques",
    "creditos fotograficos", "creditos de imagenes",
)

PARATESTO_EDITORIALE_ESATTO = (
    "copertina", "frontespizio", "copyright", "colophon", "crediti",
    "il libro", "trama", "sinossi", "l'autore", "l'autrice", "gli autori",
    "autori", "biografia", "notizie sull'autore", "notizie sull'autrice",
    "nota sull'autore", "nota sull'autrice", "biografia dell'autore",
    "biografia dell'autrice",
    "dello stesso autore", "della stessa autrice",
    "cover", "title page", "copyright", "copyright and info",
    "about the book", "synopsis",
    "book description", "plot summary",
    "about the author", "about the authors", "authors", "biography",
    "author biography", "author bio", "also by",
    "umschlag", "titelei", "impressum", "uber den autor", "autoren",
    "biografie", "uber die autorin", "autorenbiografie",
    "kurzbeschreibung", "buchbeschreibung",
    "couverture", "page de titre", "a propos du livre", "synopsis",
    "resume du livre",
    "a propos de l'auteur", "a propos de l'autrice", "auteurs",
    "biographie", "biographie de l'auteur", "biographie de l'autrice",
    "de meme auteur",
    "cubierta", "portada", "creditos", "sobre el libro", "sinopsis",
    "resumen del libro",
    "sobre el autor", "sobre la autora", "autores", "biografia",
    "biografia del autor", "biografia de la autora",
    *PARATESTO_CREDITI_IMMAGINI_ESATTO,
)

TESTO_DIDATTICO_ESATTO = (
    "domande", "esercizi", "quesiti", "domande di discussione",
    "questions", "exercises", "discussion questions",
)


def paratesto_cercabile(titoli=(), epub_type=(), ruoli_aria=()) -> bool:
    """Dediche e ringraziamenti conservano il ruolo, ma restano cercabili."""
    if set(epub_type or ()) & PARATESTO_CERCABILE_EPUB:
        return True
    if set(ruoli_aria or ()) & PARATESTO_CERCABILE_ARIA:
        return True
    testo = normalizza(" ".join(str(x) for x in titoli if x))
    return any(combacia(frase, testo) for frase in PARATESTO_CERCABILE)


def epigrafe_dom_cercabile(marcatori=()) -> bool:
    """Firma editoriale stretta per epigrafi senza semantica EPUB.

    Alcune esportazioni marcano il contenitore come ``dedication``, il testo
    come ``extract`` e l'attribuzione come ``signature``. Presi singolarmente
    sono stili ambigui; la loro compresenza descrive invece una citazione
    autonoma con fonte, che conserva ruolo paratestuale ma resta indicizzabile.
    """
    token = {str(x or "").strip().casefold() for x in marcatori}
    return {"dedication", "extract", "signature"}.issubset(token)


def dedica_dom_cercabile(marcatori=()) -> bool:
    """Classi esplicite di dedica, inglesi o italiane numerate."""
    return any(
        (str(x or "").strip().casefold() == "dedication"
         or re.fullmatch(r"dedica\d*", str(x or "").strip().casefold()))
        for x in marcatori
    )


def paratesto_editoriale_esatto(titoli=()) -> bool:
    """Vero solo per un'intestazione editoriale completa, non sottostringa."""
    validi = {normalizza(x) for x in PARATESTO_EDITORIALE_ESATTO}
    return any(normalizza(str(titolo)) in validi
               for titolo in titoli if titolo)


def paratesto_crediti_immagini_esatto(titoli=()) -> bool:
    """Intestazione completa di crediti fotografici o iconografici."""
    validi = {
        normalizza(x).strip() for x in PARATESTO_CREDITI_IMMAGINI_ESATTO
    }
    return any(normalizza(str(titolo)).strip() in validi
               for titolo in titoli if titolo)


def dedica_breve(testi=()) -> bool:
    """Dediche nominali senza heading, per esempio ``A Justine``/``To Sam``.

    Viene usata soltanto su blocchi gia' classificati come paratesto: decide
    l'uso indicizzabile, non inventa da sola un ruolo editoriale.
    """
    preposizioni = {
        # Italiano e forme articolate; ``normalizza`` elimina gli accenti.
        "a", "ad", "al", "allo", "alla", "ai", "agli", "alle",
        # Inglese, tedesco, francese e spagnolo.
        "to", "for", "fur", "au", "aux", "pour", "para",
    }
    for testo in testi:
        valore = normalizza(str(testo or "")).strip()
        parole = valore.split()
        breve_nominale = len(parole) <= 8 and len(valore) <= 80
        # Le dediche a gruppi o famiglie possono continuare con un elenco di
        # nomi. Per allargare il limite senza assorbire normale prosa breve si
        # pretende la forma esplicita ``destinatari: nome, nome, ...``.
        elenco_nominale = (
            len(parole) <= 18 and len(valore) <= 160
            and ":" in str(testo or "") and "," in str(testo or "")
        )
        if (2 <= len(parole) and parole[0] in preposizioni
                and (breve_nominale or elenco_nominale)):
            return True
    return False


PROMO_EDITORIALE = (
    "ti e piaciuto questo libro", "scoprire nuovi autori",
    "iscriverti alla nostra newsletter", "seguici su", "booktrailer",
    "leggi qui la scheda", "leggete qui la scheda",
    "visita il nostro sito", "scarica il catalogo",
    "registrati e ricevi",
    "did you enjoy this book", "discover new authors",
    "sign up for our newsletter", "subscribe to our newsletter",
    "follow us", "like us on", "watch us on", "join us on", "shop online",
    "hat ihnen dieses buch gefallen", "neue autoren entdecken",
    "newsletter abonnieren", "folgen sie uns",
    "vous avez aime ce livre", "decouvrir de nouveaux auteurs",
    "inscrivez vous a notre newsletter", "suivez nous",
    "te ha gustado este libro", "descubrir nuevos autores",
    "suscribete a nuestro boletin", "siguenos",
)

# Inviti all'azione sufficientemente specifici da essere promozionali quando
# conducono anche a un sito esterno. La condizione sull'URL evita che un solo
# imperativo generico basti; posizione e lunghezza restano vincolate nel
# classificatore dei blocchi.
PROMO_EDITORIALE_FORTE = (
    "leggi qui la scheda", "leggete qui la scheda",
    "visita il nostro sito", "scarica il catalogo",
    "registrati e ricevi",
)

CREDITI_EDITORIALI = (
    "acquisitions editor", "compilation editor", "copy editor",
    "production editor", "technical editor", "project manager",
    "art coordinator", "cover photos", "cover photo", "cover design",
    "editor responsabile", "redattore", "revisione editoriale",
    "progetto grafico", "grafica di copertina", "foto di copertina",
    "verantwortlicher redakteur", "umschlaggestaltung",
    "directeur editorial", "revision editoriale", "conception graphique",
    "editor responsable", "revision editorial", "diseno de cubierta",
)

LICENZE_UTENTE = (
    "end user license agreement", "ebook license agreement", "ebook eula",
    "contratto di licenza per l'utente finale", "licenza utente finale",
    "endbenutzer lizenzvereinbarung", "endbenutzer lizenzvertrag",
    "contrat de licence utilisateur final",
    "accord de licence utilisateur final",
    "acuerdo de licencia de usuario final",
    "contrato de licencia de usuario final",
)

TITOLI_BIOGRAFIA_AUTORE = (
    "biografia", "notizie sull'autore", "notizie sull'autrice",
    "nota sull'autore", "nota sull'autrice", "biografia dell'autore",
    "biografia dell'autrice", "about the author", "about the authors",
    "author biography", "author bio", "biography", "uber den autor",
    "uber die autorin", "autorenbiografie", "a propos de l'auteur",
    "a propos de l'autrice", "biographie de l'auteur",
    "biographie de l'autrice", "sobre el autor", "sobre la autora",
    "biografia del autor", "biografia de la autora",
)

BACKLIST_EDITORIALE = (
    "ultimi volumi pubblicati", "altri volumi pubblicati",
    "titoli pubblicati", "novita in collana", "collana diretta da",
    "recent titles", "other titles published", "also available",
    "zuletzt erschienen", "weitere titel",
    "derniers titres parus", "autres titres publies",
    "ultimos titulos publicados", "otros titulos publicados",
)


def paratesto_promozionale(testi=()) -> bool:
    """Riconosce firme multiple oppure un invito forte con URL esterno."""
    grezzo = " ".join(str(x) for x in testi if x)
    testo = normalizza(grezzo)
    firme = sum(combacia(frase, testo) for frase in PROMO_EDITORIALE)
    invito_forte = any(combacia(frase, testo)
                       for frase in PROMO_EDITORIALE_FORTE)
    ha_url = bool(re.search(r"(?:https?://|www\.)", grezzo, re.I))
    return firme >= 2 or (invito_forte and ha_url)


def rimando_editoriale_a_raccolta(testi=()) -> bool:
    """Formula breve che attribuisce il testo a una raccolta piu' ampia.

    Da sola non assegna alcun ruolo: il classificatore la usa soltanto ai
    margini del volume e davanti a una pagina titolare strutturale.
    """
    testo = normalizza(" ".join(str(x) for x in testi if x))
    formule = (
        "fa parte della raccolta",
        "fanno parte della raccolta",
        "fa parte della piu ampia raccolta",
        "fanno parte della piu ampia raccolta",
    )
    return any(combacia(frase, testo) for frase in formule)


def paratesto_crediti_editoriali(testi=()) -> bool:
    """Crediti dello staff editoriale, con almeno due firme indipendenti."""
    testo = normalizza(" ".join(str(x) for x in testi if x))
    return sum(combacia(frase, testo) for frase in CREDITI_EDITORIALI) >= 2


def paratesto_licenza_utente(testi=()) -> bool:
    """Licenze/EULA editoriali, non contenuto dell'opera."""
    testo = normalizza(" ".join(str(x) for x in testi if x))
    return any(combacia(frase, testo) for frase in LICENZE_UTENTE)


def titolo_biografia_autore_esatto(titoli=()) -> bool:
    """Intestazione biografica completa, mai semplice sottostringa."""
    validi = {normalizza(x).strip() for x in TITOLI_BIOGRAFIA_AUTORE}
    return any(normalizza(str(titolo)).strip() in validi
               for titolo in titoli if titolo)


def paratesto_backlist(testi=()) -> bool:
    """Catalogo di altri titoli dell'editore, con firma non ambigua."""
    testo = normalizza(" ".join(str(x) for x in testi if x))
    if any(combacia(frase, testo) for frase in BACKLIST_EDITORIALE):
        return True
    # I cataloghi in coda all'EPUB portano spesso il nome della casa editrice
    # invece di una formula standard come ``altri titoli pubblicati``. La
    # coppia funzionale catalogo+editore resta abbastanza specifica; sara' poi
    # il classificatore a richiedere anche posizione finale e dimensione
    # limitata, quindi una menzione incidentale nel testo non basta.
    coppie_catalogo_editore = (
        ("catalogo", ("editore", "edizioni", "casa editrice")),
        ("catalog", ("publisher", "publishing")),
        ("catalogue", ("publisher", "editeur")),
        ("katalog", ("verlag",)),
        ("catalogo", ("editorial",)),
    )
    return any(
        combacia(catalogo, testo)
        and any(combacia(editore, testo) for editore in editori)
        for catalogo, editori in coppie_catalogo_editore
    )


def paratesto_legale(testi=()) -> bool:
    """Copyright/colophon senza heading, riconosciuto da firme congiunte."""
    grezzo = " ".join(str(x or "") for x in testi)
    testo = normalizza(grezzo)
    diritto = ("©" in grezzo or combacia("copyright", testo)
               or combacia("tutti i diritti riservati", testo)
               or combacia("all rights reserved", testo))
    firme = (
        "isbn", "edizioni", "editore", "casa editrice", "prima edizione",
        "publisher", "published by", "first published",
        "verlag", "editeur", "editorial",
    )
    firme_stampa = (
        "finito di stampare", "stampato presso", "printed in italy",
        "stabilimento di", "registr trib", "registrazione tribunale",
        "direttore responsabile",
    )
    colophon_tipografico = sum(
        combacia(frase, testo) for frase in firme_stampa) >= 2
    return ((diritto and any(combacia(frase, testo) for frase in firme))
            or colophon_tipografico)


INCIPIT_SOMMARIO = (
    "indice", "sommario", "indice generale",
    "contents", "table of contents",
    "inhalt", "inhaltsverzeichnis",
    "sommaire", "table des matieres",
    "contenido", "sumario",
)


def sommario_incipit(testi=()) -> bool:
    """Heading testuale iniziale di un TOC privo di markup semantico."""
    for valore in testi:
        testo = normalizza(str(valore or "")).strip()
        if any(testo == frase or testo.startswith(frase + " ")
               for frase in INCIPIT_SOMMARIO):
            return True
    return False


def testo_didattico_esatto(titoli=()) -> bool:
    """Domande ed esercizi sono contenuto, non un indice numerato."""
    validi = {normalizza(x).strip() for x in TESTO_DIDATTICO_ESATTO}
    for titolo in titoli:
        if not titolo:
            continue
        valore = normalizza(str(titolo)).strip()
        # Stile editoriale a falso maiuscoletto: ``D OMANDE``.
        valore = re.sub(r"^d\s+omande$", "domande", valore)
        if valore in validi:
            return True
    return False


def piano_capitolo_esatto(titoli=()) -> bool:
    """Riconosce il sommario locale, anche col falso maiuscoletto EPUB."""
    for titolo in titoli:
        if not titolo:
            continue
        valore = normalizza(str(titolo)).strip()
        if re.fullmatch(r"p(?:\s+)?iano\s+del\s+capitolo(?:\s+\d+)?", valore):
            return True
    return False

# ---------------------------------------------------------------- vocabolario
# Chiave: ruolo. Valore: frasi da confrontare col titolo, PER PAROLA.
VOCABOLARIO: dict[str, dict[str, list[str]]] = {
    "it": {
        NOTA: ["note", "nota", "nota al testo", "note al testo", "note bibliografiche",
               "nota del traduttore", "note del traduttore", "annotazioni"],
        BIBLIOGRAFIA: ["bibliografia", "nota bibliografica",
                       "selezione bibliografica",
                       "fonti bibliografiche",
                       "riferimenti bibliografici", "fonti",
                       "opere citate", "bibliografia essenziale", "letture"],
        SOMMARIO: ["indice", "sommario", "indice generale",
                   "elenco delle illustrazioni", "indice delle illustrazioni",
                   "elenco delle figure", "indice delle figure"],
        PARATESTO: ["copertina", "frontespizio", "occhiello", "colophon",
                    "copyright", "dedica", "ringraziamenti", "l'autore",
                    "l'autrice", "gli autori", "dello stesso autore",
                    "della stessa autrice", "il libro", "nota dell'editore",
                    "avvertenza", "crediti", "quest'opera",
                    "notizie sull'autore", "notizie sull'autrice",
                    "nota sull'autore", "nota sull'autrice",
                    "biografia dell'autore", "biografia dell'autrice"],
        SOGLIA: ["prefazione", "introduzione", "premessa", "postfazione",
                 "prologo", "epilogo", "conclusioni", "conclusione",
                 "nota introduttiva", "note conclusive", "presentazione",
                 "avvertenza dell'autore", "nota editoriale"],
        APPENDICE: ["appendice", "appendici", "allegati", "documenti",
                    "cronologia", "glossario", "tavole"],
        INDICE_ANALITICO: ["indice analitico", "indice dei nomi", "indice dei luoghi",
                           "indice delle cose notevoli", "indice dei temi",
                           "abbreviazioni", "elenco delle abbreviazioni", "sigle"],
        CORPO: ["capitolo", "parte", "libro primo", "libro secondo", "sezione"],
    },
    "en": {
        NOTA: ["notes", "endnotes", "footnotes", "notes to the text"],
        BIBLIOGRAFIA: ["bibliography", "references", "works cited",
                       "further reading", "sources"],
        INDICE_ANALITICO: ["index", "name index", "subject index", "general index",
                           "abbreviations", "list of abbreviations"],
        SOMMARIO: ["contents", "table of contents", "list of illustrations",
                   "list of figures"],
        PARATESTO: ["cover", "title page", "half title", "copyright",
                    "colophon", "dedication", "acknowledgements",
                    "acknowledgments", "about the author", "also by",
                    "about the authors", "author biography", "author bio",
                    "front matter", "back matter"],
        SOGLIA: ["preface", "introduction", "foreword", "prologue", "epilogue",
                 "afterword", "conclusion"],
        APPENDICE: ["appendix", "appendices", "glossary", "chronology",
                    "tables"],
        CORPO: ["chapter", "part", "book one", "book two", "section"],
    },
    "de": {
        NOTA: ["anmerkungen", "fussnoten", "fußnoten", "endnoten"],
        BIBLIOGRAFIA: ["literaturverzeichnis", "bibliographie", "quellen",
                       "literatur"],
        INDICE_ANALITICO: ["register", "namenregister", "sachregister",
                           "abkurzungen", "abkurzungsverzeichnis"],
        SOMMARIO: ["inhalt", "inhaltsverzeichnis", "abbildungsverzeichnis",
                   "verzeichnis der abbildungen"],
        PARATESTO: ["impressum", "widmung", "danksagung", "uber den autor",
                    "uber die autorin", "autorenbiografie", "umschlag",
                    "titelei"],
        SOGLIA: ["vorwort", "einleitung", "nachwort", "prolog", "epilog"],
        APPENDICE: ["anhang", "glossar", "zeittafel"],
        CORPO: ["kapitel", "teil", "abschnitt"],
    },
    "fr": {
        NOTA: ["notes", "notes du traducteur"],
        BIBLIOGRAFIA: ["bibliographie", "references", "sources",
                       "ouvrages cites"],
        INDICE_ANALITICO: ["index", "index des noms", "abreviations",
                           "liste des abreviations"],
        SOMMARIO: ["sommaire", "table des matieres",
                   "liste des illustrations", "table des illustrations"],
        PARATESTO: ["couverture", "page de titre", "copyright", "dedicace",
                    "remerciements", "a propos de l'auteur",
                    "a propos de l'autrice", "biographie de l'auteur",
                    "biographie de l'autrice", "de meme auteur"],
        SOGLIA: ["preface", "introduction", "avant-propos", "postface",
                 "prologue", "epilogue", "conclusion"],
        APPENDICE: ["annexe", "annexes", "glossaire", "chronologie"],
        CORPO: ["chapitre", "partie", "livre premier"],
    },
    "es": {
        NOTA: ["notas", "notas al texto"],
        BIBLIOGRAFIA: ["bibliografia", "referencias", "obras citadas", "fuentes"],
        INDICE_ANALITICO: ["indice analitico", "indice de nombres",
                           "abreviaturas", "lista de abreviaturas"],
        SOMMARIO: ["indice", "contenido", "sumario",
                   "lista de ilustraciones", "indice de ilustraciones"],
        PARATESTO: ["cubierta", "portada", "creditos", "dedicatoria",
                    "agradecimientos", "sobre el autor", "sobre la autora",
                    "biografia del autor", "biografia de la autora"],
        SOGLIA: ["prefacio", "introduccion", "prologo", "epilogo", "conclusion"],
        APPENDICE: ["apendice", "anexo", "glosario", "cronologia"],
        CORPO: ["capitulo", "parte", "seccion"],
    },
}

# `epub:type` e ruoli ARIA: quando ci sono, sono dichiarazioni dell'editore.
DA_EPUB_TYPE = {
    "footnote": NOTA, "footnotes": NOTA, "endnote": NOTA, "endnotes": NOTA,
    "rearnote": NOTA, "rearnotes": NOTA, "noteref": NOTA,
    "bibliography": BIBLIOGRAFIA, "biblioentry": BIBLIOGRAFIA,
    "index": INDICE_ANALITICO, "toc": SOMMARIO, "landmarks": SOMMARIO,
    "cover": PARATESTO, "titlepage": PARATESTO, "halftitlepage": PARATESTO,
    "copyright-page": PARATESTO, "colophon": PARATESTO, "dedication": PARATESTO,
    "epigraph": PARATESTO, "abstract": PARATESTO,
    "acknowledgments": PARATESTO, "imprimatur": PARATESTO,
    "preface": SOGLIA, "foreword": SOGLIA, "introduction": SOGLIA,
    "prologue": SOGLIA, "epilogue": SOGLIA, "afterword": SOGLIA,
    "conclusion": SOGLIA,
    "appendix": APPENDICE, "glossary": APPENDICE, "chronology": APPENDICE,
    "chapter": CORPO, "part": CORPO, "division": CORPO, "bodymatter": CORPO,
    "volume": CORPO, "subchapter": CORPO,
}
DA_ARIA = {
    "doc-footnote": NOTA, "doc-endnote": NOTA, "doc-endnotes": NOTA,
    "doc-noteref": NOTA, "doc-bibliography": BIBLIOGRAFIA,
    "doc-biblioentry": BIBLIOGRAFIA, "doc-index": INDICE_ANALITICO,
    "doc-toc": SOMMARIO, "doc-cover": PARATESTO, "doc-colophon": PARATESTO,
    "doc-credits": PARATESTO, "doc-dedication": PARATESTO,
    "doc-epigraph": PARATESTO, "doc-abstract": PARATESTO,
    "doc-acknowledgments": PARATESTO, "doc-preface": SOGLIA,
    "doc-foreword": SOGLIA, "doc-prologue": SOGLIA, "doc-epilogue": SOGLIA,
    "doc-afterword": SOGLIA, "doc-conclusion": SOGLIA, "doc-appendix": APPENDICE,
    "doc-glossary": APPENDICE, "doc-chapter": CORPO, "doc-part": CORPO,
}

# Alcuni EPUB, soprattutto EPUB 2 convertiti, non usano `epub:type` ma
# conservano comunque una dichiarazione editoriale molto esplicita in classi
# CSS come `footnote` o `preface`. Non sono standard e quindi restano separati
# dalle dichiarazioni forti qui sopra; il confronto e' esclusivamente sul token
# intero, mai su sottostringhe o classi decorative generiche.
MARCATORE_NOTE_NUMERATE_LINKATE = "__segnatura_note_numerate_linkate__"

DA_MARCATORE_DOM = {
    "footnote": NOTA, "footnotes": NOTA, "endnote": NOTA,
    "endnotes": NOTA, "rearnote": NOTA, "rearnotes": NOTA,
    # Variante prodotta da alcune esportazioni editoriali/InDesign. Il
    # prefisso ``x`` appartiene al contenitore della nota; ``footnote-link``
    # resta invece escluso perché identifica il richiamo dentro il corpo.
    "xfootnote": NOTA, "x-footnote": NOTA, "x_footnote": NOTA,
    # Esportazione InDesign/EPUB 2 diffusa nell'editoria accademica italiana:
    # ogni nota vive in un contenitore ``testo_nota``. Il token e' esatto e
    # quindi non confonde espressioni generiche che contengono la parola nota.
    "testo_nota": NOTA, "testo-nota": NOTA,
    # Esportazione italiana InDesign/Calibre: il paragrafo della nota usa una
    # classe descrittiva esplicita, talvolta distinta per la continuazione.
    "note_pie_di_pagina": NOTA, "note_pie_di_pagina_sotto": NOTA,
    # Intestazione delle note di capitolo in alcune esportazioni Calibre.
    # La classe generica ``note`` resta intenzionalmente esclusa: ``noteh``
    # identifica invece l'heading che apre l'apparato ed e' sufficientemente
    # specifica da stabilire il confine col corpo del capitolo.
    "noteh": NOTA,
    MARCATORE_NOTE_NUMERATE_LINKATE: NOTA,
    "bibliography": BIBLIOGRAFIA, "references": BIBLIOGRAFIA,
    "subject-index": INDICE_ANALITICO, "name-index": INDICE_ANALITICO,
    "table-of-contents": SOMMARIO, "toc": SOMMARIO,
    "cover": PARATESTO, "titlepage": PARATESTO,
    "title-page": PARATESTO, "halftitlepage": PARATESTO,
    "halftitle": PARATESTO, "half-title": PARATESTO,
    "bastard-title": PARATESTO, "occhiello": PARATESTO,
    # Numero di pagina ornamentale associato all'occhiello in alcune
    # esportazioni InDesign. Non e' contenuto indicizzabile.
    "occhiello_n": PARATESTO, "occhiello-n": PARATESTO,
    "faux-titre": PARATESTO, "schmutztitel": PARATESTO,
    "anteportada": PARATESTO, "copyright-page": PARATESTO,
    "colophon": PARATESTO, "dedication": PARATESTO,
    "preface": SOGLIA, "foreword": SOGLIA, "introduction": SOGLIA,
    "prologue": SOGLIA, "epilogue": SOGLIA, "afterword": SOGLIA,
    "appendix": APPENDICE, "glossary": APPENDICE,
    "chronology": APPENDICE,
}


def apparato_note_numerate_linkate(testo: str, n_link: int) -> bool:
    """Firma locale di un contenitore di note ``[1] [2] [3] ...``.

    Alcune conversioni Calibre cancellano i nomi semantici delle classi ma
    conservano perfettamente richiami e backlink. Richiedere che il contenitore
    inizi da ``[1]``, prosegua almeno fino a ``[3]`` nell'ordine e contenga i
    relativi link evita di scambiare per apparato la prosa con citazioni inline.
    """
    if n_link < 3 or not re.match(r"^\s*\[\s*1\s*\]", testo or ""):
        return False
    numeri = [int(x) for x in re.findall(r"\[\s*(\d{1,4})\s*\]",
                                         testo or "")]
    return len(numeri) >= 3 and numeri[:3] == [1, 2, 3]


def per_marcatori_dom(marcatori) -> tuple[str | None, str | None]:
    """Ruolo e token del marcatore DOM piu' vicino all'elemento.

    I marcatori arrivano in ordine dagli antenati all'elemento corrente: la
    scansione inversa fa prevalere, per esempio, un `footnote` annidato in un
    contenitore generico di front matter.
    """
    for marcatore in reversed(tuple(marcatori or ())):
        token = (marcatore or "").strip().casefold()
        if token in DA_MARCATORE_DOM:
            return DA_MARCATORE_DOM[token], token
        # Varianti numerate usate da alcune esportazioni InDesign per gli
        # elementi successivi della stessa pagina titolare (``titlepage1``,
        # ``titlepage2``). Il suffisso e' soltanto numerico e il confronto e'
        # ancorato all'intero token.
        if re.fullmatch(r"titlepage\d+", token):
            return PARATESTO, token
        # Sigla molto comune negli EPUB 2/Calibre: ``fnote`` e le sue varianti
        # numerate identificano paragrafi di note. Il confronto resta ancorato
        # all'intero token, quindi non reintroduce i falsi positivi da
        # sottostringa che questa funzione deve evitare.
        if re.fullmatch(r"fnote\d*", token):
            return NOTA, token
        # Altra famiglia diffusa: ``fn`` per le note ordinarie e ``fn_t``
        # (footnote top) per la prima nota del gruppo. Il suffisso resta
        # ristretto e ancorato, per non trasformare classi arbitrarie che
        # cominciano con le stesse lettere.
        if re.fullmatch(r"fn(?:\d*|[_-](?:t|text))", token):
            return NOTA, token
        # InDesign assegna spesso un id/classe progressivo al contenitore:
        # ``footnote-036``. Il numero ancorato distingue la nota dal richiamo
        # inline ``footnote-link``, che deve restare testo del capitolo.
        if re.fullmatch(r"footnote[-_]\d+", token):
            return NOTA, token
        # Classi editoriali italiane esatte: ``bib``/``bib1`` identificano
        # voci bibliografiche; ``dedica``/``dedica1`` una dedica. I suffissi
        # sono soltanto numerici, quindi parole come ``bible`` o ``dedicato``
        # non possono combaciare accidentalmente.
        if re.fullmatch(r"bib\d*", token):
            return BIBLIOGRAFIA, token
        # Variante descrittiva molto comune nelle esportazioni InDesign:
        # ``biblio`` e suffissi di stile come ``biblio-1sp``. Il prefisso e'
        # ancorato all'intero token e seguito solo da segmenti CSS, quindi non
        # combacia parole generiche come ``bibliophile``.
        if re.fullmatch(r"biblio(?:[-_][a-z0-9]+)*", token):
            return BIBLIOGRAFIA, token
        if re.fullmatch(r"dedica\d*", token):
            return PARATESTO, token
        # Esportazioni italiane InDesign descrivono spesso i singoli elementi
        # della pagina titolare come ``autore-frontespizio``,
        # ``titolo-frontespizio1`` o ``titolo-frontespizio-lib``. Sono token
        # composti ma semanticamente espliciti; il match per segmenti interi
        # evita di riaprire i falsi positivi da semplice sottostringa.
        if re.fullmatch(
                r"(?:[a-z0-9]+[-_])*frontespizio"
                r"(?:\d*|(?:[-_][a-z0-9]+)*)",
                token):
            return PARATESTO, token
    return None, None


def normalizza(s: str) -> str:
    """Minuscole, senza accenti, con spazi ai bordi: pronta per il confronto
    PER PAROLA. Gli accenti si tolgono perche' i titoli li scrivono in tutti i
    modi (`prefazione`, `Prefazióne`) e perche' cosi' il tedesco senza umlaut
    combacia lo stesso."""
    s = unicodedata.normalize("NFD", (s or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.replace("’", "'").replace("`", "'")
    return " " + re.sub(r"[^0-9a-z']+", " ", s).strip() + " "


def nome_file_frontespizio(nome: str | None) -> bool:
    """Firma stretta dei filename usati per il frontespizio EPUB."""
    return bool(re.fullmatch(
        r"(?:[fp]\d+[_-])?"
        r"(?:title(?:page)?|frontispiece|frontespizio)"
        r"(?:[_-]?\d*)?\.(?:xhtml|html|htm)",
        str(nome or ""),
        re.I,
    ))


def combacia(frase: str, testo_normalizzato: str) -> bool:
    """La frase compare come sequenza di parole intere?

    MAI per sottostringa: `toc` dentro `ottocento`, `index` dentro `indexed`,
    `nota` dentro `notare`. E' il bug che ha colpito Sibilla e Archilles, con lo
    stesso esempio (`protocol` → `toc`).
    """
    f = normalizza(frase).strip()
    return bool(f) and f" {f} " in testo_normalizzato


def per_titolo(titolo: str | None, lingua: str | None = None) -> tuple[str | None, str | None]:
    """(ruolo, frase che ha combaciato). La lingua sceglie il vocabolario da
    provare per primo; poi si provano comunque tutte, perche' molti libri
    italiani hanno sezioni intitolate in inglese e viceversa."""
    if not titolo:
        return None, None
    t = normalizza(titolo)
    # Le schede biografiche plurali sono spesso intitolate con la sola parola
    # ``Autori``/``Authors``. Trattarle come intestazioni esatte evita che la
    # parola dentro un normale titolo di capitolo diventi un falso paratesto.
    if paratesto_editoriale_esatto((titolo,)):
        return PARATESTO, t.strip()
    if piano_capitolo_esatto((titolo,)):
        return SOMMARIO, "piano del capitolo"
    # Alcuni CSS simulano la spaziatura tipografica inserendo uno spazio dopo
    # la prima lettera dell'heading (``N OTE``). Il segmentatore propaga quel
    # titolo anche ai paragrafi che seguono: riconoscerne soltanto le forme
    # esatte permette quindi all'intero apparato locale di ereditare NOTA,
    # senza attribuire significato alla classe CSS generica ``note``.
    if t.strip() in {"n ota", "n ote", "n otes"}:
        return NOTA, "note"
    # Nei manuali accademici questa formula introduce normalmente le note
    # numerate del capitolo (spesso quasi tutte citazioni), mentre una sezione
    # separata "Ulteriori riferimenti bibliografici" segue subito dopo. La
    # regola generica della frase piu' lunga farebbe vincere "riferimenti
    # bibliografici" e perderebbe la distinzione operativa fra i due apparati.
    if (combacia("note e riferimenti bibliografici", t)
            or re.search(
                r"\bn\s+ote\s+e\s+riferimenti\s+bibliografici\b", t)):
        return NOTA, "note e riferimenti bibliografici"
    lingue = list(VOCABOLARIO)
    if lingua:
        base = lingua.split("-")[0].lower()
        if base in VOCABOLARIO:
            lingue = [base] + [x for x in lingue if x != base]
    # le frasi piu' lunghe hanno la precedenza: «indice analitico» prima di «indice»
    generiche_solo_esatte = {"nota", "fonti", "sources", "quellen", "fuentes"}
    paratesto_solo_esatto = {
        normalizza(x).strip() for x in PARATESTO_EDITORIALE_ESATTO
    }
    for lg in lingue:
        voci = [(ruolo, frase) for ruolo, frasi in VOCABOLARIO[lg].items()
                for frase in frasi]
        for ruolo, frase in sorted(voci, key=lambda x: -len(x[1])):
            if combacia(frase, t):
                # Queste formule descrivono una scheda editoriale soltanto
                # quando costituiscono l'intero heading. In un titolo come
                # ``Il libro di larga circolazione`` o ``L'autore, lo
                # stampatore-libraio...`` sono invece parole del normale
                # discorso saggistico. Il caso esatto e' gia' stato gestito
                # da ``paratesto_editoriale_esatto`` sopra.
                if (ruolo == PARATESTO
                        and normalizza(frase).strip()
                        in paratesto_solo_esatto):
                    continue
                if (frase in generiche_solo_esatte
                        and t.strip() != normalizza(frase).strip()):
                    continue
                return ruolo, frase
    return None, None
