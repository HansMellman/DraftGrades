# Import dependencies
import pandas as pd
import streamlit as st
import numpy as np
import io
from draft_rounds import round_1, round_2, round_3, round_4, round_5, round_6, round_7

# Set page configuration with an emoji in the browser tab
st.set_page_config(
    page_title="Finkell Draft Grades",  # This will appear on the browser tab
    page_icon="🏈",  # Use the American football emoji as the favicon
  # layout="wide"  # Set the app layout to wide
)

# Initialize session state for file uploads
if 'uploaded_files' not in st.session_state:
    st.session_state['uploaded_files'] = None

# Function to clear uploaded files
def clear_files():
    st.session_state['uploaded_files'] = None

# Page title
st.title("Finkell Draft Grades")

# Note about usage
st.write("Please note that this will only work **after** PS2 and pre-reveal of the following years Draft Class. Any attempt after that will not work due to incomplete data.")

# Request the league name from the user
league = st.text_input("Please enter the league abbreviation", help="For Example 'TFL'")

# Request the current draft year from the user
cur_year = st.number_input("Enter the current draft year", step=1, value=2024, min_value=2024, max_value=2200, help="This is needed for filtering purposes.")

# Request CSVs from the user.
files = st.file_uploader("Upload CSV files(player_record, players_personal, player_information & team_information)",
                         type="csv", accept_multiple_files=True,
                         help="Hold down Ctrl whilst selecting to choose multiple CSVs. "\
                              "They can be in any order, as long as the default naming convention remains intact.")

# Update the session state with uploaded files
if files:
    st.session_state['uploaded_files'] = files

# Button to clear uploaded files
if st.button("Clear Uploaded Files"):
    clear_files()

# Initialize variables for the different files
player_record = None
players_personal = None
team_information = None
player_information = None

# Use files from session state for processing
if st.session_state['uploaded_files']:
    st.write("Uploaded files:")
    # Display the names of all uploaded files in a condensed table format
    file_details = {"File Name": [file.name for file in st.session_state['uploaded_files']], 
                    "File Size (KB)": [file.size / 1024 for file in st.session_state['uploaded_files']]}
    st.table(pd.DataFrame(file_details))

    # Identify and assign files based on their names
    for file in st.session_state['uploaded_files']:
        if "player_record" in file.name:
            player_record = pd.read_csv(file)
        elif "players_personal" in file.name:
            players_personal = pd.read_csv(file)
        elif "team_information" in file.name:
            team_information = pd.read_csv(file)
        elif "player_information" in file.name:
            player_information = pd.read_csv(file, low_memory=False, on_bad_lines='skip', encoding='latin-1')

    # Check that all required files are loaded
    missing_files = []
    if player_record is None:
        missing_files.append("Player record file")
    if players_personal is None:
        missing_files.append("Player personal file")
    if team_information is None:
        missing_files.append("Team information file")
    if player_information is None:
        missing_files.append("Player information file")

    if missing_files:
        st.error(f"Missing files: {', '.join(missing_files)}")
    else:
        # Proceed with data processing
        st.write("All required files are loaded. Proceeding with data processing...")
        # Show a progress bar for processing
        with st.spinner("Processing data..."):
            # Your data processing logic here...

            # Isolate only needed columns from CSVs and perform data manipulation
            player_information = player_information[['Player_ID', 'First_Name', 'Last_Name', 'Position', 'Drafted_By', 'Draft_Round', 'Drafted_Position', 'Draft_Year']]
            players_personal = players_personal[['Player_ID', 'Future_Overall']]
            team_information = team_information[['Team', 'Home_City']]

            cur_draft = player_information[
                (player_information['Draft_Year'] == cur_year) &
                (~player_information['Position'].str.contains('P|K', na=False))
            ].copy()

            team_mapping = team_information.set_index('Team')['Home_City'].to_dict()
            cur_draft['Drafted_By'] = cur_draft['Drafted_By'].map(team_mapping)
            cur_draft = pd.merge(cur_draft, players_personal, how='left', on='Player_ID')

            # Load EstimatedFV CSV and continue data processing
            estimated_fv_df = pd.read_csv('EstimatedFV.csv')
            cur_draft = pd.merge(cur_draft,
                                 estimated_fv_df[['draft round', 'draft_position', 'expected_FV']],
                                 how='left',
                                 left_on=['Draft_Round', 'Drafted_Position'],
                                 right_on=['draft round', 'draft_position'])

            cur_draft.drop(columns=['draft round', 'draft_position'], inplace=True)
            cur_draft['expected_FV'] = cur_draft['expected_FV'].fillna(0).astype('int64')
            cur_draft['difference_BPA'] = (cur_draft['Future_Overall'] - cur_draft['expected_FV'])

            def get_pos_avg(draft_round, position):
                # Select the appropriate dictionary based on the draft round
                if draft_round == 1:
                    return round_1.get(position, 0)
                elif draft_round == 2:
                    return round_2.get(position, 0)
                elif draft_round == 3:
                    return round_3.get(position, 0)
                elif draft_round == 4:
                    return round_4.get(position, 0)
                elif draft_round == 5:
                    return round_5.get(position, 0)
                elif draft_round == 6:
                    return round_6.get(position, 0)
                elif draft_round == 7:
                    return round_7.get(position, 0)
                else:
                    return 0

            cur_draft['pos_avg'] = cur_draft.apply(lambda row: get_pos_avg(row['Draft_Round'], row['Position']), axis=1)
            cur_draft['weighted_value'] = np.floor(cur_draft['Future_Overall'] * 
                                                   (cur_draft['Future_Overall'] / cur_draft['pos_avg'])).astype(int)

            top_20 = cur_draft.sort_values('weighted_value', ascending=False).head(20)
            bpa_df = cur_draft.groupby('Drafted_By', as_index=False)['difference_BPA'].mean().round(2)
            bpa_df.rename(columns={'difference_BPA': 'bpa'}, inplace=True)
            bpa_df = bpa_df.sort_values(by='bpa', ascending=False)
            bpa_df['bpa_rank'] = bpa_df['bpa'].rank(ascending=False, method='min').astype(int)

            conditions = [
                (bpa_df['bpa'] > 2.01),
                (bpa_df['bpa'] >= -2.00) & (bpa_df['bpa'] <= 2.00),
                (bpa_df['bpa'] < -2.01)
            ]
            verdicts = ['Did well for BPA', 'Drafted as expected', 'Missed on picks or prioritised other things over BPA']
            bpa_df['verdict'] = np.select(conditions, verdicts, default='Unknown')

            weighted_df_raw = cur_draft.groupby('Drafted_By', as_index=False)['weighted_value'].mean().round(2)
            weighted_df_raw.rename(columns={'weighted_average': 'weighted_value'}, inplace=True)
            weighted_df_raw = weighted_df_raw.sort_values(by='weighted_value', ascending=False)
            weighted_df_raw['weighted_rank'] = weighted_df_raw['weighted_value'].rank(ascending=False, method='min').astype(int)

            conditions = [
                (weighted_df_raw['weighted_value'] >= 50),
                (weighted_df_raw['weighted_value'] <= 49.9) & (weighted_df_raw['weighted_value'] >= 44),
                (weighted_df_raw['weighted_value'] < 44)
            ]
            verdicts = ['Acquired 2+ Starters', 'As Expected/Mid', 'Had Several Misses']
            weighted_df_raw['verdict'] = np.select(conditions, verdicts, default='Unknown')
            weighted_df_raw = weighted_df_raw[['weighted_rank', 'Drafted_By', 'weighted_value', 'verdict']]
            weighted_rank = pd.merge(bpa_df[['Drafted_By', 'bpa_rank']], weighted_df_raw, on='Drafted_By', how='left')
            weighted_rank = weighted_rank[['bpa_rank', 'weighted_rank', 'Drafted_By', 'weighted_value', 'verdict']]
            weighted_rank = weighted_rank.sort_values(by='weighted_rank', ascending=True)

            draft_quality = cur_draft.groupby('Draft_Round', as_index=False)['difference_BPA'].mean()
            draft_quality.rename(columns={'difference_BPA': 'average value'}, inplace=True)
            draft_quality = draft_quality.sort_values(by='Draft_Round')
            draft_quality['average value'] = draft_quality['average value'].round(2)
            overall_mean = cur_draft['difference_BPA'].mean().round(2)
            draft_quality.loc[len(draft_quality.index)] = ['overall', overall_mean]

        # Function to save dataframes to an Excel file in-memory
        def save_dfs_to_excel(league, cur_year, **dfs):
            output = io.BytesIO()
            filename = f"{league}_{cur_year}_DraftGrades.xlsx"
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                for sheet_name, df in dfs.items():
                    df.to_excel(writer, sheet_name=sheet_name, index=False)
            output.seek(0)
            return output, filename

        # Create and display the download button
        excel_file, filename = save_dfs_to_excel(
            league, cur_year,
            bpa_df=bpa_df,
            weighted_rank=weighted_rank,
            top_20=top_20,
            draft_quality=draft_quality
        )

        st.download_button(
            label="📥 Download Excel file",
            data=excel_file,
            file_name=filename,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
else:
    st.write("Please upload the required CSV files.")
