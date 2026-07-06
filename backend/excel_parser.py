import pandas as pd

def parse_inspections(file_path: str) -> list[dict]:
    """
    Parse the SMS inspection Excel file and return a list of inspection records.

    The Excel file has multiple sheets. We read the 'Inspections' sheet which has a two-row header:
    - Row 0: group labels (Report, Violation, Vehicle Unit #1, etc.)
    - Row 1: actual column names (Date, State, Number, Level, etc.)

    We skip Row 0 and use Row 1 as the header.
    """
    try:
        xl = pd.ExcelFile(file_path, engine="openpyxl")

        # use Inspections sheet if available, else fall back to first sheet
        sheet_name = "Inspections" if "Inspections" in xl.sheet_names else xl.sheet_names[0]

        # skiprows=1 to skip the first row of group labels, leaving real column names as header
        df = pd.read_excel(xl, sheet_name=sheet_name, skiprows=1, engine="openpyxl")

        # drop any completely empty rows
        df.dropna(how="all", inplace=True)

        # clean column names
        df.columns = [str(c).strip() for c in df.columns]

        # Real column names from row 1 are:
        # Date, State, Number, Level, Placardable HM Vehicle Inspection, HM Inspection,
        # BASIC, Violation Group Description, Code, Description, Out of Service,
        # Convicted of a Different Charge, Violation Severity Weight, Time Weight,
        # BASIC Violations per Inspection, Unit, Type, Make, License State,
        # License Number, VIN, Type, Make, License State, License Number, VIN

        # Rename to friendly keys for the frontend
        df.rename(columns={
            "Date": "inspection_date",
            "State": "state",
            "Number": "report_number",
            "Level": "level",
            "Placardable HM Vehicle Inspection": "placardable_hm",
            "HM Inspection": "hm_inspection",
            "BASIC": "basic",
            "Violation Group Description": "violation_group",
            "Code": "violation_code",
            "Description": "violation_description",
            "Out of Service": "out_of_service",
            "Convicted of a Different Charge": "convicted_different_charge",
            "Violation Severity Weight": "violation_severity_weight",
            "Time Weight": "time_weight",
            "BASIC Violations per Inspection": "basic_violations_per_inspection",
            "Unit": "unit",
        }, inplace=True)

        # Convert date columns to strings
        for col in df.select_dtypes(include=["datetime64[ns]", "datetime64[ns, UTC]"]).columns:
            df[col] = df[col].dt.strftime("%Y-%m-%d")
        
        # Drop rows where inspection_date is missing (they're subrows/continuation rows)
        if "inspection_date" in df.columns:
            df = df[df["inspection_date"].notna() & (df["inspection_date"] != "")]
        
        return df.fillna("").to_dict(orient="records")
    
    except Exception as e:
        print(f"[Parser] Error parsing Excel: {e}")
        return []

def parse_crashes(file_path: str) -> list[dict]:
    """
    Parse the Crashes sheet from the SMS Excel file.
    Also has a two-row header like the Inspections sheet.
    """
    try:
        xl = pd.ExcelFile(file_path, engine="openpyxl")
        if "Crashes" not in xl.sheet_names:
            return []
        
        df = pd.read_excel(file_path, sheet_name="Crashes", skiprows=1, engine="openpyxl")
        df.dropna(how="all", inplace=True)
        df.columns = [str(c).strip() for c in df.columns]

        df.rename(columns={
            "Date": "crash_date",
            "State": "state",
            "Number": "report_number",
            "Fatalities": "fatalities",
            "Injuries": "injuries",
            "Tow-Away": "tow_away",
            "HM Released": "hm_released",
            "Not Preventable Flag": "not_preventable_flag",
        }, inplace=True)

        for col in df.select_dtypes(include=["datetime64[ns]"]).columns:
            df[col] = df[col].dt.strftime("%Y-%m-%d")
        
        if "crash_date" in df.columns:
            df = df[df["crash_date"].notna() & (df["crash_date"] != "")]
        
        return df.fillna("").to_dict(orient="records")
    
    except Exception as e:
        print(f"[Parser] Error parsing crashes: {e}")
        return []