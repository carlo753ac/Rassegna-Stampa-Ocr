import streamlit as st
import fitz  # PyMuPDF
import pytesseract
from PIL import Image
import io

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Rassegna Stampa OCR & Indice", layout="wide", page_icon="📰")

st.title("📰 Rassegna Stampa: Estrazione tramite Indice")
st.markdown("Sfrutta l'indice del PDF per raggruppare le pagine per articolo, esegui l'OCR e genera un nuovo PDF su misura.")

# --- INIZIALIZZAZIONE SESSION STATE ---
if 'articles_data' not in st.session_state:
    st.session_state.articles_data = []
if 'pdf_bytes' not in st.session_state:
    st.session_state.pdf_bytes = None

# --- FUNZIONI ---
@st.cache_data(show_spinner=False)
def process_pdf(file_bytes):
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    toc = doc.get_toc() # Estrae l'indice: [livello, titolo, numero_pagina]
    
    articles_data = []
    
    # Se il PDF non ha un indice, fallback alla divisione per pagina singola
    if not toc:
        st.warning("⚠️ Nessun indice trovato nel PDF! Il programma tratterà ogni pagina come un articolo separato.")
        for i in range(len(doc)):
            toc.append([1, f"Pagina {i+1}", i+1])

    progress_bar = st.progress(0)
    status_text = st.empty()
    
    # Analizza gli articoli basandosi sull'indice
    for i in range(len(toc)):
        livello, titolo, start_page = toc[i]
        start_page_idx = start_page - 1 # PyMuPDF è 0-indexed, l'indice è 1-indexed
        
        # Calcola la fine dell'articolo
        if i < len(toc) - 1:
            next_start_page_idx = toc[i+1][2] - 1
            end_page_idx = next_start_page_idx - 1
        else:
            end_page_idx = len(doc) - 1 # L'ultimo articolo va fino alla fine del PDF
            
        # Sicurezza: se per qualche motivo l'indice è sfasato
        if end_page_idx < start_page_idx:
            end_page_idx = start_page_idx

        status_text.text(f"Elaborazione: '{titolo}' (Pagine {start_page_idx+1}-{end_page_idx+1})...")
        
        # Estrai l'immagine della prima pagina per l'anteprima
        first_page = doc.load_page(start_page_idx)
        pix = first_page.get_pixmap(dpi=100)
        thumb_img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        
        # Esegui OCR su tutte le pagine dell'articolo e unisci il testo
        full_article_text = ""
        for page_num in range(start_page_idx, end_page_idx + 1):
            p = doc.load_page(page_num)
            p_pix = p.get_pixmap(dpi=150)
            p_img = Image.frombytes("RGB", [p_pix.width, p_pix.height], p_pix.samples)
            testo_pagina = pytesseract.image_to_string(p_img, lang="ita")
            full_article_text += testo_pagina + "\n"
            
        articles_data.append({
            "title": titolo,
            "start_page": start_page_idx,
            "end_page": end_page_idx,
            "text": full_article_text,
            "thumbnail": thumb_img
        })
        
        progress_bar.progress((i + 1) / len(toc))
        
    status_text.empty()
    progress_bar.empty()
    doc.close()
    
    return articles_data

def generate_new_pdf(selected_articles):
    """Crea un nuovo PDF unendo gli articoli (e tutte le loro pagine) selezionati."""
    original_doc = fitz.open(stream=st.session_state.pdf_bytes, filetype="pdf")
    new_doc = fitz.open()
    
    for article in selected_articles:
        # Inserisce il range di pagine dell'articolo
        new_doc.insert_pdf(original_doc, from_page=article['start_page'], to_page=article['end_page'])
        
    pdf_out = new_doc.write()
    new_doc.close()
    original_doc.close()
    return pdf_out


# --- INTERFACCIA UTENTE ---

uploaded_file = st.sidebar.file_uploader("Carica la Rassegna Stampa (PDF)", type=["pdf"])

if uploaded_file is not None:
    if st.sidebar.button("Analizza Articoli e OCR"):
        st.session_state.pdf_bytes = uploaded_file.read()
        with st.spinner("Lettura dell'indice e scansione OCR in corso (potrebbe volerci un po')..."):
            st.session_state.articles_data = process_pdf(st.session_state.pdf_bytes)
        st.sidebar.success(f"Analisi completata! Trovati {len(st.session_state.articles_data)} articoli.")

if st.session_state.articles_data:
    st.divider()
    
    # Ricerca
    search_query = st.text_input("🔍 Cerca parola chiave negli articoli (es. 'mercato', 'sindaco'):", "").lower()
    
    # Filtraggio
    filtered_articles = []
    for art in st.session_state.articles_data:
        if search_query in art['text'].lower() or search_query in art['title'].lower():
            filtered_articles.append(art)
            
    if not filtered_articles:
        st.warning("Nessun articolo trovato per la parola chiave inserita.")
    else:
        st.success(f"Trovati {len(filtered_articles)} articoli pertinenti.")
    
    # Form per la selezione
    with st.form("selection_form"):
        selected_articles = []
        
        # Mostra i risultati in una griglia (3 colonne)
        cols = st.columns(3)
        for idx, art_data in enumerate(filtered_articles):
            col = cols[idx % 3]
            with col:
                st.image(art_data['thumbnail'], use_container_width=True)
                st.markdown(f"**{art_data['title']}**")
                
                pagine_totali = (art_data['end_page'] - art_data['start_page']) + 1
                st.caption(f"Pagine: {art_data['start_page'] + 1} - {art_data['end_page'] + 1} ({pagine_totali} pag.)")
                
                # Anteprima testo
                snippet = art_data['text'][:100].replace('\n', ' ') + "..."
                st.info(snippet)
                
                # Checkbox con chiave univoca basata sul titolo e pagina per evitare conflitti
                if st.checkbox("Seleziona Articolo", key=f"check_{art_data['start_page']}_{idx}"):
                    selected_articles.append(art_data)
                    
        st.divider()
        submit_selection = st.form_submit_button("Crea nuovo PDF con articoli selezionati")

    # Esportazione
    if submit_selection:
        if len(selected_articles) > 0:
            # Ordina gli articoli selezionati in base alla loro posizione originale nel PDF
            selected_articles = sorted(selected_articles, key=lambda x: x['start_page'])
            
            with st.spinner("Compilazione del nuovo PDF in corso..."):
                new_pdf_bytes = generate_new_pdf(selected_articles)
                
            st.success(f"PDF generato con successo! ({len(selected_articles)} articoli inclusi)")
            
            st.download_button(
                label="📥 Scarica Rassegna Stampa Personalizzata",
                data=new_pdf_bytes,
                file_name="Rassegna_Personalizzata.pdf",
                mime="application/pdf"
            )
        else:
            st.error("Seleziona almeno un articolo per creare il nuovo PDF.")
