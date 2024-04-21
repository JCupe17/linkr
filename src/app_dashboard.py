"""App dashboard for drug exposure."""
import base64
import datetime as dt
import io
import logging

import pandas as pd
from dash import Dash, dcc, html, dash_table, Input, Output, State, callback
import plotly.express as px

import src.preprocessing as pr


external_stylesheets = ['https://codepen.io/chriddyp/pen/bWLwgP.css']

CONCEPT_FILE = "./data/vocabulary_download_v5_all/CONCEPT.csv"
CONCEPT_DATES_COLS_TO_PARSE = ["valid_start_date", "valid_end_date"]
DRUG_STRENGTH_FILE = "./data/vocabulary_download_v5_all/DRUG_STRENGTH.csv"
DRUG_STRENGTH_DATES_COLS_TO_PARSE = ["valid_start_date", "valid_end_date"]

concept_df = pr.load_csv(filename=CONCEPT_FILE, sep="\t", parse_dates=CONCEPT_DATES_COLS_TO_PARSE)
drug_strength_df = pr.load_csv(filename=DRUG_STRENGTH_FILE, sep="\t", parse_dates=DRUG_STRENGTH_DATES_COLS_TO_PARSE)
strength_df = pr.preprocess_drug_strength(drug_df=drug_strength_df, concept_df=concept_df)

app = Dash(__name__, external_stylesheets=external_stylesheets)

app.layout = html.Div([
    dcc.Upload(
        id='upload-data',
        children=html.Div([
            'Drag and Drop or ',
            html.A('Select Files')
        ]),
        style={
            'width': '100%',
            'height': '60px',
            'lineHeight': '60px',
            'borderWidth': '1px',
            'borderStyle': 'dashed',
            'borderRadius': '5px',
            'textAlign': 'center',
            'margin': '10px'
        },
        # Allow multiple files to be uploaded
        multiple=False,
    ),
    html.Div(id='output-data-upload'),

    html.Hr(),
    html.H5("Patient selection"),

    html.Div([
        dcc.Dropdown(id="patient-id-dropdown", placeholder="Select Patient ID"),
        html.Div(id="selected-patient"),
    ]),

    html.Hr(),
    html.H5("Number of drugs across every visit"),
    html.Div([
        dcc.Graph(id="drugs-all-visits"),
    ]),

    html.Hr(),
    html.H5("Drugs per patient"),
    html.Div([
        html.Div("Select how do you want to visualize the drugs per patient"),
        dcc.RadioItems(options=["Visit ID", "Date range"], value="Visit ID", inline=True, id="visit-radio"),
    ]),
    html.Div([
        dcc.Dropdown(options=[], id="visit-id-dropdown", placeholder="Select a visit"),
        dcc.DatePickerRange(id="visit-id-date-range"),
        # html.Div(id="output-visit-type"),
        dcc.Graph(id="drugs-visit"),
    ]),

    # Store dataframe
    dcc.Store(id="input-dataframe"),
    dcc.Store(id="patient-dataframe"),
    dcc.Store(id="patient-visit-dataframe"),

])

@callback(
    Output("input-dataframe", "data"),
    Input("upload-data", "contents"),
    State('upload-data', 'filename'),
)
def loaded_dataframe(contents, filename):
    if contents is not None:
        content_type, content_string = contents.split(',')

        decoded = base64.b64decode(content_string)
        try:
            if 'csv' in filename:
                # Assume that the user uploaded a CSV file
                df = pd.read_csv(
                    io.StringIO(decoded.decode('utf-8')))
                df["person_id"] = df["person_id"].astype(str)
            elif 'xls' in filename:
                # Assume that the user uploaded an excel file
                df = pd.read_excel(io.BytesIO(decoded))

            df = pr.preprocess_drug_exposure(df)
            logging.info("Loading a file with %s rows and %s columns", df.shape[0], df.shape[1])
            return df.to_json(date_format="iso", orient="split")
        except Exception:
            msg = 'There was an error processing this file.'
            logging.exception(msg)
            return html.Div([msg])

@callback(
    Output("output-data-upload", "children"),
    Input("input-dataframe", "data"),
    State('upload-data', 'filename'),
    State('upload-data', 'last_modified'),
)
def update_output(json_df, filename, date):
    """Update the output after loading a file."""
    if json_df is not None:
        df = pd.read_json(json_df, orient="split", encoding="utf-8")
        df = pr.preprocess_drug_exposure(df)
        return html.Div([
            html.H5(filename),
            html.H6(dt.datetime.fromtimestamp(date)),
            dash_table.DataTable(
                data=df.to_dict('records'), page_size=10,
                style_table={"overflowX": "auto"}
            ),
        ])


@callback(
    Output("patient-id-dropdown", "options"),
    Input("input-dataframe", "data"),
)
def update_dropdown(json_df):
    if json_df is not None:
        df = pd.read_json(json_df, orient="split")
        options = pr.get_unique_patient_id(df)
    else:
        options = [{"label": "", "value": ""}]
    return options


@callback(
    Output("selected-patient", "children"),
    Input("patient-id-dropdown", "value"),
)
def update_patient_selection(value):
    return f"You have selected the patient {value}"


@callback(
    Output("patient-dataframe", "data"),
    Input("patient-id-dropdown", "value"),
    State("input-dataframe", "data"),
)
def store_patient_dataframe(value, json_df):
    if value is not None:
        df = pd.read_json(json_df, orient="split")
        patient_df = pr.get_dataframe_per_patient(df=df, patient_id=value)
        patient_df = pr.refining_drug_exposure(drug_df=patient_df, concept_df=concept_df)

        patient_df = pd.merge(left=patient_df, left_on="drug_concept_id", right=strength_df, right_on="drug_concept_id", how="left")
        patient_df["dose"] = patient_df.apply(pr.compute_drug_dose, axis=1)

        return patient_df.to_json(date_format="iso", orient="split")


@callback(
    Output("drugs-all-visits", "figure"),
    Input("patient-id-dropdown", "value"),
    State("input-dataframe", "data"),
)
def update_figure_number_drugs(value, json_df):
    print("Outside update")
    if value is not None:
        print("Inside update")
        df = pd.read_json(json_df, orient="split")
        patient_df = pr.get_dataframe_per_patient(df=df, patient_id=value)
        print(f"Patient df {patient_df.shape}")
        grouped_df = pr.get_dataframe_to_plot_all_visits(patient_df)
        print(f"Grouped df {grouped_df.shape}")
        fig = px.scatter(grouped_df, x="date", y="nb_drugs", color="visit_id")
    else:
        fig = px.scatter()
    return fig


@callback(
    Output("visit-id-dropdown", "options"),
    Input("patient-dataframe", "data"),
)
def update_visit_dropdown(json_df):
    if json_df is not None:
        df = pd.read_json(json_df, orient="split")
        options = pr.get_unique_visit_id(df)
    else:
        options = [{"label": "", "value": ""}]
    return options


# @callback(
#     Output("output-visit-type", "children"),
#     Input("visit-radio", "value"),
# )
# def update_visit_type(selected_type):
#     if selected_type == "Visit ID":
#         return html.Div([
#             dcc.Dropdown(options=[], id="visit-id-dropdown", placeholder="Select a visit"),
#         ])
#     else:
#         return html.Div([
#             dcc.DatePickerRange(id="visit-id-date-range"),
#         ])


@callback(
    Output("drugs-visit", "figure"),
    Input("visit-radio", "value"),
    Input("visit-id-dropdown", "value"),
    Input("visit-id-date-range", "start_date"),
    Input("visit-id-date-range", "end_date"),
    State("patient-dataframe", "data"),
    # State("visit-id-date-range", "value")
)
def update_figure_drugs_visit(visit_type, visit_id, start_date, end_date, json_df):
    fig = px.scatter()
    df = pd.DataFrame()

    if json_df is not None:
        df = pd.read_json(json_df, orient="split")
        df = pr.preprocess_drug_exposure_dates(df)

    print(f"DF {df.shape}")
    if visit_type == "Visit ID":
        visit_df = df.copy()
        if visit_id is not None:
            visit_df = visit_df[visit_df["visit_occurrence_id"] == visit_id].reset_index(drop=True)
        y_axis = "drug_concept_name"
    else:
        visit_df = df.copy()
        if start_date is not None:
            start_date_object = dt.datetime.fromisoformat(start_date)
            visit_df = visit_df[visit_df["drug_exposure_start_date"] >= start_date_object].reset_index(drop=True)
        if end_date is not None:
            end_date_object = dt.datetime.fromisoformat(end_date)
            visit_df = visit_df[visit_df["drug_exposure_end_date"] < end_date_object].reset_index(drop=True)
        y_axis = "drug_concept_id"

    if len(visit_df) > 0:
        print(f"VISIT DF {visit_df.shape}")
        visit_df = pr.preprocessing_visit_dataframe(visit_df)
        fig = px.timeline(
            visit_df,
            x_start="drug_exposure_start_datetime",
            x_end="drug_exposure_end_datetime",
            y=y_axis,
            color="quantity_diff_trend",
            color_continuous_scale="bluered",
            opacity=0.5,
        )

    return fig

if __name__ == '__main__':
    app.run(debug=True)
