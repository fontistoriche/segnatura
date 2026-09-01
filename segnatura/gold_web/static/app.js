const LABELS = ['work_text', 'note', 'bibliography', 'index', 'paratext', 'mixed'];

const I18N = {
  it: {
    profileTag:'Profilo dell’edizione', subtitle: 'Revisione EPUB e Profilo dell’edizione', savedLocal: 'Nella sessione',
    welcomeTitle: 'Revisiona la classificazione di Segnatura',
    welcomeBody: 'Le correzioni valgono soltanto per questa esatta edizione dell’EPUB.',
    chooseBook: 'Scegli un libro', loadingBooks: 'Caricamento libri…', open: 'Apri', home:'Home', browseEpub:'Sfoglia EPUB…', importingEpub:'Caricamento EPUB…', importedEpub:'EPUB selezionato dal disco',
    document: 'Sezione EPUB', originalPage: 'Pagina originale dell’EPUB', previousBlock: 'Blocco precedente', nextBlock: 'Blocco successivo', reload: 'Ricarica',
    wholeDocument: 'Intera sezione EPUB', documentHint: 'Classifica l’intera sezione visualizzata.',
    highlightedBlock: 'Blocco evidenziato', sameAsDocument: 'Usa la categoria del documento',
    rangeTitle:'Parte di questo blocco', rangeHelp:'Se il blocco contiene funzioni diverse, seleziona qui sopra il testo esatto, scegli la categoria e aggiungilo come intervallo separato.', saveRange:'Classifica il testo selezionato', removeRange:'Rimuovi', noRanges:'Nessun intervallo specifico.', selectRangeFirst:'Seleziona prima una porzione di testo nel riquadro qui sopra.', rangeSaved:'Intervallo salvato', rangeRemoved:'Intervallo rimosso', mixedRangeHint:'Per un blocco misto, seleziona e classifica separatamente le sue parti.',
    optionalNote: 'Nota facoltativa', export: 'Esporta profilo', exporting: 'Creazione del Profilo dell’edizione…', exported: 'Profilo dell’edizione esportato', savedNextToEpub:'Profilo salvato accanto all’EPUB', noApplicableCorrections:'Classifica almeno un documento o blocco con una categoria concreta.',
    shortcut: 'Tasti 1–6: categoria · frecce: blocco precedente/successivo',
    booksFound: (n,root,selected) => selected ? `${n} EPUB ${n === 1 ? 'disponibile' : 'disponibili'} · ${selected} ${selected === 1 ? 'selezionato' : 'selezionati'} dal disco` : `${n} EPUB ${n === 1 ? 'trovato' : 'trovati'} in ${root}`, loading: 'Apertura e analisi dell’EPUB…', saved: 'Salvato nella sessione', saveError: 'Errore di salvataggio',
    unsavedCorrections:n => `${n} ${n === 1 ? 'correzione non esportata' : 'correzioni non esportate'}`, unsavedChanges:'Modifiche non esportate', confirmDiscardUnsaved:'Ci sono modifiche non esportate. Vuoi davvero lasciare questo libro e perderle?',
    noBlocks: 'Nessun blocco testuale', block: 'Blocco', characters: 'caratteri', confidence:'confidenza', auxiliary: 'ausiliario', linear: 'lettura lineare',
    annotated: (done, total) => `${done}/${total} blocchi annotati`, noDocumentLabel: 'Classifica prima il documento',
    explore:'Editor del Profilo dell’edizione',
    labels: {work_text:'Testo', note:'Nota', bibliography:'Bibliografia', index:'Indice', paratext:'Paratesto', mixed:'Misto'},
    descriptions: {
      work_text:'Contenuto leggibile dell’opera, compresi titoli, prefazioni, epigrafi e appendici.',
      note:'Annotazione collegata a un passaggio che lo spiega, cita o documenta.',
      bibliography:'Elenco autonomo di fonti o opere consultate.',
      index:'Strumento di navigazione o rinvio: sommario, nomi, luoghi, immagini o altre destinazioni.',
      paratext:'Materiale editoriale: frontespizio, copyright, colophon, promozione o dati di edizione.',
      mixed:'Il documento o blocco contiene davvero più funzioni.'
    }
  },
  en: {
    profileTag:'Edition Profile', subtitle: 'EPUB review and Edition Profile', savedLocal: 'In session',
    welcomeTitle: 'Review Segnatura’s classification',
    welcomeBody: 'Corrections apply only to this exact EPUB edition.',
    chooseBook: 'Choose a book', loadingBooks: 'Loading books…', open: 'Open', home:'Home', browseEpub:'Browse EPUB…', importingEpub:'Loading EPUB…', importedEpub:'EPUB selected from disk',
    document: 'EPUB section', originalPage: 'Original EPUB page', previousBlock: 'Previous block', nextBlock: 'Next block', reload: 'Reload',
    wholeDocument: 'Entire EPUB section', documentHint: 'Classify the entire section currently displayed.',
    highlightedBlock: 'Highlighted block', sameAsDocument: 'Use the document category',
    rangeTitle:'Part of this block', rangeHelp:'If the block contains different functions, select the exact text above, choose its category, and add it as a separate range.', saveRange:'Classify selected text', removeRange:'Remove', noRanges:'No specific ranges.', selectRangeFirst:'First select some text in the box above.', rangeSaved:'Range saved', rangeRemoved:'Range removed', mixedRangeHint:'For a mixed block, select and classify its parts separately.',
    optionalNote: 'Optional note', export: 'Export profile', exporting: 'Creating the Edition Profile…', exported: 'Edition Profile exported', savedNextToEpub:'Profile saved next to the EPUB', noApplicableCorrections:'Classify at least one document or block with a concrete category.',
    shortcut: 'Keys 1–6: category · arrows: previous/next block',
    booksFound: (n,root,selected) => selected ? `${n} EPUB ${n === 1 ? 'available' : 'files available'} · ${selected} selected from disk` : `${n} EPUB ${n === 1 ? 'found' : 'files found'} in ${root}`, loading: 'Opening and analysing the EPUB…', saved: 'Saved in this session', saveError: 'Save failed',
    unsavedCorrections:n => `${n} unexported ${n === 1 ? 'correction' : 'corrections'}`, unsavedChanges:'Unexported changes', confirmDiscardUnsaved:'There are unexported changes. Do you really want to leave this book and lose them?',
    noBlocks: 'No text blocks', block: 'Block', characters: 'characters', confidence:'confidence', auxiliary: 'auxiliary', linear: 'linear reading',
    annotated: (done, total) => `${done}/${total} annotated blocks`, noDocumentLabel: 'Classify the document first',
    explore:'Edition Profile editor',
    labels: {work_text:'Text', note:'Note', bibliography:'Bibliography', index:'Index', paratext:'Paratext', mixed:'Mixed'},
    descriptions: {
      work_text:'Readable content of the work, including headings, prefaces, epigraphs and appendices.',
      note:'An annotation tied to another passage that explains, cites or documents it.',
      bibliography:'A standalone list of sources or works consulted.',
      index:'A navigation or reference tool: contents, names, places, illustrations or other destinations.',
      paratext:'Editorial matter: title page, copyright, colophon, promotion or edition data.',
      mixed:'The document or block genuinely contains more than one function.'
    }
  }
};

const AUDIT_I18N = {
  en: {
    independentAudit:'LLM-assisted review', auditTitle:'Ask the LLM to review the complete EPUB', startAudit:'Start complete review', acceptAllAudit:'Accept all applicable suggestions',
    auditNotConfigured:'No LLM backend is configured. Manual Edition Profiles remain available.', auditReady:'The deterministic result is complete. Estimate the calls before starting an LLM review.', auditReadyEstimate:(c,b,d)=>`The complete review will make ${c} model calls for ${b} blocks in ${d} EPUB sections.`, auditRunning:'The LLM is auditing the complete book. You may continue the manual review while it works.', auditWorkingTitle:'LLM is working', auditWorkingDetail:(c,t,e)=>`${c} of ${t} calls completed · elapsed ${e}`, cancelAudit:'Stop review', auditStoppingTitle:'Stopping the review', auditStoppingDetail:'The current model call must finish before the audit can stop.', auditCancelled:'Review stopped by the user.', auditFailed:'Audit failed',
    auditComplete:(d,b,f)=>`Complete audit: ${d} EPUB sections and ${b} blocks submitted · ${f} valid suggestions.`, auditDiscarded:n=>` ${n} malformed suggestions were discarded and logged.`, acceptSuggestion:'Accept', rejectSuggestion:'Reject', applyEditedCategory:'Apply selected category', viewFinding:'Show in EPUB', deterministicResult:'Segnatura result', mixedCategories:'multiple block categories', confirmAcceptAll:'Accept every applicable LLM suggestion? You can still change the resulting Edition Profile before export.', auditDecisionSaved:'Audit decision saved', generalFinding:'General finding'
  },
  it: {
    independentAudit:'Revisione assistita dall’LLM', auditTitle:'Chiedi all’LLM di revisionare l’EPUB completo', startAudit:'Avvia revisione completa', acceptAllAudit:'Accetta tutti i suggerimenti applicabili',
    auditNotConfigured:'Nessun backend LLM configurato. Puoi comunque creare manualmente un Profilo dell’edizione.', auditReady:'Il risultato deterministico è completo. Stima le chiamate prima di avviare una revisione LLM.', auditReadyEstimate:(c,b,d)=>`La revisione completa richiederà ${c} chiamate al modello per ${b} blocchi in ${d} sezioni EPUB.`, auditRunning:'L’LLM sta revisionando l’intero libro. Nel frattempo puoi continuare la revisione manuale.', auditWorkingTitle:'L’LLM sta lavorando', auditWorkingDetail:(c,t,e)=>`${c} chiamate completate su ${t} · tempo trascorso ${e}`, cancelAudit:'Interrompi revisione', auditStoppingTitle:'Interruzione in corso', auditStoppingDetail:'La chiamata al modello già in corso deve terminare prima di fermare la revisione.', auditCancelled:'Revisione interrotta dall’utente.', auditFailed:'Revisione fallita',
    auditComplete:(d,b,f)=>`Revisione completa: ${d} sezioni EPUB e ${b} blocchi inviati · ${f} suggerimenti validi.`, auditDiscarded:n=>` ${n} suggerimenti malformati sono stati scartati e registrati.`, acceptSuggestion:'Accetta', rejectSuggestion:'Rifiuta', applyEditedCategory:'Applica la categoria scelta', viewFinding:'Mostra nell’EPUB', deterministicResult:'Risultato di Segnatura', mixedCategories:'più categorie nei blocchi', confirmAcceptAll:'Accettare tutti i suggerimenti LLM applicabili? Potrai ancora modificare il Profilo dell’edizione prima di esportarlo.', auditDecisionSaved:'Decisione sulla revisione salvata', generalFinding:'Segnalazione generale'
  }
};
for (const locale of Object.keys(AUDIT_I18N)) Object.assign(I18N[locale], AUDIT_I18N[locale]);

const WORKFLOW_I18N = {
  en: {
    stepBook:'Open the book', stepBookHelp:'Segnatura classifies the complete EPUB.', stepAudit:'Choose how to review it', stepAuditHelp:'Manually or with help from an LLM.',
    stepReview:'Validate corrections', stepReviewHelp:'Nothing is applied without your decision.', stepExport:'Export the profile', stepExportHelp:'Only approved corrections are included.',
    bookStructure:'Book structure', reviewQueue:'Edition Profile editor', reviewTitle:'Build the Edition Profile', reviewIntro:'LLM suggestions and manual corrections remain separate and enter the Edition Profile only after your decision.',
    manualCorrection:'Manual review', manualCorrectionHelp:'Inspect the original EPUB and correct any document or block yourself, including while the LLM is working.', exportHelp:'The file contains only corrections you accepted or added manually. Segnatura itself is not rewritten.',
    auditWaiting:'Manual review available · LLM review optional', auditInProgress:'LLM review in progress', auditDone:'LLM review complete', reviewWaiting:'No corrections selected', reviewProgress:(done,total)=>`${done}/${total} LLM decisions`, manualProgress:n=>`${n} manual corrections`, reviewEmpty:'No LLM corrections proposed', exportReady:'Ready to export', exportWaiting:'Select or approve at least one correction',
    auditCurrent:'Segnatura', auditProposed:'LLM proposal', acceptAsProposed:'Accept proposal', acceptSelectedCategory:'Accept selected category', rejectKeepSegnatura:'Reject · keep Segnatura', decisionAccepted:'Proposal accepted', decisionEdited:'Changed and accepted', decisionRejected:'Rejected', noFindings:'The audit found no corrections to propose.'
  },
  it: {
    stepBook:'Apri il libro', stepBookHelp:'Segnatura classifica l’EPUB completo.', stepAudit:'Scegli come revisionarlo', stepAuditHelp:'A mano, oppure con l’aiuto di un LLM.',
    stepReview:'Convalida le correzioni', stepReviewHelp:'Nessuna modifica viene applicata senza la tua decisione.', stepExport:'Esporta il profilo', stepExportHelp:'Entrano solo le correzioni approvate.',
    bookStructure:'Struttura del libro', reviewQueue:'Editor del Profilo dell’edizione', reviewTitle:'Costruisci il Profilo dell’edizione', reviewIntro:'I suggerimenti LLM e le correzioni manuali restano separati ed entrano nel Profilo dell’edizione solo dopo una tua decisione.',
    manualCorrection:'Revisione manuale', manualCorrectionHelp:'Esamina l’EPUB originale e correggi autonomamente documenti o blocchi, anche mentre l’LLM sta lavorando.', exportHelp:'Il file contiene soltanto le correzioni approvate o inserite manualmente. Segnatura non viene riscritta.',
    auditWaiting:'Revisione manuale disponibile · revisione LLM facoltativa', auditInProgress:'Revisione LLM in corso', auditDone:'Revisione LLM completata', reviewWaiting:'Nessuna correzione selezionata', reviewProgress:(done,total)=>`${done}/${total} decisioni LLM`, manualProgress:n=>`${n} correzioni manuali`, reviewEmpty:'Nessuna correzione LLM proposta', exportReady:'Pronto per l’esportazione', exportWaiting:'Seleziona o approva almeno una correzione',
    auditCurrent:'Segnatura', auditProposed:'Proposta LLM', acceptAsProposed:'Accetta la proposta', acceptSelectedCategory:'Accetta la categoria scelta', rejectKeepSegnatura:'Rifiuta · mantieni Segnatura', decisionAccepted:'Proposta accettata', decisionEdited:'Modificata e accettata', decisionRejected:'Rifiutata', noFindings:'La revisione non ha proposto alcuna correzione.'
  }
};
for (const locale of Object.keys(WORKFLOW_I18N)) Object.assign(I18N[locale], WORKFLOW_I18N[locale]);

const PROFILE_UI_I18N = {
  en: {
    welcomeTitle:'Review Segnatura’s classification',
    welcomeBody:'Corrections apply only to this exact EPUB edition.',
    stepBookHelp:'Segnatura classifies the complete EPUB.', stepAudit:'Choose how to review it', stepAuditHelp:'Manually or with help from an LLM.', stepReviewHelp:'Nothing is applied without your approval.', stepExportHelp:'The file contains only corrections you approved.',
    llmMode:'LLM suggestions', manualMode:'Manual review', llmSuggestionList:'LLM suggestions', llmContextHelp:'Estimate and start an LLM review below. Only actionable classification suggestions will appear here.',
    llmSettings:'LLM connection', configureLlm:'Configure LLM', llmConfiguredAs:model=>`LLM ready · ${model || 'model'}`, settings:'Settings', closeSettings:'Close settings', cancel:'Cancel', provider:'Provider', baseUrl:'API base URL', model:'Model', apiKey:'API key', timeout:'Timeout per call', reasoningEffort:'Reasoning effort', advancedOptions:'Advanced options', loadModels:'Connect and load models', loadingModels:'Connecting…', modelsLoaded:n=>`${n} models loaded. Choose one or enter its identifier manually.`, noModelsLoaded:'Connection succeeded, but the endpoint exposed no models. Enter the model identifier manually.', testConfiguration:'Test configuration', testingConfiguration:'Testing structured output…', connectionTestPassed:model=>`Configuration verified with ${model}.`, useConfiguration:'Save configuration',
    apiPrivacy:'A remote provider receives EPUB excerpts. The API key and review state stay only in this running app.',
    reviewHistory:'Review history', noReviews:'No LLM reviews yet', reviewNumber:(n,model,status)=>`Review ${n} · ${model || 'model'} · ${status}`, configurationSaved:'LLM configuration ready',
    estimateAudit:'Estimate calls', estimatingAudit:'Estimating…', estimateAgain:'Estimate a new review', startAudit:'Start complete review', auditWorkingTitle:model=>`${model || 'LLM'} is working`, auditWorkingDetail:(c,total,elapsed)=>`${c} of ${total} calls completed · elapsed ${elapsed}`, auditFinishedTime:elapsed=>`total time ${elapsed}`,
    manualCorrection:'Manual correction', manualCorrectionHelp:'Select Manual review above to inspect every document and block.'
  },
  it: {
    welcomeTitle:'Revisiona la classificazione di Segnatura',
    welcomeBody:'Le correzioni valgono soltanto per questa esatta edizione dell’EPUB.',
    stepBookHelp:'Segnatura classifica l’EPUB completo.', stepAudit:'Scegli come revisionarlo', stepAuditHelp:'A mano, oppure con l’aiuto di un LLM.', stepReviewHelp:'Niente viene applicato senza la tua approvazione.', stepExportHelp:'Il file contiene solo le correzioni che hai approvato.',
    llmMode:'Suggerimenti LLM', manualMode:'Revisione manuale', llmSuggestionList:'Suggerimenti dell’LLM', llmContextHelp:'Stima e avvia qui sotto una revisione LLM. Compariranno soltanto proposte di classificazione che puoi accettare, modificare o rifiutare.',
    llmSettings:'Connessione LLM', configureLlm:'Configura LLM', llmConfiguredAs:model=>`LLM pronto · ${model || 'modello'}`, settings:'Impostazioni', closeSettings:'Chiudi impostazioni', cancel:'Annulla', provider:'Provider', baseUrl:'URL base dell’API', model:'Modello', apiKey:'Chiave API', timeout:'Timeout per chiamata', reasoningEffort:'Livello di ragionamento', advancedOptions:'Opzioni avanzate', loadModels:'Connetti e carica i modelli', loadingModels:'Connessione…', modelsLoaded:n=>`${n} modelli caricati. Scegline uno oppure inserisci manualmente il suo identificatore.`, noModelsLoaded:'Connessione riuscita, ma l’endpoint non ha pubblicato modelli. Inserisci manualmente il loro identificatore.', testConfiguration:'Verifica configurazione', testingConfiguration:'Verifica dell’output strutturato…', connectionTestPassed:model=>`Configurazione verificata con ${model}.`, useConfiguration:'Salva configurazione',
    apiPrivacy:'Un provider remoto riceve estratti dell’EPUB. La chiave API e lo stato della revisione restano soltanto nell’app in esecuzione.',
    reviewHistory:'Cronologia delle revisioni', noReviews:'Nessuna revisione LLM', reviewNumber:(n,model,status)=>`Revisione ${n} · ${model || 'modello'} · ${status}`, configurationSaved:'Configurazione LLM pronta',
    estimateAudit:'Stima le chiamate', estimatingAudit:'Calcolo della stima…', estimateAgain:'Stima una nuova revisione', startAudit:'Avvia revisione completa', auditWorkingTitle:model=>`${model || 'LLM'} sta lavorando`, auditWorkingDetail:(c,total,elapsed)=>`${c} chiamate completate su ${total} · tempo trascorso ${elapsed}`, auditFinishedTime:elapsed=>`tempo totale ${elapsed}`,
    manualCorrection:'Correzione manuale', manualCorrectionHelp:'Seleziona Revisione manuale qui sopra per esaminare ogni documento e blocco.'
  }
};
for (const locale of Object.keys(PROFILE_UI_I18N)) Object.assign(I18N[locale], PROFILE_UI_I18N[locale]);

const SUPPORTED_LOCALES = ['en', 'it'];
const storedLocale = localStorage.getItem('segnatura-gold-locale');
const state = {
  locale: SUPPORTED_LOCALES.includes(storedLocale) ? storedLocale : 'en',
  book: null, documentIndex: 0, blockIndex: 0, annotations: {documents:{}, blocks:{}, ranges:{}}, blockDetail: null, rangePreview:null, audit: null, audits: [], auditTimer: null, contextMode:'llm', llm:null, exportedSignatures:{},
  catalog: [], libraryRoot: ''
};

const $ = id => document.getElementById(id);
const t = key => I18N[state.locale][key];
const labelName = label => I18N[state.locale].labels[label];

function effectiveProfileState() {
  const documents = new Map();
  const blocks = new Map();
  const ranges = new Map();
  const audits = [...(state.audits || [])].sort((a, b) =>
    String(a.created_at || '').localeCompare(String(b.created_at || '')));
  for (const audit of audits) {
    if (audit.status !== 'completed' || !audit.report) continue;
    const findings = new Map(
      (audit.report.findings || []).map(item => [item.id, item]));
    for (const [findingId, decision] of Object.entries(audit.decisions || {})) {
      if (!['accepted', 'edited'].includes(decision.decision)) continue;
      const finding = findings.get(findingId);
      if (!finding?.can_create_edition_profile_override || !decision.category)
        continue;
      const value = [decision.category,
        decision.note || finding.explanation || ''];
      if (finding.scope === 'document') documents.set(finding.href, value);
      else if (finding.scope === 'block') blocks.set(finding.block_id, value);
    }
  }
  for (const [href, item] of Object.entries(state.annotations.documents || {}))
    documents.set(href, [item.label, item.note || '']);
  for (const [blockId, item] of Object.entries(state.annotations.blocks || {}))
    blocks.set(blockId, [item.label, item.note || '']);
  for (const [rangeId, item] of Object.entries(state.annotations.ranges || {}))
    ranges.set(rangeId, [item.label, item.start, item.end, item.note || '']);
  const payload = {
    documents:[...documents.entries()].sort(([a], [b]) => a.localeCompare(b)),
    blocks:[...blocks.entries()].sort(([a], [b]) => a.localeCompare(b)),
    ranges:[...ranges.entries()].sort(([a], [b]) => a.localeCompare(b))
  };
  return {
    count:documents.size + blocks.size + ranges.size,
    signature:JSON.stringify(payload)
  };
}

const EMPTY_PROFILE_SIGNATURE = JSON.stringify({documents:[], blocks:[], ranges:[]});

function unsavedProfileState() {
  const current = effectiveProfileState();
  if (!state.book) return {...current, dirty:false};
  const exported = state.exportedSignatures[state.book.id] ??
    EMPTY_PROFILE_SIGNATURE;
  return {...current, dirty:current.signature !== exported};
}

function renderUnsavedState() {
  const current = unsavedProfileState();
  const node = $('save-state');
  node.style.color = '';
  node.classList.toggle('unsaved', current.dirty);
  if (current.dirty) node.textContent = current.count
    ? t('unsavedCorrections')(current.count) : t('unsavedChanges');
  else node.textContent = current.count ? t('exported') : t('savedLocal');
}

function confirmLeavingBook() {
  return !unsavedProfileState().dirty || confirm(t('confirmDiscardUnsaved'));
}

function applyLocale() {
  document.documentElement.lang = state.locale;
  document.querySelectorAll('[data-locale]').forEach(button => {
    button.classList.toggle('active', button.dataset.locale === state.locale);
    button.setAttribute('aria-pressed', button.dataset.locale === state.locale ? 'true' : 'false');
  });
  document.querySelectorAll('[data-i18n]').forEach(node => {
    const value = t(node.dataset.i18n);
    if (typeof value === 'string') node.textContent = value;
  });
  document.querySelectorAll('[data-i18n-title]').forEach(node => node.title = t(node.dataset.i18nTitle));
  renderLlmConfigurationButton();
  renderLabels();
  if (state.book) renderBook();
  renderLibrarySummary();
}

async function api(url, options={}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try { message = (await response.json()).error || message; } catch (_) {}
    throw new Error(message);
  }
  return response.json();
}

async function loadCatalog() {
  try {
    const data = await api('/api/books');
    state.catalog = data.books;
    state.libraryRoot = data.root;
    const select = $('book-select');
    select.innerHTML = '<option value=""></option>';
    for (const book of data.books) addCatalogOption(book);
    renderLibrarySummary();
  } catch (error) { showWelcomeError(error.message); }
}

function addCatalogOption(book) {
  const option = document.createElement('option');
  option.value = book.path;
  option.textContent = book.folder && book.folder !== '.'
    ? `${book.folder} — ${book.name}` : book.name;
  $('book-select').appendChild(option);
}

async function importEpub(file) {
  if (!file) return;
  showWelcomeError('');
  const button = $('browse-epub');
  button.disabled = true;
  button.textContent = t('importingEpub');
  try {
    const body = new FormData();
    body.append('epub', file, file.name);
    const data = await api('/api/import', {method:'POST', body});
    state.catalog.push(data.book);
    addCatalogOption(data.book);
    $('book-select').value = data.book.path;
    renderLibrarySummary();
    setSaveState(t('importedEpub'));
  } catch (error) {
    showWelcomeError(error.message);
  } finally {
    button.disabled = false;
    button.textContent = t('browseEpub');
    $('epub-file').value = '';
  }
}

async function loadLlmConfiguration() {
  try {
    state.llm = await api('/api/llm/config');
    if (state.llm.model) $('llm-model').value = state.llm.model;
    renderLlmConfigurationButton();
  } catch (_) {
    state.llm = {configured:false};
    renderLlmConfigurationButton();
  }
}

function renderLibrarySummary() {
  if (state.libraryRoot) {
    const selected = state.catalog.filter(book => book.selected_from_disk).length;
    $('library-root').textContent =
      t('booksFound')(state.catalog.length, state.libraryRoot, selected);
  }
}

function showWelcomeError(message) {
  $('welcome-error').hidden = !message;
  $('welcome-error').textContent = message || '';
}

async function openBook() {
  const path = $('book-select').value;
  if (!path) return;
  showWelcomeError('');
  $('open-book').disabled = true;
  $('open-book').textContent = t('loading');
  try {
    const book = await api('/api/open', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({path})});
    state.book = book;
    state.annotations = book.annotations || {documents:{}, blocks:{}, ranges:{}};
    state.annotations.ranges ||= {};
    state.audit = book.audit || null;
    state.audits = book.audits || (book.audit ? [book.audit] : []);
    state.llm = book.llm || {configured:book.audit_available};
    $('llm-model').value = state.llm.model || '';
    renderLlmConfigurationButton();
    state.contextMode = auditFindings().length ? 'llm' : 'manual';
    state.documentIndex = Math.max(0, book.documents.findIndex(doc => doc.blocks.length));
    state.blockIndex = 0;
    $('welcome').hidden = true;
    $('workspace').hidden = false;
    $('change-book').hidden = false;
    renderContextMode();
    renderBook();
    await selectBlock(0, false);
  } catch (error) { showWelcomeError(error.message); }
  finally {
    $('open-book').disabled = false;
    $('open-book').textContent = t('open');
  }
}

function currentDocument() { return state.book?.documents[state.documentIndex]; }
function currentBlock() { return currentDocument()?.blocks[state.blockIndex]; }

function setContextMode(mode) {
  state.contextMode = mode === 'manual' ? 'manual' : 'llm';
  renderContextMode();
}

function renderContextMode() {
  const manual = state.contextMode === 'manual';
  $('mode-manual')?.classList.toggle('active', manual);
  $('mode-llm')?.classList.toggle('active', !manual);
  if ($('manual-context')) $('manual-context').hidden = !manual;
  if ($('llm-context')) $('llm-context').hidden = manual;
  if ($('llm-context-help')) $('llm-context-help').hidden = auditFindings().length > 0;
}

function syncAuditInHistory(audit) {
  if (!audit) return;
  const index = state.audits.findIndex(item => item.run_id === audit.run_id);
  if (index >= 0) state.audits[index] = audit;
  else state.audits.push(audit);
}

function renderAuditHistory() {
  const select = $('audit-history');
  if (!select) return;
  const active = state.audits.find(item =>
    ['running', 'cancelling'].includes(item.status));
  if (active) state.audit = active;
  select.innerHTML = '';
  if (!state.audits.length) {
    const option = document.createElement('option');
    option.value = ''; option.textContent = t('noReviews'); select.appendChild(option);
    select.disabled = true; return;
  }
  select.disabled = Boolean(active);
  state.audits.forEach((audit, index) => {
    const option = document.createElement('option');
    option.value = audit.run_id;
    const model = audit.report?.models?.[0] || audit.requested_model;
    option.textContent = t('reviewNumber')(index + 1, model, audit.status);
    select.appendChild(option);
  });
  select.value = state.audit?.run_id || state.audits.at(-1)?.run_id || '';
}

function renderBook() {
  if (!state.book) return;
  $('book-title').textContent = state.book.title;
  $('book-meta').textContent = [state.book.language, state.book.publisher, `EPUB ${state.book.epub_version}`].filter(Boolean).join(' · ');
  const select = $('document-select');
  select.innerHTML = '';
  state.book.documents.forEach((doc, index) => {
    const option = document.createElement('option');
    option.value = index;
    option.textContent = `${index + 1}. ${doc.title}`;
    select.appendChild(option);
  });
  select.value = state.documentIndex;
  renderDocument();
}

function renderDocument() {
  const doc = currentDocument();
  if (!doc) return;
  $('document-select').value = state.documentIndex;
  $('document-meta').textContent = `${doc.position}/${state.book.documents.length} · ${doc.blocks.length} ${t('block').toLowerCase()} · ${doc.linear ? t('linear') : t('auxiliary')}`;
  $('annotation-document-title').textContent = doc.title;
  $('document-deterministic').textContent = `${t('deterministicResult')}: ${doc.deterministic_category ? labelName(doc.deterministic_category) : t('mixedCategories')}`;
  const list = $('block-list');
  list.innerHTML = '';
  doc.blocks.forEach((block, index) => {
    const item = document.createElement('li');
    const button = document.createElement('button');
    const suggested = unresolvedFindingForBlock(block.id);
    const hasRange = Object.values(state.annotations.ranges || {})
      .some(range => range.block_id === block.id);
    button.className = `${index === state.blockIndex ? 'active ' : ''}${state.annotations.blocks[block.id] || hasRange ? 'done ' : ''}${suggested ? 'audit-suggestion' : ''}`;
    const confidence = Number.isFinite(block.deterministic_confidence)
      ? `${Math.round(block.deterministic_confidence * 100)}%` : '—';
    const category = block.deterministic_category
      ? labelName(block.deterministic_category) : '—';
    button.innerHTML = `<strong>${block.position}. ${escapeHtml(block.title || block.shape)}</strong><span class="block-classification">${escapeHtml(category)} · ${escapeHtml(confidence)}</span><small>${escapeHtml(block.shape)} · ${block.characters} ${t('characters')}</small>`;
    button.onclick = () => selectBlock(index);
    item.appendChild(button); list.appendChild(item);
  });
  const annotated = doc.blocks.filter(block => state.annotations.blocks[block.id] ||
    Object.values(state.annotations.ranges || {}).some(range => range.block_id === block.id)).length;
  $('progress-bar').style.width = `${doc.blocks.length ? annotated / doc.blocks.length * 100 : 0}%`;
  $('progress-text').textContent = t('annotated')(annotated, doc.blocks.length);
  renderLabels();
  const block = currentBlock();
  $('block-deterministic').textContent = block?.deterministic_category
    ? `${t('deterministicResult')}: ${labelName(block.deterministic_category)}` : '';
  renderRanges();
  renderAudit();
}

async function selectBlock(index, reloadDocument=true) {
  const doc = currentDocument();
  if (!doc || !doc.blocks.length) {
    $('block-heading').textContent = t('noBlocks');
    $('block-text').textContent = '';
    $('epub-frame').src = `/epub/${state.book.id}/${encodePath(doc.href)}`;
    return;
  }
  state.blockIndex = Math.max(0, Math.min(index, doc.blocks.length - 1));
  state.rangePreview = null;
  const block = currentBlock();
  state.blockDetail = await api(`/api/books/${state.book.id}/blocks/${block.id}`);
  $('block-heading').textContent = `${t('block')} ${block.position}/${doc.blocks.length} · ${block.shape}`;
  $('block-text').textContent = state.blockDetail.text;
  $('reader-location').textContent = `${doc.title} · ${block.position}/${doc.blocks.length}`;
  $('annotation-note').value = state.annotations.blocks[block.id]?.note || '';
  const src = `/epub/${state.book.id}/${encodePath(doc.href)}?block=${encodeURIComponent(block.id)}`;
  if (reloadDocument || $('epub-frame').src !== new URL(src, location.href).href) $('epub-frame').src = src;
  renderDocument();
  document.querySelector('.block-list button.active')?.scrollIntoView({block:'nearest'});
}

function encodePath(path) { return path.split('/').map(encodeURIComponent).join('/'); }
function escapeHtml(value) {
  const div = document.createElement('div'); div.textContent = value ?? ''; return div.innerHTML;
}

function renderLabels() {
  for (const scope of ['document', 'block']) {
    const container = $(`${scope}-labels`);
    if (!container) continue;
    container.innerHTML = '';
    const selected = scope === 'document'
      ? state.annotations.documents[currentDocument()?.href]?.label
      : state.annotations.blocks[currentBlock()?.id]?.label;
    LABELS.forEach((label, index) => {
      const button = document.createElement('button');
      button.className = `label-button ${label === 'mixed' ? 'special' : ''} ${selected === label ? 'selected' : ''}`;
      button.textContent = `${index + 1}. ${labelName(label)}`;
      button.title = I18N[state.locale].descriptions[label];
      button.onclick = () => saveAnnotation(scope, label);
      container.appendChild(button);
    });
  }
}

function rangesForCurrentBlock() {
  const block = currentBlock();
  if (!block) return [];
  return Object.values(state.annotations.ranges || {})
    .filter(range => range.block_id === block.id)
    .sort((a, b) => a.start - b.start || a.end - b.end);
}

function syncReaderRanges() {
  const frame = $('epub-frame');
  if (!frame?.contentWindow) return;
  frame.contentWindow.postMessage({
    type:'segnatura-ranges',
    saved:rangesForCurrentBlock().map(range => ({
      start:range.start, end:range.end
    })),
    preview:state.rangePreview
  }, '*');
}

function renderRanges() {
  const category = $('range-category');
  const list = $('range-list');
  if (!category || !list) return;
  const selectedCategory = category.value || 'note';
  category.innerHTML = '';
  LABELS.slice(0, 5).forEach(label => {
    const option = document.createElement('option');
    option.value = label; option.textContent = labelName(label);
    category.appendChild(option);
  });
  category.value = LABELS.slice(0, 5).includes(selectedCategory)
    ? selectedCategory : 'note';
  list.innerHTML = '';
  const ranges = rangesForCurrentBlock();
  if (!ranges.length) {
    const empty = document.createElement('p');
    empty.className = 'muted'; empty.textContent = t('noRanges');
    list.appendChild(empty);
    syncReaderRanges();
    return;
  }
  for (const range of ranges) {
    const row = document.createElement('div'); row.className = 'range-item';
    const content = document.createElement('div');
    const heading = document.createElement('strong');
    heading.textContent = `${labelName(range.label)} · ${range.start}–${range.end}`;
    const excerpt = document.createElement('small');
    excerpt.textContent = state.blockDetail?.text.slice(range.start, range.end) || '';
    content.append(heading, excerpt);
    const remove = document.createElement('button');
    remove.className = 'quiet'; remove.textContent = t('removeRange');
    remove.onclick = () => removeRange(range.range_id);
    row.append(content, remove); list.appendChild(row);
  }
  syncReaderRanges();
}

function selectedTextOffsets(container) {
  const selection = window.getSelection();
  if (!selection || selection.rangeCount !== 1 || selection.isCollapsed) return null;
  const selected = selection.getRangeAt(0);
  if (!container.contains(selected.startContainer) ||
      !container.contains(selected.endContainer)) return null;
  const before = document.createRange();
  before.selectNodeContents(container);
  before.setEnd(selected.startContainer, selected.startOffset);
  let start = before.toString().length;
  let text = selected.toString();
  const leading = text.length - text.trimStart().length;
  const trailing = text.length - text.trimEnd().length;
  start += leading;
  const end = start + text.length - leading - trailing;
  return end > start ? {start, end} : null;
}

function previewSelectedRange() {
  const offsets = selectedTextOffsets($('block-text'));
  state.rangePreview = offsets;
  syncReaderRanges();
}

async function saveSelectedRange() {
  if (!state.book || !currentBlock() || !state.blockDetail) return;
  const offsets = selectedTextOffsets($('block-text'));
  if (!offsets) {
    $('range-error').hidden = false;
    $('range-error').textContent = t('selectRangeFirst');
    return;
  }
  $('range-error').hidden = true;
  try {
    const response = await api(`/api/books/${state.book.id}/annotations/range`, {
      method:'PUT', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({
        block_id:currentBlock().id, start:offsets.start, end:offsets.end,
        label:$('range-category').value, note:''
      })
    });
    state.annotations.ranges[response.range.range_id] = response.range;
    state.rangePreview = null;
    window.getSelection()?.removeAllRanges();
    setSaveState(t('rangeSaved'));
    renderDocument();
  } catch (error) {
    $('range-error').hidden = false;
    $('range-error').textContent = error.message;
  }
}

async function removeRange(rangeId) {
  try {
    await api(`/api/books/${state.book.id}/annotations/range/${rangeId}`,
      {method:'DELETE'});
    delete state.annotations.ranges[rangeId];
    setSaveState(t('rangeRemoved'));
    renderDocument();
  } catch (error) { setSaveState(error.message, true); }
}

async function saveAnnotation(scope, label) {
  if (!state.book) return;
  const doc = currentDocument();
  const block = currentBlock();
  if (scope === 'block' && !block) return;
  if (scope === 'block' && label === 'mixed') {
    setSaveState(t('mixedRangeHint'));
  }
  const note = scope === 'block' ? $('annotation-note').value : '';
  const payload = scope === 'document'
    ? {href:doc.href, label, note}
    : {block_id:block.id, label, note};
  setSaveState(t('savedLocal'));
  try {
    await api(`/api/books/${state.book.id}/annotations/${scope}`, {
      method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)
    });
    const record = {...payload, updated_at:new Date().toISOString()};
    if (scope === 'document') state.annotations.documents[doc.href] = record;
    else state.annotations.blocks[block.id] = {...record, href:doc.href, fingerprint:state.blockDetail.fingerprint, xpath:state.blockDetail.xpath};
    setSaveState(t('saved'));
    renderDocument();
  } catch (_) { setSaveState(t('saveError'), true); }
}

function auditFindings() {
  return (state.audit?.report?.findings || []).filter(
    item => item.can_create_edition_profile_override);
}
function auditDecisions() { return state.audit?.decisions || {}; }
function auditElapsedSeconds() {
  const started = Date.parse(state.audit?.created_at || '');
  const completed = Date.parse(state.audit?.completed_at || '');
  const end = Number.isFinite(completed) ? completed : Date.now();
  return Number.isFinite(started)
    ? Math.max(0, Math.floor((end - started) / 1000)) : 0;
}
function formatDuration(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) return '';
  seconds = Math.round(seconds);
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${String(seconds % 60).padStart(2, '0')}`;
}
function unresolvedFindingForBlock(blockId) {
  return auditFindings().some(item => item.block_id === blockId && !auditDecisions()[item.id]);
}

function setWorkflowStep(id, status) {
  const node = $(id);
  if (!node) return;
  node.classList.toggle('active', status === 'active');
  node.classList.toggle('done', status === 'done');
}

function renderWorkflow() {
  if (!state.book) return;
  const findings = auditFindings();
  const decisions = auditDecisions();
  const decided = findings.filter(item => decisions[item.id]).length;
  const auditComplete = state.audit?.status === 'completed';
  const auditRunning = ['running', 'cancelling'].includes(state.audit?.status);
  const reviewComplete = auditComplete && decided === findings.length;
  const manualCorrectionCount = Object.keys(state.annotations.documents || {}).length +
    Object.keys(state.annotations.blocks || {}).length +
    Object.keys(state.annotations.ranges || {}).length;
  const hasManualCorrections = manualCorrectionCount > 0;
  const hasApprovedAuditCorrection = state.audits.some(audit => {
    const auditFindings = audit.report?.findings || [];
    return auditFindings.some(item =>
      ['accepted', 'edited'].includes(audit.decisions?.[item.id]?.decision));
  });
  const canExport = hasManualCorrections || hasApprovedAuditCorrection;

  $('workflow-book-status').textContent = state.book.title;
  $('workflow-audit-status').textContent = auditRunning
    ? t('auditInProgress') : (auditComplete ? t('auditDone') : t('auditWaiting'));
  $('workflow-review-status').textContent = auditComplete
    ? (findings.length ? t('reviewProgress')(decided, findings.length) : t('reviewEmpty'))
    : (hasManualCorrections ? t('manualProgress')(manualCorrectionCount) : t('reviewWaiting'));
  $('workflow-export-status').textContent = canExport ? t('exportReady') : t('exportWaiting');
  $('export-book').hidden = auditRunning;
  $('export-book').disabled = !canExport;

  setWorkflowStep('workflow-book', 'done');
  setWorkflowStep('workflow-audit', auditRunning ? 'active'
    : (auditComplete || hasManualCorrections ? 'done' : 'active'));
  setWorkflowStep('workflow-review', reviewComplete || hasManualCorrections ? 'done' : (auditComplete ? 'active' : 'waiting'));
  setWorkflowStep('workflow-export', canExport ? 'active' : 'waiting');

  if ($('review-count')) $('review-count').textContent = auditComplete
    ? (findings.length ? t('reviewProgress')(decided, findings.length) : t('reviewEmpty'))
    : (hasManualCorrections ? t('manualProgress')(manualCorrectionCount) : t('reviewWaiting'));
  if ($('review-progress-bar')) $('review-progress-bar').style.width = `${findings.length ? decided / findings.length * 100 : (hasManualCorrections || auditComplete ? 100 : 0)}%`;
  renderUnsavedState();
}

function findingLocation(item) {
  if (item.scope === 'book') return t('generalFinding');
  const doc = state.book?.documents.find(document => document.href === item.href);
  if (!doc) return item.href || t('generalFinding');
  if (!item.block_id) return doc.title;
  const block = doc.blocks.find(candidate => candidate.id === item.block_id);
  return `${doc.title} · ${t('block')} ${block?.position || ''}`;
}

function navigateToFinding(item) {
  if (!state.book || item.scope === 'book') return;
  const documentIndex = state.book.documents.findIndex(doc => doc.href === item.href);
  if (documentIndex < 0) return;
  state.documentIndex = documentIndex;
  const doc = state.book.documents[documentIndex];
  state.blockIndex = item.block_id
    ? Math.max(0, doc.blocks.findIndex(block => block.id === item.block_id)) : 0;
  renderBook();
  selectBlock(state.blockIndex);
}

function renderAudit() {
  if (!state.book) return;
  renderAuditHistory();
  const availableFindings = auditFindings();
  const button = $('start-audit');
  const estimateButton = $('estimate-audit');
  const acceptAll = $('accept-all-audit');
  const status = $('audit-status');
  const activity = $('audit-activity');
  const cancelButton = $('cancel-audit');
  const container = $('audit-findings');
  container.innerHTML = '';
  const working = ['running', 'cancelling'].includes(state.audit?.status);
  activity.hidden = !working;
  renderWorkflow();
  button.disabled = !state.book.audit_available || working;
  button.hidden = true;
  estimateButton.disabled = working;
  estimateButton.hidden = working || !state.book.audit_available;
  estimateButton.classList.toggle(
    'estimate-action', !state.audit && !state.book.audit_estimate);
  estimateButton.textContent = (state.audit || state.book.audit_estimate)
    ? t('estimateAgain') : t('estimateAudit');
  acceptAll.hidden = true;

  if (!state.book.audit_available) {
    status.textContent = t('auditNotConfigured');
    estimateButton.hidden = true;
    return;
  }
  if (!state.audit) {
    const estimate = state.book.audit_estimate;
    status.textContent = estimate
      ? t('auditReadyEstimate')(
          estimate.total_calls, estimate.blocks, estimate.documents)
      : t('auditReady');
    button.hidden = !estimate;
    return;
  }
  if (working) {
    status.textContent = t('auditRunning');
    const current = state.audit.progress_current || 0;
    const total = state.audit.progress_total || state.book.audit_estimate?.total_calls || 0;
    const elapsed = auditElapsedSeconds();
    const stopping = state.audit.status === 'cancelling';
    const model = state.audit.requested_model || state.llm?.model || '';
    $('audit-activity-title').textContent = stopping
      ? t('auditStoppingTitle') : t('auditWorkingTitle')(model);
    $('audit-activity-detail').textContent = stopping
      ? t('auditStoppingDetail')
      : t('auditWorkingDetail')(current, total, formatDuration(elapsed));
    $('audit-progress-bar').style.width = `${total ? current / total * 100 : 0}%`;
    cancelButton.disabled = stopping;
    cancelButton.hidden = stopping;
    scheduleAuditPoll();
    return;
  }
  if (state.audit.status === 'cancelled') {
    status.textContent = t('auditCancelled');
    button.hidden = !state.book.audit_estimate;
    return;
  }
  if (state.audit.status === 'failed') {
    status.textContent = `${t('auditFailed')}: ${state.audit.error || ''}`;
    button.hidden = !state.book.audit_estimate;
    return;
  }
  const report = state.audit.report;
  if (!report) return;
  const coverage = report.coverage;
  const documents = coverage.documents_submitted ?? coverage.documents_audited;
  const blocks = coverage.blocks_submitted ?? coverage.blocks_audited;
  const discarded = report.statistics?.discarded_findings || 0;
  status.textContent = t('auditComplete')(
    documents, blocks, availableFindings.length) +
    (discarded ? t('auditDiscarded')(discarded) : '') +
    ` · ${t('auditFinishedTime')(formatDuration(auditElapsedSeconds()))}`;
  button.hidden = !state.book.audit_estimate;
  acceptAll.hidden = true;

  if (!availableFindings.length) {
    const empty = document.createElement('p');
    empty.className = 'audit-empty'; empty.textContent = t('noFindings');
    container.appendChild(empty);
  }

  for (const item of availableFindings) {
    const decision = auditDecisions()[item.id];
    const card = document.createElement('article');
    card.className = `audit-finding ${decision ? 'decided' : ''}`;
    const heading = document.createElement('strong');
    heading.textContent = findingLocation(item);
    const meta = document.createElement('small');
    meta.textContent = `${item.severity} · ${Math.round(item.confidence * 100)}%`;
    const comparison = document.createElement('div'); comparison.className = 'audit-comparison';
    const current = document.createElement('div');
    current.innerHTML = `<small>${escapeHtml(t('auditCurrent'))}</small><strong>${escapeHtml(item.current_category ? labelName(item.current_category) : '—')}</strong>`;
    const arrow = document.createElement('span'); arrow.className = 'comparison-arrow'; arrow.textContent = '→';
    const proposed = document.createElement('div');
    proposed.innerHTML = `<small>${escapeHtml(t('auditProposed'))}</small><strong>${escapeHtml(item.proposed_category ? labelName(item.proposed_category) : item.kind)}</strong>`;
    comparison.append(current, arrow, proposed);
    const explanation = document.createElement('p'); explanation.textContent = item.explanation;
    card.append(heading, meta, comparison, explanation);
    if (decision) {
      const decisionState = document.createElement('div');
      decisionState.className = `decision-state ${decision.decision}`;
      decisionState.textContent = decision.decision === 'accepted' ? t('decisionAccepted')
        : (decision.decision === 'edited' ? t('decisionEdited') : t('decisionRejected'));
      card.appendChild(decisionState);
    }
    if (item.scope !== 'book') {
      const show = document.createElement('button'); show.className = 'quiet'; show.textContent = t('viewFinding');
      show.onclick = () => navigateToFinding(item); card.appendChild(show);
    }
    const controls = document.createElement('div'); controls.className = 'audit-finding-controls';
    if (item.can_create_edition_profile_override) {
      const select = document.createElement('select');
      for (const category of LABELS.slice(0, 5)) {
        const option = document.createElement('option'); option.value = category; option.textContent = labelName(category);
        option.selected = category === (decision?.category || item.proposed_category); select.appendChild(option);
      }
      const accept = document.createElement('button'); accept.className = 'accept'; accept.textContent = t('acceptAsProposed');
      accept.onclick = () => decideAuditFinding(item.id, 'accepted');
      const edit = document.createElement('button'); edit.className = 'edit'; edit.textContent = t('acceptSelectedCategory');
      edit.onclick = () => decideAuditFinding(item.id, 'edited', select.value);
      controls.append(select, accept, edit);
    }
    const reject = document.createElement('button'); reject.className = 'reject'; reject.textContent = t('rejectKeepSegnatura');
    reject.onclick = () => decideAuditFinding(item.id, 'rejected'); controls.appendChild(reject);
    card.appendChild(controls); container.appendChild(card);
  }
}

async function startAudit() {
  if (!state.book?.audit_available || !state.book.audit_estimate) return;
  $('start-audit').disabled = true;
  try {
    state.audit = await api(`/api/books/${state.book.id}/audit`, {method:'POST'});
    state.book.audit_estimate = null;
    syncAuditInHistory(state.audit);
    setContextMode('llm');
    renderAudit();
  } catch (error) { setSaveState(error.message, true); renderAudit(); }
}

async function estimateAudit() {
  if (!state.book?.audit_available) return;
  const button = $('estimate-audit');
  button.disabled = true;
  button.textContent = t('estimatingAudit');
  try {
    state.book.audit_estimate = await api(
      `/api/books/${state.book.id}/audit-estimate`);
    renderAudit();
  } catch (error) {
    setSaveState(error.message, true);
  } finally {
    button.disabled = false;
    button.textContent = (state.audit || state.book?.audit_estimate)
      ? t('estimateAgain') : t('estimateAudit');
  }
}

async function cancelAudit() {
  if (!state.audit?.run_id || !['running','cancelling'].includes(state.audit.status)) return;
  $('cancel-audit').disabled = true;
  try {
    state.audit = await api(`/api/audits/${state.audit.run_id}/cancel`, {method:'POST'});
    renderAudit();
  } catch (error) { setSaveState(error.message, true); renderAudit(); }
}

function scheduleAuditPoll() {
  if (state.auditTimer || !state.audit?.run_id) return;
  state.auditTimer = setTimeout(async () => {
    state.auditTimer = null;
    try {
      const previousStatus = state.audit?.status;
      state.audit = await api(`/api/audits/${state.audit.run_id}`);
      syncAuditInHistory(state.audit);
      if (previousStatus !== state.audit.status && !['running','cancelling'].includes(state.audit.status)) {
        renderDocument();
      } else {
        renderAudit();
      }
    } catch (error) { setSaveState(error.message, true); }
  }, 2500);
}

async function decideAuditFinding(findingId, decision, category=null) {
  try {
    state.audit = await api(`/api/audits/${state.audit.run_id}/findings/${findingId}`, {
      method:'PUT', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({decision, category})
    });
    syncAuditInHistory(state.audit);
    setSaveState(t('auditDecisionSaved'));
    renderDocument();
  } catch (error) { setSaveState(error.message, true); }
}

async function acceptAllAuditFindings() {
  if (!state.audit?.run_id || !confirm(t('confirmAcceptAll'))) return;
  try {
    state.audit = await api(`/api/audits/${state.audit.run_id}/accept-all`, {method:'POST'});
    syncAuditInHistory(state.audit);
    setSaveState(t('auditDecisionSaved'));
    renderDocument();
  } catch (error) { setSaveState(error.message, true); }
}

async function configureLlm() {
  const button = $('save-llm-config');
  button.disabled = true;
  try {
    state.llm = await api('/api/llm/config', {
      method:'PUT', headers:{'Content-Type':'application/json'},
      body:JSON.stringify(llmFormData())
    });
    $('llm-api-key').value = '';
    if (state.book) {
      state.book.audit_available = true;
      state.book.audit_estimate = null;
    }
    $('llm-dialog').close();
    renderLlmConfigurationButton();
    setSaveState(t('configurationSaved'));
    renderAudit();
  } catch (error) { setSaveState(error.message, true); }
  finally { button.disabled = false; }
}

function llmFormData() {
  return {
    provider:$('llm-provider').value,
    base_url:$('llm-base-url').value,
    model:$('llm-model').value,
    api_key:$('llm-api-key').value,
    timeout:Number($('llm-timeout').value),
    reasoning_effort:$('llm-reasoning').value
  };
}

function setLlmConnectionStatus(message, error=false) {
  const status = $('llm-connection-status');
  status.textContent = message || '';
  status.classList.toggle('error', error);
}

async function loadLlmModels() {
  const button = $('load-llm-models');
  button.disabled = true;
  button.textContent = t('loadingModels');
  setLlmConnectionStatus(t('loadingModels'));
  try {
    const result = await api('/api/llm/models', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify(llmFormData())
    });
    const options = $('llm-model-options');
    options.innerHTML = '';
    for (const model of result.models || []) {
      const option = document.createElement('option');
      option.value = model;
      options.appendChild(option);
    }
    setLlmConnectionStatus(result.models?.length
      ? t('modelsLoaded')(result.models.length) : t('noModelsLoaded'));
  } catch (error) {
    setLlmConnectionStatus(error.message, true);
  } finally {
    button.disabled = false;
    button.textContent = t('loadModels');
  }
}

async function testLlmConfiguration() {
  const button = $('test-llm-config');
  button.disabled = true;
  button.textContent = t('testingConfiguration');
  setLlmConnectionStatus(t('testingConfiguration'));
  try {
    const result = await api('/api/llm/test', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify(llmFormData())
    });
    setLlmConnectionStatus(t('connectionTestPassed')(result.model));
  } catch (error) {
    setLlmConnectionStatus(error.message, true);
  } finally {
    button.disabled = false;
    button.textContent = t('testConfiguration');
  }
}

function renderLlmConfigurationButton() {
  const button = $('open-llm-settings');
  if (!button) return;
  button.textContent = state.llm?.configured
    ? t('llmConfiguredAs')(state.llm.model) : t('configureLlm');
  button.classList.toggle('configured', Boolean(state.llm?.configured));
}

function openLlmSettings() {
  const dialog = $('llm-dialog');
  setLlmConnectionStatus('');
  if (state.llm?.provider) {
    $('llm-provider').value = state.llm.provider === 'LM Studio'
      ? 'lm_studio' : 'openai_compatible';
  }
  if (state.llm?.model) $('llm-model').value = state.llm.model;
  if (typeof dialog.showModal === 'function') dialog.showModal();
  else dialog.setAttribute('open', '');
}

function closeLlmSettings() {
  const dialog = $('llm-dialog');
  if (typeof dialog.close === 'function') dialog.close();
  else dialog.removeAttribute('open');
}

function setSaveState(text, error=false) {
  $('save-state').textContent = text;
  $('save-state').classList.remove('unsaved');
  $('save-state').style.color = error ? '#e5484d' : '';
}

async function inheritDocument() {
  const label = state.annotations.documents[currentDocument()?.href]?.label;
  if (!label) { setSaveState(t('noDocumentLabel'), true); return; }
  await saveAnnotation('block', label);
}

function moveBlock(delta) {
  if (!state.book) return;
  const locations = [];
  state.book.documents.forEach((doc, documentIndex) =>
    doc.blocks.forEach((_, blockIndex) => locations.push({documentIndex, blockIndex})));
  const current = locations.findIndex(x =>
    x.documentIndex === state.documentIndex && x.blockIndex === state.blockIndex);
  const target = locations[current + delta];
  if (!target) return;
  state.documentIndex = target.documentIndex;
  state.blockIndex = target.blockIndex;
  renderBook();
  selectBlock(target.blockIndex);
}

async function exportEditionProfile() {
  if (!state.book) return;
  setSaveState(t('exporting'));
  try {
    const response = await fetch(`/api/books/${state.book.id}/export`);
    if (!response.ok) {
      let message = `${response.status} ${response.statusText}`;
      try {
        const data = await response.json();
        message = data.code === 'no_applicable_corrections'
          ? t('noApplicableCorrections') : (data.error || message);
      } catch (_) {}
      throw new Error(message);
    }
    if (response.headers.get('X-Segnatura-Saved-Next-To-EPUB') === '1') {
      state.exportedSignatures[state.book.id] =
        effectiveProfileState().signature;
      setSaveState(t('savedNextToEpub'));
    } else {
      const disposition = response.headers.get('Content-Disposition') || '';
      const match = disposition.match(/filename="([^"]+)"/);
      const filename = match?.[1] || `${state.book.title}.segnatura.json`;
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement('a');
      link.href = url; link.download = filename; link.click();
      URL.revokeObjectURL(url);
      state.exportedSignatures[state.book.id] =
        effectiveProfileState().signature;
      setSaveState(t('exported'));
    }
  } catch (error) {
    setSaveState(error.message || t('saveError'), true);
  }
}

document.querySelectorAll('[data-locale]').forEach(button => {
  button.addEventListener('click', () => {
    state.locale = button.dataset.locale;
    localStorage.setItem('segnatura-gold-locale', state.locale);
    applyLocale();
  });
});
$('open-book').addEventListener('click', openBook);
$('book-select').addEventListener('keydown', event => { if (event.key === 'Enter') openBook(); });
$('browse-epub').addEventListener('click', () => $('epub-file').click());
$('epub-file').addEventListener('change', event => importEpub(event.target.files?.[0]));
$('change-book').addEventListener('click', () => {
  if (!confirmLeavingBook()) return;
  if (state.auditTimer) clearTimeout(state.auditTimer);
  state.auditTimer = null;
  $('workspace').hidden = true;
  $('welcome').hidden = false;
  $('change-book').hidden = true;
  state.book = null;
  state.audit = null;
  state.audits = [];
  setSaveState(t('savedLocal'));
});
$('mode-llm').addEventListener('click', () => setContextMode('llm'));
$('mode-manual').addEventListener('click', () => setContextMode('manual'));
$('audit-history').addEventListener('change', event => {
  state.audit = state.audits.find(item => item.run_id === event.target.value) || null;
  renderDocument();
});
$('open-llm-settings').addEventListener('click', openLlmSettings);
$('close-llm-settings').addEventListener('click', closeLlmSettings);
$('cancel-llm-settings').addEventListener('click', closeLlmSettings);
$('llm-dialog').addEventListener('click', event => {
  if (event.target === $('llm-dialog')) closeLlmSettings();
});
$('save-llm-config').addEventListener('click', configureLlm);
$('load-llm-models').addEventListener('click', loadLlmModels);
$('test-llm-config').addEventListener('click', testLlmConfiguration);
$('llm-provider').addEventListener('change', event => {
  if (event.target.value === 'lm_studio')
    $('llm-base-url').value = 'http://localhost:1234/v1';
  setLlmConnectionStatus('');
});
$('document-select').addEventListener('change', event => {
  state.documentIndex = Number(event.target.value); state.blockIndex = 0; renderDocument(); selectBlock(0);
});
$('previous-block').addEventListener('click', () => moveBlock(-1));
$('next-block').addEventListener('click', () => moveBlock(1));
$('reload-page').addEventListener('click', () => { const frame = $('epub-frame'); frame.src = frame.src; });
$('epub-frame').addEventListener('load', syncReaderRanges);
$('inherit-document').addEventListener('click', inheritDocument);
$('save-range').addEventListener('click', saveSelectedRange);
$('block-text').addEventListener('pointerup', previewSelectedRange);
$('block-text').addEventListener('keyup', previewSelectedRange);
$('estimate-audit').addEventListener('click', estimateAudit);
$('start-audit').addEventListener('click', startAudit);
$('cancel-audit').addEventListener('click', cancelAudit);
$('accept-all-audit').addEventListener('click', acceptAllAuditFindings);
$('annotation-note').addEventListener('change', () => {
  const label = state.annotations.blocks[currentBlock()?.id]?.label;
  if (label) saveAnnotation('block', label);
});
$('export-book').addEventListener('click', exportEditionProfile);
window.addEventListener('beforeunload', event => {
  if (!unsavedProfileState().dirty) return;
  event.preventDefault();
  event.returnValue = '';
});
document.addEventListener('keydown', event => {
  if (!state.book || ['TEXTAREA','SELECT','INPUT'].includes(event.target.tagName)) return;
  if (event.key >= '1' && event.key <= '6') saveAnnotation('block', LABELS[Number(event.key) - 1]);
  else if (event.key === 'ArrowLeft') moveBlock(-1);
  else if (event.key === 'ArrowRight') moveBlock(1);
});

applyLocale();
loadCatalog();
loadLlmConfiguration();
