import datetime
import pathlib
import re

import pandas as pd


CSV_DIRECTORY = pathlib.Path(__file__).parent.parent / "csv"

CBS_CSV_PATH = CSV_DIRECTORY / "CBS_holidays.csv"
DOCUMENT_CSV_PATH = CSV_DIRECTORY / "Document_gov_holidays.csv"
OUTPUT_CSV_PATH = CSV_DIRECTORY / "Combined_holidays.csv"

CBS_START_YEAR = 2019


MONTHS = {
    "January": 1,
    "February": 2,
    "March": 3,
    "April": 4,
    "May": 5,
    "June": 6,
    "July": 7,
    "August": 8,
    "September": 9,
    "October": 10,
    "November": 11,
    "December": 12,
}


BOOLEAN_COLUMNS = [
    "Is_Public_Holiday",
    "Is_Bank_Holiday",
    "Is_Mercantile_Holiday",
    "Is_Poya_Day",
]


REQUIRED_COLUMNS = {
    "Year",
    "Month",
    "Date",
    "Day",
    "Holiday_Name",
    "Is_Public_Holiday",
    "Is_Bank_Holiday",
    "Is_Mercantile_Holiday",
}


def format_date(year, month, day):
    """
    Convert Year, Month and Date into YYYY-MM-DD format.
    """

    year = int(year)
    day = int(day)

    if isinstance(month, str):
        month = month.strip()

        if month.title() in MONTHS:
            month_number = MONTHS[month.title()]

        elif month.isdigit():
            month_number = int(month)

        else:
            raise ValueError(f"Invalid month value: {month}")

    else:
        month_number = int(month)

    full_date = datetime.date(
        year,
        month_number,
        day,
    )

    return full_date.strftime("%Y-%m-%d")


def clean_holiday_name(name):
    """
    Remove unnecessary spaces without changing the holiday wording.
    """

    if pd.isna(name):
        return ""

    name = str(name).strip()
    name = re.sub(r"\s+", " ", name)

    return name


def normalize_name_for_comparison(name):
    """
    Normalize a holiday name only for comparison.

    This does not change the final holiday name.
    """

    if pd.isna(name):
        return ""

    name = str(name).casefold().strip()

    # Treat "&" and "and" as equivalent
    name = re.sub(r"\s*&\s*", " and ", name)

    # Ignore punctuation differences
    name = re.sub(r"[^\w\s]", "", name)

    # Remove repeated spaces
    name = re.sub(r"\s+", " ", name).strip()

    return name


def is_poya_day(holiday_name):
    """
    Return True if the holiday is a Poya Day.
    """

    if pd.isna(holiday_name):
        return False

    return "poya day" in str(holiday_name).casefold()


def convert_to_boolean(value):
    """
    Convert common CSV Boolean values into True or False.
    """

    if pd.isna(value):
        return False

    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        return value != 0

    return str(value).strip().casefold() in {
        "true",
        "1",
        "yes",
        "y",
        "t",
    }


def combine_boolean_values(values):
    """
    Return True if at least one value in the group is True.
    """

    return any(
        convert_to_boolean(value)
        for value in values
    )


def join_unique_holiday_names(values):
    """
    Combine genuinely different holiday names occurring on the same date.
    """

    unique_names = []
    existing_keys = set()

    for value in values.dropna():
        holiday_name = clean_holiday_name(value)

        if not holiday_name:
            continue

        comparison_key = normalize_name_for_comparison(
            holiday_name
        )

        if comparison_key not in existing_keys:
            unique_names.append(holiday_name)
            existing_keys.add(comparison_key)

    return " / ".join(unique_names)


def validate_columns(df, dataframe_name):
    """
    Ensure that the source dataframe contains all required columns.
    """

    missing_columns = REQUIRED_COLUMNS - set(df.columns)

    if missing_columns:
        missing_text = ", ".join(
            sorted(missing_columns)
        )

        raise ValueError(
            f"{dataframe_name} is missing these columns: "
            f"{missing_text}"
        )


def prepare_dataframe(df):
    """
    Clean a dataframe and create its Full_Date and Boolean columns.
    """

    df = df.copy()

    # Ensure Year is numeric
    df["Year"] = pd.to_numeric(
        df["Year"],
        errors="coerce",
    )

    # Remove rows with invalid years
    df = df.dropna(
        subset=["Year"]
    ).copy()

    df["Year"] = df["Year"].astype(int)

    df["Holiday_Name"] = df[
        "Holiday_Name"
    ].apply(clean_holiday_name)

    # Remove rows without a holiday name
    df = df[
        df["Holiday_Name"] != ""
    ].copy()

    df["Full_Date"] = df.apply(
        lambda row: format_date(
            row["Year"],
            row["Month"],
            row["Date"],
        ),
        axis=1,
    )

    for column in [
        "Is_Public_Holiday",
        "Is_Bank_Holiday",
        "Is_Mercantile_Holiday",
    ]:
        df[column] = df[column].apply(
            convert_to_boolean
        )

    df["Is_Poya_Day"] = df[
        "Holiday_Name"
    ].apply(is_poya_day)

    return df


def combine_rows_by_date(df):
    """
    Combine multiple holiday rows occurring on the same date.
    """

    return (
        df.groupby(
            "Full_Date",
            as_index=False,
        )
        .agg(
            {
                "Year": "first",
                "Month": "first",
                "Date": "first",
                "Day": "first",
                "Holiday_Name": join_unique_holiday_names,
                "Is_Public_Holiday": combine_boolean_values,
                "Is_Bank_Holiday": combine_boolean_values,
                "Is_Mercantile_Holiday": combine_boolean_values,
                "Is_Poya_Day": combine_boolean_values,
            }
        )
    )


def combine_document_boolean_values(document_df):
    """
    Combine the Document dataset Boolean values by date.
    """

    document_boolean_df = (
        document_df.groupby(
            "Full_Date",
            as_index=False,
        )[BOOLEAN_COLUMNS]
        .agg(combine_boolean_values)
    )

    document_boolean_df.rename(
        columns={
            column: f"{column}_Document"
            for column in BOOLEAN_COLUMNS
        },
        inplace=True,
    )

    return document_boolean_df


def merge_cbs_with_document_booleans(
    cbs_df,
    document_df,
):
    """
    From 2019 onward, keep CBS dates and names.

    Document data contributes only its Boolean classifications.
    """

    document_boolean_df = (
        combine_document_boolean_values(
            document_df
        )
    )

    combined_df = cbs_df.merge(
        document_boolean_df,
        on="Full_Date",
        how="left",
    )

    for column in BOOLEAN_COLUMNS:
        document_column = f"{column}_Document"

        combined_df[document_column] = (
            combined_df[document_column]
            .fillna(False)
            .apply(convert_to_boolean)
        )

        combined_df[column] = (
            combined_df[column].apply(
                convert_to_boolean
            )
            | combined_df[document_column]
        )

        combined_df.drop(
            columns=[document_column],
            inplace=True,
        )

    return combined_df


def display_name_differences(
    cbs_df,
    document_df,
):
    """
    Display holiday-name differences from 2019 onward only.
    """

    cbs_names = (
        cbs_df.groupby(
            "Full_Date",
            as_index=False,
        )["Holiday_Name"]
        .agg(join_unique_holiday_names)
        .rename(
            columns={
                "Holiday_Name": "CBS_Holiday_Name"
            }
        )
    )

    document_names = (
        document_df.groupby(
            "Full_Date",
            as_index=False,
        )["Holiday_Name"]
        .agg(join_unique_holiday_names)
        .rename(
            columns={
                "Holiday_Name": "Document_Holiday_Name"
            }
        )
    )

    comparison_df = cbs_names.merge(
        document_names,
        on="Full_Date",
        how="inner",
    )

    comparison_df["CBS_Normalized"] = comparison_df[
        "CBS_Holiday_Name"
    ].apply(normalize_name_for_comparison)

    comparison_df["Document_Normalized"] = comparison_df[
        "Document_Holiday_Name"
    ].apply(normalize_name_for_comparison)

    differences = comparison_df[
        comparison_df["CBS_Normalized"]
        != comparison_df["Document_Normalized"]
    ]

    if differences.empty:
        print(
            f"\nNo holiday-name differences found "
            f"from {CBS_START_YEAR} onward."
        )
        return

    print(
        f"\nHoliday-name differences from "
        f"{CBS_START_YEAR} onward:"
    )

    print(
        differences[
            [
                "Full_Date",
                "CBS_Holiday_Name",
                "Document_Holiday_Name",
            ]
        ].to_string(index=False)
    )


def display_unmatched_document_dates(
    cbs_df,
    document_df,
):
    """
    Display Document dates from 2019 onward that do not exist in CBS.
    """

    cbs_dates = set(
        cbs_df["Full_Date"]
    )

    unmatched_rows = document_df[
        ~document_df["Full_Date"].isin(
            cbs_dates
        )
    ].copy()

    if unmatched_rows.empty:
        print(
            f"\nAll Document dates from "
            f"{CBS_START_YEAR} onward exist in CBS."
        )
        return

    print(
        f"\nWarning: These Document holidays from "
        f"{CBS_START_YEAR} onward do not have a "
        f"matching CBS date and were ignored:"
    )

    print(
        unmatched_rows[
            [
                "Full_Date",
                "Holiday_Name",
            ]
        ]
        .drop_duplicates()
        .to_string(index=False)
    )


def main():
    cbs_df = pd.read_csv(
        CBS_CSV_PATH
    )

    document_df = pd.read_csv(
        DOCUMENT_CSV_PATH
    )

    validate_columns(
        cbs_df,
        "CBS_holidays.csv",
    )

    validate_columns(
        document_df,
        "Document_gov_holidays.csv",
    )

    cbs_df = prepare_dataframe(
        cbs_df
    )

    document_df = prepare_dataframe(
        document_df
    )

    # Document dataset is used directly before 2019
    document_before_2019 = document_df[
        document_df["Year"] < CBS_START_YEAR
    ].copy()

    # CBS validation is used only from 2019 onward
    cbs_from_2019 = cbs_df[
        cbs_df["Year"] >= CBS_START_YEAR
    ].copy()

    document_from_2019 = document_df[
        document_df["Year"] >= CBS_START_YEAR
    ].copy()

    # Review differences only for years covered by CBS
    display_name_differences(
        cbs_from_2019,
        document_from_2019,
    )

    display_unmatched_document_dates(
        cbs_from_2019,
        document_from_2019,
    )

    # Before 2019:
    # Use the Document dataset as the main source
    before_2019_df = combine_rows_by_date(
        document_before_2019
    )

    # From 2019 onward:
    # Use CBS dates and holiday names
    cbs_from_2019 = combine_rows_by_date(
        cbs_from_2019
    )

    from_2019_df = (
        merge_cbs_with_document_booleans(
            cbs_from_2019,
            document_from_2019,
        )
    )

    # Join the two periods
    final_df = pd.concat(
        [
            before_2019_df,
            from_2019_df,
        ],
        ignore_index=True,
    )

    final_df = final_df[
        [
            "Full_Date",
            "Year",
            "Month",
            "Date",
            "Day",
            "Holiday_Name",
            "Is_Public_Holiday",
            "Is_Bank_Holiday",
            "Is_Mercantile_Holiday",
            "Is_Poya_Day",
        ]
    ]

    final_df.sort_values(
        by="Full_Date",
        inplace=True,
    )

    final_df.reset_index(
        drop=True,
        inplace=True,
    )

    final_df.to_csv(
        OUTPUT_CSV_PATH,
        index=False,
    )

    print(
        "\nCombined CSV file created successfully at:",
        OUTPUT_CSV_PATH,
    )


if __name__ == "__main__":
    main()