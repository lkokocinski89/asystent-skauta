import streamlit as st
import pandas as pd
import os
from datetime import date
import re 
from sqlalchemy import text # Będziemy tego potrzebować do bazy danych

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
# Używamy session_state, aby nick był pamiętany
if 'scout_nick' not in st.session_state:
    st.session_state.scout_nick = ""

scout_nick_input = st.text_input("Podaj swój nick skauta, aby się zalogować:", value=st.session_state.scout_nick)

# Jeśli ktoś próbuje się "wylogować" (wyczyścić pole), zaktualizuj stan
if st.session_state.scout_nick and not scout_nick_input:
    st.session_state.scout_nick = ""
elif scout_nick_input:
    st.session_state.scout_nick = scout_nick_input

# Zablokuj resztę aplikacji, jeśli nick nie jest podany
if not st.session_state.scout_nick:
    st.warning("Musisz podać swój nick skauta, aby kontynuować.")
    st.stop()

# Pobierz nick z pamięci
scout_nick = st.session_state.scout_nick
st.success(f"Zalogowano jako: **{scout_nick}**. Widzisz tylko swoje prywatne dane.")

# --- Inicjalizacja Połączenia z Bazą Danych ---
# Streamlit automatycznie użyje sekretu "DATABASE_URL"
try:
    conn = st.connection("database", type="sql")
except Exception as e:
    st.error(f"Błąd połączenia z bazą danych. Upewnij się, że skonfigurowałeś sekrety w Streamlit Cloud. Błąd: {e}")
    st.stop()
    
# Inicjalizacja Session State dla formularzy (teraz pod logowaniem)
if 'player_list_df' not in st.session_state:
    st.session_state['player_list_df'] = pd.DataFrame() 

# --- Funkcja Inicjalizująca Bazę Danych (uruchomi się tylko raz) ---
@st.cache_resource
def init_db():
    # Stwórz tabele, jeśli nie istnieją. Kluczowe jest dodanie 'scout_nick'
    with conn.session as s:
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
        s.commit()

# Uruchom inicjalizację
init_db()

# --- Funkcje Pomocnicze (DLA POBOROWYCH) ---
def load_contacts_db(nick):
    df = conn.query(
        "SELECT * FROM contacts WHERE scout_nick = :nick",
        params={"nick": nick},
        ttl=0 # Nie chcemy cache'owania - zawsze świeże dane
    )
    # Zapewnij poprawną kolejność i typy
    df['data_kontaktu'] = pd.to_datetime(df['data_kontaktu'])
    return df

def fill_form_callback():
    selected_option = st.session_state.get('player_filler_select', 'Wybierz...')
    match = re.search(r'\(ID: (\d+)\)', selected_option)
    
    if match and not st.session_state.player_list_df.empty:
        try:
            player_id_to_find = int(match.group(1))
            player_data_series = st.session_state.player_list_df[
                st.session_state.player_list_df['PlayerID'].astype(int) == player_id_to_find
            ]
            
            if not player_data_series.empty:
                player_data = player_data_series.iloc[0]
                manager_id = str(player_data['OwningUserID'])
                
                st.session_state.form_manager_id = manager_id
                st.session_state.form_player_name = f"{player_data['FirstName']} {player_data['LastName']}"
                st.session_state.form_player_id = str(player_data['PlayerID'])
                
                df_contacts_local = load_contacts_db(scout_nick) 
                if manager_id in df_contacts_local['manager_id'].astype(str).values:
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


# --- Główna Logika ---
df_contacts = load_contacts_db(scout_nick)
df_buyers = conn.query("SELECT * FROM buyers WHERE scout_nick = :nick", params={"nick": scout_nick}, ttl=0)

status_options_contacts = ['Brak kontaktu', 'Nowy (Do kontaktu)', 'Wysłano HT-mail', 'Odpowiedział (Pozytywnie)', 'Odpowiedział (Negatywnie)', 'Monitorowany', 'Zakończony (Nie pisać)']
status_options_buyers = ['Nowy', 'Zapytany', 'Zainteresowany', 'Kupił', 'Niezainteresowany', 'Do ponowienia']

# === SEKCJA 1: REJESTR KONTAKTÓW (DLA POBOROWYCH) ===
st.header('Rejestr Kontaktów (Poborowi)')
st.markdown("Wpisz ID managera lub **użyj listy na dole**, aby automatycznie wypełnić formularz.")

# Inicjalizacja pól formularza
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
        # Sprawdź, czy wpis już istnieje
        exists = conn.query(
            "SELECT 1 FROM contacts WHERE scout_nick = :nick AND manager_id = :id",
            params={"nick": scout_nick, "id": manager_id_str},
            ttl=0
        )
        
        with conn.session as s:
            if not exists.empty:
                # AKTUALIZUJ
                sql = text("""
                    UPDATE contacts SET 
                    nick_managera = :nick_m, imie_nazwisko_zawodnika = :imie, id_gracza = :id_g, 
                    status = :status, notatki = :notatki, data_kontaktu = :data 
                    WHERE scout_nick = :nick AND manager_id = :id
                """)
                s.execute(sql, params={
                    "nick_m": st.session_state.form_manager_nick,
                    "imie": st.session_state.form_player_name,
                    "id_g": st.session_state.form_player_id,
                    "status": st.session_state.form_status,
                    "notatki": st.session_state.form_notes,
                    "data": st.session_state.form_date,
                    "nick": scout_nick,
                    "id": manager_id_str
                })
                st.success(f'Pomyślnie zaktualizowano dane dla managera: {manager_id_str}')
            else:
                # DODAJ NOWY
                sql = text("""
                    INSERT INTO contacts (scout_nick, manager_id, nick_managera, imie_nazwisko_zawodnika, id_gracza, status, notatki, data_kontaktu)
                    VALUES (:nick, :id, :nick_m, :imie, :id_g, :status, :notatki, :data)
                """)
                s.execute(sql, params={
                    "nick": scout_nick,
                    "id": manager_id_str,
                    "nick_m": st.session_state.form_manager_nick,
                    "imie": st.session_state.form_player_name,
                    "id_g": st.session_state.form_player_id,
                    "status": st.session_state.form_status,
                    "notatki": st.session_state.form_notes,
                    "data": st.session_state.form_date
                })
                st.success(f'Pomyślnie dodano nowy kontakt dla managera: {manager_id_str}')
            s.commit()
        
        # Wyczyść formularz
        st.session_state.form_manager_id = ""
        st.session_state.form_manager_nick = ""
        st.session_state.form_player_name = ""
        st.session_state.form_player_id = ""
        st.session_state.form_notes = ""
        st.rerun() 


# === SEKCJA 2: WYŚWIETLANIE BAZY KONTAKTÓW (POBOROWI) ===
st.header('Twoja Baza Kontaktów (Poborowi)')
if df_contacts.empty:
    st.info('Twoja baza kontaktów jest pusta.')
else:
    display_columns = ['manager_id', 'nick_managera', 'imie_nazwisko_zawodnika', 'id_gracza', 'status', 'notatki', 'data_kontaktu']
    st.data_editor(df_contacts[display_columns].sort_values(by='data_kontaktu', ascending=False), use_container_width=True)

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
        b_budget = st.text_input('Budżet (opcjonaljonalnie)')
        b_spots = st.text_input('Ilość Miejsc (opcjonalnie)')
        b_contact_date = st.date_input('Data Kontaktu', value=date.today())
    b_notes = st.text_area('Notatki (Kupiec)', placeholder="Wpisz swoje uwagi...")
    submit_button_buyer = st.form_submit_button(label='Zapisz Kupca')

if submit_button_buyer:
    if not b_manager_id:
        st.error('ID Managera jest polem wymaganym!')
    else:
        b_manager_id_str = str(b_manager_id)
        exists = conn.query(
            "SELECT 1 FROM buyers WHERE scout_nick = :nick AND manager_id = :id",
            params={"nick": scout_nick, "id": b_manager_id_str},
            ttl=0
        )
        
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
                st.success(f'Pomyślnie zaktualizowano dane dla kupca: {b_manager_id_str}')
            else:
                sql = text("""
                    INSERT INTO buyers (scout_nick, manager_id, nick_managera, budzet, ilosc_miejsc, status, notatki, data_kontaktu)
                    VALUES (:nick, :id, :nick_m, :budzet, :miejsca, :status, :notatki, :data)
                """)
                s.execute(sql, params={
                    "nick": scout_nick, "id": b_manager_id_str, "nick_m": b_manager_nick,
                    "budzet": b_budget, "miejsca": b_spots, "status": b_status,
                    "notatki": b_notes, "data": b_contact_date
                })
                st.success(f'Pomyślnie dodano nowego kupca: {b_manager_id_str}')
            s.commit()
        st.rerun()

# Wyświetlanie bazy kupców
st.header('Twoja Baza Kupców')
if df_buyers.empty:
    st.info('Twoja baza kupców jest pusta.')
else:
    st.data_editor(df_buyers.drop(columns=['scout_nick']).sort_values(by='data_kontaktu', ascending=False), use_container_width=True)

st.divider() 

# === SEKCJA 4: IMPORT I PRZEGLĄDARKA LISTY POBOROWYCH ===
st.header('Przeglądarka Listy Poborowych')
uploaded_file = st.file_uploader("Wgraj plik CSV z poborowymi", type=['csv', 'xlsx'], key="player_list_uploader")

if uploaded_file is not None:
    try:
        if uploaded_file.name.endswith('.csv'):
            df_players_raw = pd.read_csv(uploaded_file, sep=';', on_bad_lines='skip')
        else:
            df_players_raw = pd.read_excel(uploaded_file)
        
        st.success('Plik załadowany pomyślnie!')
        
        kolumny_graczy = [
            'PlayerID', 'FirstName', 'LastName', 'OwningUserID', 'Age', 'AgeDays', 
            'PlayerForm', 'StaminaSkill', 'DefenderSkill', 'PlaymakerSkill', 
            'WingerSkill', 'PassingSkill', 'ScorerSkill', 'SetPiecesSkill', 
            'TeamTrainerSkill', 'FormCoachLevels'
        ]
        
        istniejace_kolumny_graczy = [col for col in kolumny_graczy if col in df_players_raw.columns]
        df_players_clean = df_players_raw[istniejace_kolumny_graczy]
        
        st.session_state.player_list_df = df_players_clean.copy()

        # Połącz z bazą kontaktów
        df_contacts_subset = df_contacts[['manager_id', 'nick_managera', 'status', 'notatki']].copy()
        
        if 'OwningUserID' in df_players_clean.columns:
            df_players_clean['OwningUserID'] = df_players_clean['OwningUserID'].astype(str)
            df_contacts_subset['manager_id'] = df_contacts_subset['manager_id'].astype(str)
            
            df_contacts_subset = df_contacts_subset.drop_duplicates(subset=['manager_id'])

            df_merged = pd.merge(
                df_players_clean,
                df_contacts_subset,
                left_on='OwningUserID',
                right_on='manager_id',
                how='left'
            )
            df_merged.drop(columns=['manager_id'], inplace=True, errors='ignore')
            df_to_show = df_merged
        else:
            df_to_show = df_players_clean

        # Wypełnij puste pola
        if 'nick_managera' not in df_to_show.columns: df_to_show['nick_managera'] = ''
        else: df_to_show['nick_managera'].fillna('', inplace=True)
        if 'status' not in df_to_show.columns: df_to_show['status'] = 'Brak kontaktu'
        else: df_to_show['status'].fillna('Brak kontaktu', inplace=True)
        if 'notatki' not in df_to_show.columns: df_to_show['notatki'] = ''
        else: df_to_show['notatki'].fillna('', inplace=True)

        st.divider() 
        
        player_options = [
            f"{row['FirstName']} {row['LastName']} (ID: {row['PlayerID']})"
            for index, row in st.session_state.player_list_df.iterrows()
        ]
        player_options.insert(0, 'Wybierz...') 
        
        st.selectbox(
            '**Wypełnij formularz danymi gracza (Sekcja 1):**',
            options=player_options,
            key='player_filler_select', 
            on_change=fill_form_callback 
        )

        filter_col1, filter_col2 = st.columns(2)
        with filter_col1:
            if 'OwningUserID' in df_to_show.columns:
                unique_owners = sorted(df_to_show['OwningUserID'].unique())
                unique_owners.insert(0, "Wszyscy") 
                selected_owner_str = st.selectbox('Filtruj po Właścicielu:', unique_owners)
            else:
                selected_owner_str = "Wszyscy"
        
        with filter_col2:
            filter_players = st.text_input('Filtruj listę tekstowo (dodatkowo):', key="filter_players_list").lower() 

        if selected_owner_str == "Wszyscy":
            filtered_by_owner_df = df_to_show
        else:
            filtered_by_owner_df = df_to_show.loc[df_to_show['OwningUserID'] == selected_owner_str].copy()

        if filter_players:
            final_df_to_show = filtered_by_owner_df.copy()
            for col in final_df_to_show.columns:
                final_df_to_show[col] = final_df_to_show[col].astype(str).str.lower()
            mask = final_df_to_show.apply(lambda row: row.str.contains(filter_players, na=False).any(), axis=1)
            final_df_to_show = filtered_by_owner_df[mask]
        else:
            final_df_to_show = filtered_by_owner_df
            
        st.data_editor(final_df_to_show, key="player_data_editor")
            
    except Exception as e:
        st.error(f'Wystąpił błąd podczas wczytywania pliku: {e}')
        st.exception(e)