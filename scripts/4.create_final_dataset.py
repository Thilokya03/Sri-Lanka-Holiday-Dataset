import datetime
import pathlib

import pandas as pd


CSV_DIRECTORY = pathlib.Path(__file__).parent.parent / "csv"

HOLIDAY_CSV_PATH = CSV_DIRECTORY / "Combined_holidays.csv"
OUTPUT_CSV_PATH = CSV_DIRECTORY / "Sri_Lanka_all_dates.csv"

START_YEAR = 2005


BOOLEAN_COLUMNS = [
    "Is_Public_Holiday",
    "Is_Bank_Holiday",
    "Is_Mercantile_Holiday",
    "Is_Poya_Day",
]


def convert_to_boolean(value):
    """
    Convert common CSV Boolean representations to True or False.
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


def load_holiday_dataset():
    """
    Load and validate the combined holiday dataset.
    """

    holiday_df = pd.read_csv(HOLIDAY_CSV_PATH)

    required_columns = {
        "Full_Date",
        "Holiday_Name",
        *BOOLEAN_COLUMNS,
    }

    missing_columns = required_columns - set(holiday_df.columns)

    if missing_columns:
        missing_text = ", ".join(sorted(missing_columns))

        raise ValueError(
            f"Combined_holidays.csv is missing these columns: "
            f"{missing_text}"
        )

    holiday_df["Full_Date"] = pd.to_datetime(
        holiday_df["Full_Date"],
        errors="coerce",
    )

    invalid_date_rows = holiday_df[
        holiday_df["Full_Date"].isna()
    ]

    if not invalid_date_rows.empty:
        raise ValueError(
            "Combined_holidays.csv contains invalid Full_Date values."
        )

    # Ensure Boolean columns contain proper Boolean values
    for column in BOOLEAN_COLUMNS:
        holiday_df[column] = holiday_df[column].apply(
            convert_to_boolean
        )

    # Ensure the holiday name is a string
    holiday_df["Holiday_Name"] = (
        holiday_df["Holiday_Name"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    # The combined holiday dataset should contain one row per date
    duplicate_dates = holiday_df[
        holiday_df.duplicated(
            subset=["Full_Date"],
            keep=False,
        )
    ]

    if not duplicate_dates.empty:
        print("\nDuplicate dates found in Combined_holidays.csv:")

        print(
            duplicate_dates[
                [
                    "Full_Date",
                    "Holiday_Name",
                ]
            ].to_string(index=False)
        )

        raise ValueError(
            "Resolve duplicate dates before creating the complete dataset."
        )

    return holiday_df


def determine_end_year(holiday_df):
    """
    Use the latest year found in the holiday dataset.

    If the current year is later, use the current year instead.
    """

    latest_holiday_year = holiday_df[
        "Full_Date"
    ].dt.year.max()

    current_year = datetime.date.today().year

    return max(
        int(latest_holiday_year),
        current_year,
    )


def create_calendar_dataset(start_year, end_year):
    """
    Create one row for every calendar date.
    """

    start_date = f"{start_year}-01-01"
    end_date = f"{end_year}-12-31"

    calendar_df = pd.DataFrame(
        {
            "Full_Date": pd.date_range(
                start=start_date,
                end=end_date,
                freq="D",
            )
        }
    )

    calendar_df["Year"] = calendar_df[
        "Full_Date"
    ].dt.year

    calendar_df["Month"] = calendar_df[
        "Full_Date"
    ].dt.month_name()

    calendar_df["Date"] = calendar_df[
        "Full_Date"
    ].dt.day

    calendar_df["Day"] = calendar_df[
        "Full_Date"
    ].dt.day_name()

    return calendar_df


def merge_calendar_with_holidays(
    calendar_df,
    holiday_df,
):
    """
    Add holiday information to every calendar date.
    """

    holiday_columns = [
        "Full_Date",
        "Holiday_Name",
        "Is_Public_Holiday",
        "Is_Bank_Holiday",
        "Is_Mercantile_Holiday",
        "Is_Poya_Day",
    ]

    final_df = calendar_df.merge(
        holiday_df[holiday_columns],
        on="Full_Date",
        how="left",
        validate="one_to_one",
    )

    # Non-holiday dates receive an empty holiday name
    final_df["Holiday_Name"] = (
        final_df["Holiday_Name"]
        .fillna("N/A")
        .astype(str)
        .str.strip()
    )

    # Non-holiday dates receive False
    for column in BOOLEAN_COLUMNS:
        final_df[column] = (
            final_df[column]
            .fillna(False)
            .apply(convert_to_boolean)
        )


    # Optional weekend flag
    final_df["Is_Weekend"] = (
        final_df["Full_Date"].dt.weekday >= 5
    )
    
    final_df["Is_Bank_Holiday"] = (
        final_df["Is_Bank_Holiday"]
        | final_df["Is_Weekend"]
    )
    
    # A date is considered a holiday if it belongs to any holiday category
    final_df["Is_Holiday"] = (
        (final_df["Holiday_Name"] != "N/A")
        | final_df["Is_Public_Holiday"]
        | final_df["Is_Bank_Holiday"]
        | final_df["Is_Mercantile_Holiday"]
        | final_df["Is_Poya_Day"]
    )
    
    # Save the date using YYYY-MM-DD format
    final_df["Full_Date"] = final_df[
        "Full_Date"
    ].dt.strftime("%Y-%m-%d")

    final_df = final_df[
        [
            "Full_Date",
            "Year",
            "Month",
            "Date",
            "Day",
            "Holiday_Name",
            "Is_Holiday",
            "Is_Public_Holiday",
            "Is_Bank_Holiday",
            "Is_Mercantile_Holiday",
            "Is_Poya_Day",
            "Is_Weekend",
        ]
    ]

    return final_df


def main():
    holiday_df = load_holiday_dataset()

    end_year = determine_end_year(
        holiday_df
    )

    calendar_df = create_calendar_dataset(
        start_year=START_YEAR,
        end_year=end_year,
    )

    final_df = merge_calendar_with_holidays(
        calendar_df,
        holiday_df,
    )

    final_df.to_csv(
        OUTPUT_CSV_PATH,
        index=False,
    )

    holiday_count = final_df[
        "Is_Holiday"
    ].sum()

    print(
        f"Complete date dataset created from "
        f"{START_YEAR}-01-01 to {end_year}-12-31."
    )

    print(
        f"Total dates: {len(final_df)}"
    )

    print(
        f"Holiday dates: {holiday_count}"
    )

    print(
        f"Saved at: {OUTPUT_CSV_PATH}"
    )


if __name__ == "__main__":
    main()