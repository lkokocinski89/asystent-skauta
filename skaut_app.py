import streamlit as st
import pandas as pd
import os
from datetime import date
import re 
from sqlalchemy import text

# --- Ustawienia Aplikacji ---
st.set_page_config(layout="wide", page_title="Asystent Skauta U21")
st.title('Asystent Skauta U21 (Hattrick)')

# --- HACK CSS DO WYŚRODKOWANIA TEKSTU W TABELACH ---
st.markdown(
    """
    <style>
    .rdg-cell { justify-content: center !important; text-align: center !important; }
    .rdg-header-cell { justify-content: center !important; text-align: center !important; }
    </style>
    """,
    unsafe_allow_html=True
)

# === EKRAN LOGOWANIA ===
if 'scout_nick' not in st.session_state:
    st.session_state.scout_nick = ""

scout_nick_input = st.text_input("Podaj swój nick skauta, aby się zalogować:", value=st.session_state.scout_nick)

if st.session_state.scout_nick and not scout_nick_input:
    st.session_state.scout_nick = ""
elif scout_nick_input:
    st.session_state.scout_nick = scout_nick_input

if not st.session_state.scout_nick:
    st.warning("Musisz podać swój nick skauta, aby kontynuować.")
    st.stop()

scout_nick = st.session_state.scout_nick
st.success(f"Zalogowano jako: **{scout_nick}**. Widzisz tylko swoje prywatne dane.")

# --- Inicjalizacja Połączenia z Bazą Danych ---
try:
    conn = st.connection("database", type="sql")
except Exception as e:
    st.error(f"Błąd połączenia z bazą danych: {e}")
    st.stop()
    
if 'player_list_df' not in st.session_state:
    st.session_state['player_list_df'] = pd.DataFrame() 

# --- Funkcja Inicjalizująca Bazę Danych ---
@st.cache_resource
def init_db():
    with conn.session as s:
        # Tabela kontaktów
        s.execute(text('''
            CREATE TABLE IF NOT EXISTS contacts (
                scout_nick TEXT,
                manager_id TEXT,
                nick_managera TEXT,
                imie_nazwisko_zawodnika TEXT,
                id_gracza TEXT,
                status TEXT,
                notatki TEXT,
                data_kontaktu DATE,
                PRIMARY KEY (scout_nick, manager_id) 
            );
        '''))
        # Tabela kupców
        s.execute(text('''
            CREATE TABLE IF NOT EXISTS buyers (
                scout_nick TEXT,
                manager_id TEXT,
                nick_managera TEXT,
                budzet TEXT,
                ilosc_miejsc TEXT,
                status TEXT,
                data_kontaktu DATE,
                notatki TEXT,
                PRIMARY KEY (scout_nick, manager_id)
            );
        '''))
        # Tabela importowanych graczy
        s.execute(text('''
            CREATE TABLE IF NOT EXISTS imported_players (
                scout_nick TEXT,
                "PlayerID" BIGINT,
                "FirstName" TEXT,
                "LastName" TEXT,
                "OwningUserID" TEXT,
                "Age" INT,
                "AgeDays" INT,
                "PlayerForm" INT,
                "StaminaSkill" TEXT,
                "DefenderSkill" TEXT,
                "PlaymakerSkill" TEXT,
                "WingerSkill" TEXT,
                "PassingSkill" TEXT,
                "ScorerSkill" TEXT,
                "SetPiecesSkill" TEXT,
                "TeamTrainerSkill" INT,
                "FormCoachLevels" INT
            );
        '''))
        s.commit()

init_db()

# --- Funkcje Pomocnicze ---
def load_contacts_db(nick):
    df = conn.query("SELECT * FROM contacts WHERE scout_nick = :nick", params={"nick": nick}, ttl=0)
    if not df.empty:
        df['data_kontaktu'] = pd.to_datetime(df['data_kontaktu'])
    return df

def load_buyers_db(nick):
    df = conn.query("SELECT * FROM buyers WHERE scout_nick = :nick", params={"nick": nick}, ttl=0)
    if not df.empty:
        df['data_kontaktu'] = pd.to_datetime(df['data_kontaktu'])
    return df

def load_saved_players(nick):
    df = conn.query('SELECT * FROM imported_players WHERE scout_nick = :nick', params={"nick": nick}, ttl=0)
    return df

def fill_form_callback():
    selected_option = st.session_state.get('player_filler_select', 'Wybierz...')
    match = re.search(r'\(ID: (\d+)\)', selected_option)
    
    if match and not st.session_state.player_list_df.empty:
        try:
            player_id_to_find = int(match.group(1))
            player_data_series = st.session_state.player_list_df[
                st.session_state.player_list_df['PlayerID'].astype(str) == str(player_id_to_find)
            ]
            
            if not player_data_series.empty:
                player_data = player_data_series.iloc[0]
                manager_id = str(player_data['OwningUserID'])
                
                st.session_state.form_manager_id = manager_id
                st.session_state.form_player_name = f"{player_data['FirstName']} {player_data['LastName']}"
                st.session_state.form_player_id = str(player_data['PlayerID'])
                
                df_contacts_local = load_contacts_db(scout_nick) 
                if not df_contacts_local.empty and manager_id in df_contacts_local['manager_id'].astype(str).values:
                    existing_nick = df_contacts_local[
                        df_contacts_local['manager_id'].astype(str) == manager_id
                    ]['nick_managera'].iloc[0]
                    st.session_state.form_manager_nick = existing_nick if pd.notna(existing_nick) else ""
                else:
                    st.session_state.form_manager_nick = ""
            
        except Exception as e:
            print(f"Błąd w fill_form_callback: {e}")
            
    elif selected_option == 'Wybierz...':
        st.session_state.form_manager_id = ""
        st.session_state.form_manager_nick = ""
        st.session_state.form_player_name = ""
        st.session_state.form_player_id = ""


# --- Główna Logika - Ładowanie danych ---
df_contacts = load_contacts_db(scout_nick)
df_buyers = load_buyers_db(scout_nick)

if st.session_state.player_list_df.empty:
    saved_players = load_saved_players(scout_nick)
    if not saved_players.empty:
        st.session_state.player_list_df = saved_players
        st.toast(f"Załadowano {len(saved_players)} graczy z bazy danych.")

status_options_contacts = ['Brak kontaktu', 'Nowy (Do kontaktu)', 'Wysłano HT-mail', 'Odpowiedział (Pozytywnie)', 'Odpowiedział (Negatywnie)', 'Monitorowany', 'Zakończony (Nie pisać)']
status_options_buyers = ['Nowy', 'Zapytany', 'Zainteresowany', 'Kupił', 'Niezainteresowany', 'Do ponowienia']

# === SEKCJA 1: REJESTR KONTAKTÓW (DLA POBOROWYCH) ===
st.header('Rejestr Kontaktów (Poborowi)')
st.markdown("Wpisz ID managera lub **użyj listy na dole**, aby automatycznie wypełnić formularz.")

if 'form_manager_id' not in st.session_state: st.session_state.form_manager_id = ""
if 'form_manager_nick' not in st.session_state: st.session_state.form_manager_nick = ""
if 'form_player_name' not in st.session_state: st.session_state.form_player_name = ""
if 'form_player_id' not in st.session_state: st.session_state.form_player_id = ""
if 'form_status' not in st.session_state: st.session_state.form_status = 'Nowy (Do kontaktu)'
if 'form_notes' not in st.session_state: st.session_state.form_notes = ""
if 'form_date' not in st.session_state: st.session_state.form_date = date.today()

col1, col2 = st.columns(2)
with col1:
    st.text_input('ID Managera (wymagane)', key='form_manager_id')
    st.text_input('Nick Managera (opcjonalnie)', key='form_manager_nick')
with col2:
    st.text_input('Imię Nazwisko Zawodnika (opcjonalnie)', key='form_player_name')
    st.text_input('ID Gracza (opcjonalnie)', key='form_player_id')
    
st.selectbox('Status Kontaktu', status_options_contacts, key='form_status')
st.date_input('Data Kontaktu', key='form_date')
st.text_area('Notatki', placeholder="Wpisz swoje uwagi, linki, ustalenia...", key='form_notes')

submit_button_contact = st.button(label='Zapisz Kontakt')

if submit_button_contact:
    if not st.session_state.form_manager_id:
        st.error('ID Managera jest polem wymaganym!')
    else:
        manager_id_str = str(st.session_state.form_manager_id)
        exists = conn.query(
            "SELECT 1 FROM contacts WHERE scout_nick = :nick AND manager_id = :id",
            params={"nick": scout_nick, "id": manager_id_str},
            ttl=0
        )
        
        with conn.session as s:
            if not exists.empty:
                sql = text("""
                    UPDATE contacts SET 
                    nick_managera = :nick_m, imie_nazwisko_zawodnika = :imie, id_gracza = :id_g, 
                    status = :status, notatki = :notatki, data_kontaktu = :data 
                    WHERE scout_nick = :nick AND manager_id = :id
                """)
                s.execute(sql, params={
                    "nick_m": st.session_state.form_manager_nick, "imie": st.session_state.form_player_name,
                    "id_g": st.session_state.form_player_id, "status": st.session_state.form_status,
                    "notatki": st.session_state.form_notes, "data": st.session_state.form_date,
                    "nick": scout_nick, "id": manager_id_str
                })
                st.success(f'Zaktualizowano: {manager_id_str}')
            else:
                sql = text("""
                    INSERT INTO contacts (scout_nick, manager_id, nick_managera, imie_nazwisko_zawodnika, id_gracza, status, notatki, data_kontaktu)
                    VALUES (:nick, :id, :nick_m, :imie, :id_g, :status, :notatki, :data)
                """)
                s.execute(sql, params={
                    "nick": scout_nick, "id": manager_id_str, "nick_m": st.session_state.form_manager_nick,
                    "imie": st.session_state.form_player_name, "id_g": st.session_state.form_player_id,
                    "status": st.session_state.form_status, "notatki": st.session_state.form_notes,
                    "data": st.session_state.form_date
                })
                st.success(f'Dodano: {manager_id_str}')
            s.commit()
        
        st.session_state.form_manager_id = ""
        st.session_state.form_manager_nick = ""
        st.session_state.form_player_name = ""
        st.session_state.form_player_id = ""
        st.session_state.form_notes = ""
        st.rerun() 


# === SEKCJA 2: WYŚWIETLANIE BAZY KONTAKTÓW ===
st.header('Twoja Baza Kontaktów (Poborowi)')
if df_contacts.empty:
    st.info('Baza pusta.')
else:
    display_columns = ['manager_id', 'nick_managera', 'imie_nazwisko_zawodnika', 'id_gracza', 'status', 'notatki', 'data_kontaktu']
    st.data_editor(df_contacts[display_columns].sort_values(by='data_kontaktu', ascending=False), use_container_width=True)

    # === SEKCJA USUWANIA KONTAKTÓW ===
    with st.expander("🗑️ Zarządzanie / Usuwanie wpisów (Poborowi)"):
        # Lista do wyboru: Nick Managera (ID) - Imię Nazwisko gracza
        delete_options = [
            f"{row['nick_managera'] or 'Bez nicku'} (ID: {row['manager_id']}) - {row['imie_nazwisko_zawodnika'] or '?'}" 
            for i, row in df_contacts.iterrows()
        ]
        selected_delete = st.selectbox("Wybierz wpis do usunięcia:", delete_options, key="delete_contact_select")
        
        if st.button("❌ Usuń wybranego managera z bazy kontaktów"):
            # Wyciągnij ID z tekstu
            match = re.search(r'\(ID: (\d+)\)', selected_delete)
            if match:
                id_to_delete = match.group(1)
                with conn.session as s:
                    s.execute(text("DELETE FROM contacts WHERE scout_nick = :nick AND manager_id = :id"), 
                              params={"nick": scout_nick, "id": id_to_delete})
                    s.commit()
                st.success(f"Usunięto managera o ID: {id_to_delete}")
                st.rerun()

st.divider() 

# === SEKCJA 3: REJESTR KUPCÓW ===
st.header('Rejestr Kupców')
with st.form(key='buyers_form', clear_on_submit=True):
    b_col1, b_col2 = st.columns(2)
    with b_col1:
        b_manager_id = st.text_input('ID Managera (wymagane)')
        b_manager_nick = st.text_input('Nick Managera (opcjonalnie)')
        b_status = st.selectbox('Status Kupca', status_options_buyers, index=0)
    with b_col2:
        b_budget = st.text_input('Budżet (opcjonalnie)')
        b_spots = st.text_input('Ilość Miejsc (opcjonalnie)')
        b_contact_date = st.date_input('Data Kontaktu', value=date.today())
    b_notes = st.text_area('Notatki (Kupiec)', placeholder="Wpisz swoje uwagi...")
    submit_button_buyer = st.form_submit_button(label='Zapisz Kupca')

if submit_button_buyer:
    if not b_manager_id:
        st.error('ID Managera jest polem wymaganym!')
    else:
        b_manager_id_str = str(b_manager_id)
        exists = conn.query("SELECT 1 FROM buyers WHERE scout_nick = :nick AND manager_id = :id", params={"nick": scout_nick, "id": b_manager_id_str}, ttl=0)
        
        with conn.session as s:
            if not exists.empty:
                sql = text("""
                    UPDATE buyers SET nick_managera = :nick_m, budzet = :budzet, ilosc_miejsc = :miejsca,
                    status = :status, notatki = :notatki, data_kontaktu = :data 
                    WHERE scout_nick = :nick AND manager_id = :id
                """)
                s.execute(sql, params={
                    "nick_m": b_manager_nick, "budzet": b_budget, "miejsca": b_spots,
                    "status": b_status, "notatki": b_notes, "data": b_contact_date,
                    "nick": scout_nick, "id": b_manager_id_str
                })
                st.success(f'Zaktualizowano kupca: {b_manager_id_str}')
            else:
                sql = text("INSERT INTO buyers (scout_nick, manager_id, nick_managera, budzet, ilosc_miejsc, status, notatki, data_kontaktu) VALUES (:nick, :id, :nick_m, :budzet, :miejsca, :status, :notatki, :data)")
                s.execute(sql, params={
                    "nick": scout_nick, "id": b_manager_id_str, "nick_m": b_manager_nick,
                    "budzet": b_budget, "miejsca": b_spots, "status": b_status,
                    "notatki": b_notes, "data": b_contact_date
                })
                st.success(f'Dodano kupca: {b_manager_id_str}')
            s.commit()
        st.rerun()

st.header('Twoja Baza Kupców')
if df_buyers.empty:
    st.info('Baza kupców pusta.')
else:
    st.data_editor(df_buyers.drop(columns=['scout_nick']).sort_values(by='data_kontaktu', ascending=False), use_container_width=True)

    # === SEKCJA USUWANIA KUPCÓW ===
    with st.expander("🗑️ Zarządzanie / Usuwanie wpisów (Kupcy)"):
        delete_options_buyers = [
            f"{row['nick_managera'] or 'Bez nicku'} (ID: {row['manager_id']})" 
            for i, row in df_buyers.iterrows()
        ]
        selected_delete_buyer = st.selectbox("Wybierz kupca do usunięcia:", delete_options_buyers, key="delete_buyer_select")
        
        if st.button("❌ Usuń wybranego kupca"):
            match = re.search(r'\(ID: (\d+)\)', selected_delete_buyer)
            if match:
                id_to_delete = match.group(1)
                with conn.session as s:
                    s.execute(text("DELETE FROM buyers WHERE scout_nick = :nick AND manager_id = :id"), 
                              params={"nick": scout_nick, "id": id_to_delete})
                    s.commit()
                st.success(f"Usunięto kupca o ID: {id_to_delete}")
                st.rerun()

st.divider() 

# === SEKCJA 4: IMPORT I PRZEGLĄDARKA LISTY POBOROWYCH ===
st.header('Przeglądarka Listy Poborowych')
st.markdown("Tutaj możesz wgrać plik, a następnie **zapisać go w bazie**, aby był dostępny przy następnym logowaniu.")

col_up, col_save = st.columns([3, 1])
with col_up:
    uploaded_file = st.file_uploader("Wgraj plik CSV z poborowymi", type=['csv', 'xlsx'], key="player_list_uploader")

# === LOGIKA ZAPISU DO BAZY ===
if uploaded_file is not None:
    try:
        if uploaded_file.name.endswith('.csv'):
            df_players_raw = pd.read_csv(uploaded_file, sep=';', on_bad_lines='skip')
        else:
            df_players_raw = pd.read_excel(uploaded_file)
        
        # Wybieramy tylko potrzebne kolumny
        kolumny_graczy = [
            'PlayerID', 'FirstName', 'LastName', 'OwningUserID', 'Age', 'AgeDays', 
            'PlayerForm', 'StaminaSkill', 'DefenderSkill', 'PlaymakerSkill', 
            'WingerSkill', 'PassingSkill', 'ScorerSkill', 'SetPiecesSkill', 
            'TeamTrainerSkill', 'FormCoachLevels'
        ]
        istniejace_kolumny = [col for col in kolumny_graczy if col in df_players_raw.columns]
        df_to_save = df_players_raw[istniejace_kolumny].copy()
        
        # Aktualizuj podgląd
        st.session_state.player_list_df = df_to_save
        st.success("Plik wczytany lokalnie. Kliknij 'Zapisz listę w bazie', aby ją zachować.")

    except Exception as e:
        st.error(f'Błąd pliku: {e}')

# Przycisk zapisu
with col_save:
    st.write("") # odstęp
    st.write("") 
    if st.button("💾 Zapisz listę w bazie"):
        if not st.session_state.player_list_df.empty:
            df_save = st.session_state.player_list_df.copy()
            df_save['scout_nick'] = scout_nick # Dodaj nick, żeby wiedzieć czyja to lista
            
            # Upewnij się, że typy są proste dla SQL (zamiana na stringi tam gdzie trzeba)
            for col in df_save.columns:
                if col not in ['PlayerID', 'Age', 'AgeDays', 'PlayerForm', 'TeamTrainerSkill', 'FormCoachLevels']:
                    df_save[col] = df_save[col].astype(str)

            try:
                # Najpierw usuń starą listę tego skauta
                with conn.session as s:
                    s.execute(text("DELETE FROM imported_players WHERE scout_nick = :nick"), params={"nick": scout_nick})
                    s.commit()
                
                # Zapisz nową (używając silnika SQLAlchemy z conn)
                df_save.to_sql('imported_players', conn.engine, if_exists='append', index=False)
                
                st.success("Lista zapisana w bazie! Będzie dostępna po odświeżeniu.")
                st.rerun()
            except Exception as e:
                st.error(f"Błąd zapisu do bazy: {e}")
        else:
            st.warning("Najpierw wgraj plik.")

# === WYŚWIETLANIE LISTY ===
if not st.session_state.player_list_df.empty:
    df_display = st.session_state.player_list_df.copy()
    
    # Połącz z notatkami
    df_contacts_subset = df_contacts[['manager_id', 'nick_managera', 'status', 'notatki']].copy()
    
    if 'OwningUserID' in df_display.columns:
        df_display['OwningUserID'] = df_display['OwningUserID'].astype(str)
        df_contacts_subset['manager_id'] = df_contacts_subset['manager_id'].astype(str)
        df_contacts_subset = df_contacts_subset.drop_duplicates(subset=['manager_id'])

        df_merged = pd.merge(df_display, df_contacts_subset, left_on='OwningUserID', right_on='manager_id', how='left')
        df_merged.drop(columns=['manager_id'], inplace=True, errors='ignore')
        df_final = df_merged
    else:
        df_final = df_display

    # Wypełnij puste
    for col in ['nick_managera', 'notatki']:
        if col in df_final.columns: df_final[col] = df_final[col].fillna('')
    if 'status' in df_final.columns: df_final['status'] = df_final['status'].fillna('Brak kontaktu')

    st.divider()
    
    # Selektor do formularza
    player_options = [f"{row['FirstName']} {row['LastName']} (ID: {row['PlayerID']})" for i, row in df_final.iterrows()]
    player_options.insert(0, 'Wybierz...')
    st.selectbox('**Wypełnij formularz danymi gracza (Sekcja 1):**', options=player_options, key='player_filler_select', on_change=fill_form_callback)

    # Filtry
    f1, f2 = st.columns(2)
    with f1:
        owners = sorted(df_final['OwningUserID'].unique().astype(str)) if 'OwningUserID' in df_final.columns else []
        sel_owner = st.selectbox('Filtruj po Właścicielu:', ["Wszyscy"] + owners)
    with f2:
        sel_txt = st.text_input('Filtruj tekstowo:', key="filter_players_list").lower()

    if sel_owner != "Wszyscy":
        df_final = df_final[df_final['OwningUserID'] == sel_owner]
    if sel_txt:
        df_final = df_final[df_final.astype(str).apply(lambda x: x.str.lower().str.contains(sel_txt)).any(axis=1)]

    st.data_editor(df_final, key="player_data_editor", hide_index=True)
else:
    st.info("Brak listy graczy. Wgraj plik CSV powyżej.")
