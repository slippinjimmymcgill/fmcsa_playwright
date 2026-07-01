import pandas as pd

def parse_inspections(file_path: str) -> list[dict]:
    """
    Parse the SMS inspection Excel file and return a list of inspection records.
    """
    try:
        # SMS Excel files may have a header row offset — adjust skiprows if needed
        df = pd.read_excel(file_path, engine="openpyxl", skiprows=0)
        df.columns = [str(c).strip() for c in df.columns]

        # Drop fully empty rows
        df.dropna(how="all", inplace=True)

        # Normalize column names for the frontend
        df.rename(columns={
            "Report Number": "report_number",
            "Inspection Date": "inspection_date",
            "State": "state",
            "Level": "level",
            "Vehicle OOS": "vehicle_oos",
            "Driver OOS": "driver_oos",
            "Hazmat OOS": "hazmat_oos",
            "Total Violations": "total_violations",
        }, inplace=True)

        # Convert dates to strings so JSON serialization works
        for col in df.select_dtypes(include=["datetime64[ns]"]).columns:
            df[col] = df[col].dt.strftime("%Y-%m-%d")

        return df.fillna("").to_dict(orient="records")

    except Exception as e:
        print(f"[Parser] Error parsing Excel: {e}")
        return []