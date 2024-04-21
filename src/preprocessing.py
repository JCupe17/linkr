import datetime as dt
import typing as T

import pandas as pd


def preprocess_drug_exposure_dates(df: pd.DataFrame) -> pd.DataFrame:
    new_df = df.copy()
    # Processing drug exposure dates
    date_columns = ["drug_exposure_start_date", "drug_exposure_end_date"]
    for col in date_columns:
        new_df[col] = pd.to_datetime(new_df[col])
    datetime_columns = ["drug_exposure_start_datetime", "drug_exposure_end_datetime"]
    for col in datetime_columns:
        new_df[col] = new_df[col].astype("datetime64[s]")
    return new_df


def preprocess_drug_exposure(df: pd.DataFrame) -> pd.DataFrame:
    new_df = df.copy()
    columns = ["drug_exposure_id", "person_id", "visit_occurrence_id"]
    columns = [col for col in columns if col in new_df.columns]
    for col in columns:
        prefix = col[0].upper()
        unique_values = new_df[col].unique()
        map_values = {val: f"{prefix}{i+1:06d}" for i, val in enumerate(unique_values)}

        new_df[col] = new_df[col].map(map_values)

    new_df = preprocess_drug_exposure_dates(df=new_df)

    return new_df


def load_csv(filename: str, sep: str, parse_dates: list[str]) -> pd.DataFrame:
    df = pd.read_csv(
        filepath_or_buffer=filename,
        sep=sep,
        parse_dates=parse_dates,
        date_format={col: "%Y%m%d" for col in parse_dates},
    )
    return df


def merge_dataset(left_df: pd.DataFrame, left_on: str, right_df: pd.DataFrame, right_on: str, prefixes: tuple[T.Optional[str], str], how: str = "left") -> pd.DataFrame:
    left_df = left_df.copy()
    if prefixes[0] is not None:
        left_df.columns = [f"{prefixes[0]}_{col}" for col in left_df.columns]
        left_on = f"{prefixes[0]}_{left_on}"

    right_df = right_df.copy()
    if prefixes[1] is not None:
        right_df.columns = [f"{prefixes[1]}_{col}" for col in right_df.columns]
        right_on = f"{prefixes[1]}_{right_on}"

    df = pd.merge(left=left_df, left_on=left_on, right=right_df, right_on=right_on, how=how)
    return df


def preprocess_drug_strength(drug_df: pd.DataFrame, concept_df: pd.DataFrame, keep_only_valid_unit: bool = False) -> pd.DataFrame:

    strength_df = drug_df.copy()
    # CHECK VALIDITY DATES
    # Invalid reason: D (deleted), U (replaced with an update), NULL (valid_end_date has the default value)
    strength_df["invalid_drug"] = strength_df["valid_end_date"].apply(lambda x: x < dt.datetime.now())

    assert len(strength_df["invalid_reason"].dropna()) == strength_df["invalid_drug"].sum()

    # ADD CONCEPT DEFINITION
    unit_concept_df = concept_df[concept_df["domain_id"] == "Unit"].reset_index(drop=True)
    # Keep only concepts that are valid
    if keep_only_valid_unit:
        unit_concept_df = unit_concept_df[unit_concept_df["valid_end_date"] >= dt.datetime.now()].reset_index(drop=True)

    # drug_concept_df = concept_df[concept_df["domain_id"] == "Drug"].reset_index(drop=True)
    drug_concept_df = concept_df.copy()

    # MERGE CONCEPTS
    # 1. Amount concept
    df = merge_dataset(
        left_df=strength_df,
        right_df=unit_concept_df,
        left_on="amount_unit_concept_id",
        right_on="concept_id",
        prefixes=(None, "amount"),
        how="left",
    )
    # 2. Numerator concept
    df = merge_dataset(
        left_df=df,
        right_df=unit_concept_df,
        left_on="numerator_unit_concept_id",
        right_on="concept_id",
        prefixes=(None, "numerator"),
        how="left",
    )
    # 3. Denominator concept
    df = merge_dataset(
        left_df=df,
        right_df=unit_concept_df,
        left_on="denominator_unit_concept_id",
        right_on="concept_id",
        prefixes=(None, "denominator"),
        how="left",
    )
    # 4. Ingredient concept
    df = merge_dataset(
        left_df=df,
        right_df=drug_concept_df,
        left_on="ingredient_concept_id",
        right_on="concept_id",
        prefixes=(None, "ingredient")
    )
    return df


def refining_drug_exposure(drug_df: pd.DataFrame, concept_df: pd.DataFrame) -> pd.DataFrame:
    exposure_df = drug_df.copy()

    # drug_concept_df = concept_df[concept_df["domain_id"] == "Drug"].reset_index(drop=True)
    drug_concept_df = concept_df.copy()

    # MERGE CONCEPTS
    # 1. Drug
    df = merge_dataset(
        left_df=exposure_df,
        left_on="drug_concept_id",
        right_df=drug_concept_df,
        right_on="concept_id",
        prefixes=(None, "drug"),
        how="left",
    )
    # 2. Drug type
    df = merge_dataset(
        left_df=df,
        left_on="drug_type_concept_id",
        right_df=drug_concept_df,
        right_on="concept_id",
        prefixes=(None, "drug_type"),
        how="left",
    )
    # 3. Route
    df = merge_dataset(
        left_df=df,
        left_on="route_concept_id",
        right_df=drug_concept_df,
        right_on="concept_id",
        prefixes=(None, "route"),
        how="left",
    )

    return df


def compute_drug_dose(row: pd.Series) -> tuple[T.Optional[float], T.Optional[str]]:
    # 1. Tablets and other fixed amount formulations
    # DRUG_STRENGTH.denominator_unit_concept_id = empty
    if row["denominator_unit_concept_id"] is None:
        dose = row["quantity"] * row["amount_value"]
        dose_lit = f"{dose} {row['denominator_concept_code']}"
    # 2. Puffs of an inhaler
    # Denominator unit is {actuat}
    elif row["denominator_unit_concept_id"] == 45744809:
        dose = row["quantity"] * row["numerator_value"]
        dose_lit = f"{dose} {row['numerator_concept_code']}"
    # Denominator is either mL or mg
    elif row["denominator_unit_concept_id"] in [8587, 8576]:  # [mL, mg]
        # 3. Quantified Drugs which are formulated as a concentration mL or mg, but
        # denominator_value might be different from 1
        if row["denominator_value"] != 1:
            dose = row["quantity"] * row["numerator_value"]
            dose_lit = f"{dose} {row['numerator_concept_code']}"
        # 4. Drugs with the total amount provided in quantity
        # NLP analysis is needed to analyze concept name (get concentration, content, units, etc.)
        # TO CHECK 1: check that quantity is expressed in mL or mL and not in oz
        # TO CHECK 2: check denominator unit e.g. g vs mg (factor 1000)
        else:
            dose = row["quantity"] * row["numerator_value"]
            dose_lit = f"{dose} {row['numerator_concept_code']}"
    # 6. Drugs with the active ingredient released over time
    elif row["denominator_unit_concept_id"] == 8505:
        dose = row["numerator_value"]
        dose_lit = f"{dose} {row['numerator_concept_code']} / {row['denominator_concept_code']}"
    # 5. Compounded drugs
    # TODO: NLP analysis needed to get different ingredients
    else:
        dose = None
        dose_lit = None

    return dose, dose_lit


def get_dataframe_per_patient(df: pd.DataFrame, patient_id: int) -> pd.DataFrame:
    patient_df = df[df["person_id"] == patient_id].reset_index(drop=True)
    return patient_df

def get_dataframe_per_visit(df: pd.DataFrame, patient_id: int, visit_id: int) -> pd.DataFrame:
    visit_df = df[(df["person_id"] == patient_id) & (df["visit_occurrence_id"] == visit_id)].reset_index(drop=True)
    return visit_df

def get_unique_patient_id(df: pd.DataFrame) -> list:
    return df["person_id"].unique().tolist()

def get_unique_visit_id(df: pd.DataFrame) -> list:
    return df["visit_occurrence_id"].unique().tolist()

def get_trend(value: float) -> int:
    if value > 0:
        return 1
    elif value < 0:
        return -1
    else:
        return 0


def get_dataframe_to_plot_all_visits(df: pd.DataFrame) -> pd.DataFrame:
    # Get all drug_concept_id per day
    drug = pd.concat([pd.Series(row.drug_concept_id, pd.date_range(row.drug_exposure_start_date, row.drug_exposure_end_date)) for row in df.itertuples()])
    drug_df = pd.DataFrame(drug, columns=["drug_concept_id"])
    # Get all visit_occurrence_id per day
    visit = pd.concat([pd.Series(row.visit_occurrence_id, pd.date_range(row.drug_exposure_start_date, row.drug_exposure_end_date)) for row in df.itertuples()])
    visit_df = pd.DataFrame(visit, columns=["visit_occurrence_id"])

    # Concatenate both dataframes to get drug_concept_id and visit_occurrence_id per day
    dates_df = pd.concat([drug_df, visit_df], axis=1).reset_index(names="date")

    # Get the number of drugs per day and the number of visits per day
    grouped_dates_df = dates_df.groupby("date").agg({"drug_concept_id": ["unique", "nunique"], "visit_occurrence_id": ["unique", "nunique"]}).reset_index()

    # Keep only one visit per day ?
    # grouped_tmp_df = grouped_tmp_df[grouped_tmp_df[("visit_occurrence_id", "nunique")] == 1].reset_index(drop=True)
    grouped_dates_df.columns = ["date", "unique_drugs", "nb_drugs", "visit_id", "nb_visits"]
    grouped_dates_df["visit_id"] = grouped_dates_df["visit_id"].apply(lambda x: x[0]).astype(str)

    return grouped_dates_df


def preprocessing_visit_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    visit_df = df.copy()
    visit_df["drug_concept_id"] = visit_df["drug_concept_id"].astype(str)
    visit_df = visit_df.sort_values(by=["drug_concept_id", "drug_exposure_start_datetime"]).reset_index(drop=True)
    # TODO: Diff by drug_concept_id
    visit_df["quantity_diff"] = visit_df.groupby("drug_concept_id")["quantity"].diff()
    visit_df["quantity_diff_percentage"] = visit_df.apply(lambda x: round(x["quantity_diff"]/x["quantity"]*100, 2) if x["quantity"] > 0 else 100, axis=1)
    visit_df["quantity_diff_trend"] = visit_df["quantity_diff"].apply(get_trend)

    return visit_df
