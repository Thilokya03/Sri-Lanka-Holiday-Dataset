import pandas as pd
import pathlib
import datetime

CBS_CSV_PATH = pathlib.Path(__file__).parent.parent / "csv" / "CBS_holidays.csv"

DOCUMENT_CSV_PATH = pathlib.Path(__file__).parent.parent / "csv" / "Document_gov_holidays.csv"

months = {
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
    "December": 12
}

def formating_df(year, month, date):
    
    date = datetime.date(year, months[month], int(date))
    return date.strftime("%Y-%m-%d")

def is_poya_day(name):
    if "poya day" in name.lower():
        return True
    return False

def combine_df(df1,df2):
    combined_df = pd.concat([df1, df2], ignore_index=True)
    combined_df = combined_df.drop_duplicates()
    return combined_df

if __name__ == "__main__":
    CBS_df = pd.read_csv(CBS_CSV_PATH)
    Document_df = pd.read_csv(DOCUMENT_CSV_PATH)
    
    new_df = combine_df(CBS_df, Document_df)
    new_df['Full_Date'] = new_df.apply(lambda row: formating_df(row['Year'], row['Month'], row['Date']), axis=1)
    
    new_df['Is_Poya_Day'] = new_df.apply(lambda row: is_poya_day(row['Holiday_Name']), axis=1)
    
    new_df = new_df[['Full_Date', 'Year', 'Month', 'Date', 'Day', 'Holiday_Name','Is_Public_Holiday', 'Is_Bank_Holiday','Is_Mercantile_Holiday','Is_Poya_Day']]
    
    new_df.sort_values(by=['Full_Date'], inplace=True)
    
    new_df.to_csv(pathlib.Path(__file__).parent.parent / "csv" / "Combined_holidays.csv", index=False)
    
    print("Combined CSV file created successfully at: ", pathlib.Path(__file__).parent.parent / "csv" / "Combined_holidays.csv")
    



