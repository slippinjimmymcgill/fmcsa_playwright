import pandas as pd


def parse_inspections(file_path: str) -> list[dict]:
    try:
        xl = pd.ExcelFile(file_path, engine="openpyxl")
        sheet_name = "Inspections" if "Inspections" in xl.sheet_names else xl.sheet_names[0]

        # Row 0 = group labels, Row 1 = real column names, data starts row 2
        # skiprows=1 skips row 0, making row 1 the header
        df = pd.read_excel(file_path, sheet_name=sheet_name, engine="openpyxl", skiprows=1)
        df.dropna(how="all", inplace=True)
        df.columns = [str(c).strip() for c in df.columns]

        df.rename(columns={
            "Date":                             "inspection_date",
            "State":                            "state",
            "Number":                           "report_number",
            "Level":                            "level",
            "Placardable HM Vehicle Inspection":"placardable_hm",
            "HM Inspection":                    "hm_inspection",
            "BASIC":                            "basic",
            "Violation Group Description":      "violation_group",
            "Code":                             "violation_code",
            "Description":                      "violation_description",
            "Out of Service":                   "out_of_service",
            "Convicted of a Different Charge":  "convicted_different_charge",
            "Violation Severity Weight":        "violation_severity_weight",
            "Time Weight":                      "time_weight",
            "BASIC Violations per Inspection":  "basic_violations_per_inspection",
            "Unit":                             "unit",
        }, inplace=True)

        # Convert datetime columns to strings
        for col in df.select_dtypes(include=["datetime64[ns]"]).columns:
            df[col] = df[col].dt.strftime("%Y-%m-%d")

        # Only drop rows where ALL key inspection fields are empty
        key_cols = [c for c in ["inspection_date", "report_number", "state"] if c in df.columns]
        if key_cols:
            df = df.dropna(subset=key_cols, how="all")

        return df.fillna("").to_dict(orient="records")

    except Exception as e:
        print(f"[Parser] Error parsing Excel: {e}")
        return []


def parse_crashes(file_path: str) -> list[dict]:
    try:
        xl = pd.ExcelFile(file_path, engine="openpyxl")
        if "Crashes" not in xl.sheet_names:
            return []

        df = pd.read_excel(file_path, sheet_name="Crashes", engine="openpyxl", skiprows=1)
        df.dropna(how="all", inplace=True)
        df.columns = [str(c).strip() for c in df.columns]

        df.rename(columns={
            "Date":                 "crash_date",
            "State":                "state",
            "Number":               "report_number",
            "Fatalities":           "fatalities",
            "Injuries":             "injuries",
            "Tow-Away":             "tow_away",
            "HM Released":          "hm_released",
            "Not Preventable Flag": "not_preventable",
        }, inplace=True)

        for col in df.select_dtypes(include=["datetime64[ns]"]).columns:
            df[col] = df[col].dt.strftime("%Y-%m-%d")

        key_cols = [c for c in ["crash_date", "report_number", "state"] if c in df.columns]
        if key_cols:
            df = df.dropna(subset=key_cols, how="all")

        return df.fillna("").to_dict(orient="records")

    except Exception as e:
        print(f"[Parser] Error parsing crashes: {e}")
        return []