import requests
from bs4 import BeautifulSoup
import pandas as pd
import datetime
import pathlib
import time



PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
CSV_DIRECTORY = PROJECT_ROOT / "csv"
CBS_CSV_PATH = CSV_DIRECTORY / "CBS_holidays.csv"

def get_html_content(url:str):
    response = requests.get(url)
    if response.status_code == 200:
        return response.text
    else:
        print(f"Failed to retrieve the webpage. Status code: {response.status_code}")
        return None

def extract_holidays(year:int ,html_content:str):
    holidays = []
    
    soup = BeautifulSoup(html_content, 'html.parser')
    quotes = soup.find_all('tr')
    
    for quote in quotes:
        raw = quote.get_text(separator=",", strip=True)
        raw = raw.replace("\xa0", "").strip(",")
        content = raw.split(",")
        if 4 > len(content) > 2:
            # print(f"Year: {year}, Content: {content}")
            typeOfHoliday = ""
            try:
                typeOfHoliday = f'B. {content[2].split("B.")[1].strip()}'
            except IndexError:
                if "Special Bank" in content[2]:
                    typeOfHoliday = "B."
            holidays.append([
                year,
                content[0].split()[0].strip(), 
                int(content[0].split()[1].strip()),
                content[1].strip(), 
            content[2].split("B.")[0].strip(), 
            'P' in typeOfHoliday,
            'B' in typeOfHoliday,
            'M' in typeOfHoliday])
    return holidays

def create_csv(holidays:list):
    # Create a DataFrame from the holidays list
    if not holidays:
        print("No holidays data to save.")
        return False
    
    df = pd.DataFrame(holidays, columns=[
                                        "Year", 
                                        "Month", 
                                        'Date', 
                                        'Day', 
                                        'Holiday_Name', 
                                        "Is_Public_Holiday",
                                        "Is_Bank_Holiday",
                                        "Is_Mercantile_Holiday"])
    
    path = pathlib.Path(CBS_CSV_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    if path.exists() and path.stat().st_size > 0:
        pre_df = pd.read_csv(path)
        df = pd.concat([pre_df, df], ignore_index=True)

        df = df.drop_duplicates(
            subset=["Year", "Month", "Date", "Holiday_Name"],
            keep="last"
        )

    df.to_csv(CBS_CSV_PATH, index=False)
    return True


if __name__ == "__main__":
    thisyear = datetime.datetime.now().year
    for year in range(2019, thisyear + 1):
        url = f"https://www.cbsl.gov.lk/en/about/about-the-bank/bank-holidays-{year}"
        html_content = get_html_content(url)
        if html_content:
            holidays = extract_holidays(year, html_content)
            if create_csv(holidays):
                print(f"Successfully created/updated the CSV file for year {year} to {CBS_CSV_PATH}.")
            else:
                print(f"Failed to create/update the CSV file for year {year}.")

        time.sleep(1)  # Throttle requests to be polite / avoid rate limiting