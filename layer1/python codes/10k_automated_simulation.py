import re
import subprocess
import tempfile
from pathlib import Path

import pandas as pd


# ============================================================
# CONFIGURATION
# ============================================================

BASE_DIR = Path(r"C:\ngspice\Spice64\bin")

NGSPICE = BASE_DIR / "ngspice_con.exe"

MODEL_FILE = BASE_DIR / "32nm_LP.pm"

OUTPUT_DIR = BASE_DIR / "generated_results"

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# FOUR CASES
# ============================================================

CASES = {

    "nmos_on": {
        "csv": BASE_DIR / "nmos_on.csv",
        "sp": BASE_DIR / "nmos_on.sp",
        "device": "nmos",
    },

    "nmos_off": {
        "csv": BASE_DIR / "nmos_off.csv",
        "sp": BASE_DIR / "nmos_off.sp",
        "device": "nmos",
    },

    "pmos_on": {
        "csv": BASE_DIR / "pmos_on.csv",
        "sp": BASE_DIR / "pmos_on.sp",
        "device": "pmos",
    },

    "pmos_off": {
        "csv": BASE_DIR / "pmos_off.csv",
        "sp": BASE_DIR / "pmos_off.sp",
        "device": "pmos",
    },
}


# ============================================================
# PARAMETERS IN .SP
# ============================================================

SP_PARAMETERS = [
    "VDD",
    "TEMP",
    "W",
    "VD",
    "VS",
    "VG",
    "VB",
]


# ============================================================
# PARAMETERS IN 32nm_LP.pm
# ============================================================

MODEL_PARAMETERS = [
    "vth0",
    "toxe",
    "ndep",
    "u0",
    "xj",
]


# ============================================================
# MODEL NAMES
# ============================================================

NMOS_MODEL_NAME = "nmos"

PMOS_MODEL_NAME = "pmos"


# ============================================================
# NORMALIZE COLUMN NAME
# ============================================================

def normalize_column_name(name):

    name = str(name).strip().lower()

    name = name.replace(" ", "")
    name = name.replace("_", "")

    aliases = {

        "vdd": "vdd",

        "temp": "temp",
        "temperature": "temp",

        "w": "w",

        "vd": "vd",
        "drain": "vd",

        "vs": "vs",
        "source": "vs",

        "vg": "vg",
        "gate": "vg",

        "vb": "vb",
        "body": "vb",

        "vth0": "vth0",

        "toxe": "toxe",

        "ndep": "ndep",

        "u0": "u0",

        "xj": "xj",
    }

    return aliases.get(
        name,
        name
    )


# ============================================================
# LOAD CSV
# ============================================================

def load_input_csv(csv_file):

    print()
    print(f"Reading CSV:")
    print(csv_file)

    df = pd.read_csv(csv_file)

    # Normalize columns
    rename_map = {}

    for column in df.columns:

        rename_map[column] = (
            normalize_column_name(column)
        )

    df = df.rename(
        columns=rename_map
    )

    required_columns = [

        "vdd",
        "temp",
        "w",
        "vd",
        "vs",
        "vg",
        "vb",

        "vth0",
        "toxe",
        "ndep",
        "u0",
        "xj",
    ]

    missing = [

        col

        for col in required_columns

        if col not in df.columns
    ]

    if missing:

        raise ValueError(
            "\nMissing columns:\n"
            + "\n".join(
                f"  - {x}"
                for x in missing
            )
            + "\n\nAvailable columns:\n"
            + str(list(df.columns))
        )

    print(
        f"Rows found: {len(df)}"
    )

    return df


# ============================================================
# CONVERT VALUE TO SPICE FORMAT
# ============================================================

def spice_value(value):

    if pd.isna(value):

        raise ValueError(
            "NaN value found in CSV"
        )

    # Keep scientific notation
    return f"{float(value):.12g}"


# ============================================================
# FIND MODEL BLOCK
# ============================================================

def find_model_block(
    text,
    model_name
):

    """
    Finds:

        .model nmos nmos level = 54

    OR:

        .model pmos pmos level = 54

    The model does NOT use parentheses.

    The block ends at the next .model statement.
    """

    pattern = re.compile(

        rf"^\s*\.model\s+"
        rf"{re.escape(model_name)}"
        rf"\s+",

        re.IGNORECASE |
        re.MULTILINE
    )

    match = pattern.search(text)

    if not match:

        raise ValueError(
            f"Could not find model "
            f"'{model_name}'"
        )

    start = match.start()

    # Search after current model
    remaining = text[match.end():]

    next_model = re.search(

        r"^\s*\.model\s+",

        remaining,

        re.IGNORECASE |
        re.MULTILINE
    )

    if next_model:

        end = (
            match.end()
            + next_model.start()
        )

    else:

        end = len(text)

    return start, end


# ============================================================
# MODIFY MODEL PARAMETER
# ============================================================

def modify_model_parameter(
    model_block,
    parameter,
    value
):

    """
    Replace:

        vth0 = OLD_VALUE

    with:

        vth0 = NEW_VALUE
    """

    pattern = re.compile(

        rf"(\b{re.escape(parameter)}"
        rf"\s*=\s*)"

        rf"([^\s\+\r\n]+)",

        re.IGNORECASE
    )

    new_block, count = pattern.subn(

        rf"\g<1>{value}",

        model_block,

        count=1
    )

    if count == 0:

        raise ValueError(
            f"Parameter '{parameter}' "
            f"not found in model "
            f"block."
        )

    return new_block


# ============================================================
# CREATE MODIFIED MODEL
# ============================================================

def create_modified_model(
    row,
    device,
    destination_model
):

    # Read original 32nm model
    text = MODEL_FILE.read_text(
        encoding="utf-8",
        errors="ignore"
    )

    # --------------------------------------------------------
    # Select model
    # --------------------------------------------------------

    if device.lower() == "nmos":

        model_name = NMOS_MODEL_NAME

    elif device.lower() == "pmos":

        model_name = PMOS_MODEL_NAME

    else:

        raise ValueError(
            f"Invalid device: {device}"
        )

    # --------------------------------------------------------
    # Find model block
    # --------------------------------------------------------

    start, end = find_model_block(
        text,
        model_name
    )

    model_block = text[start:end]

    # --------------------------------------------------------
    # Modify ONLY selected model
    # --------------------------------------------------------

    for parameter in MODEL_PARAMETERS:

        value = spice_value(
            row[parameter]
        )

        model_block = modify_model_parameter(

            model_block,

            parameter,

            value
        )

    # --------------------------------------------------------
    # Reconstruct entire PM file
    # --------------------------------------------------------

    modified_text = (

        text[:start]

        + model_block

        + text[end:]
    )

    # --------------------------------------------------------
    # Save
    # --------------------------------------------------------

    destination_model.write_text(

        modified_text,

        encoding="utf-8"
    )


# ============================================================
# MODIFY .PARAM IN SP FILE
# ============================================================

def modify_sp_parameter(
    text,
    parameter,
    value
):

    """
    Handles:

        .param VDD = 0.9

    and

        .param VDD=0.9

    and importantly:

        .param VG = {VDD}

    """

    pattern = re.compile(

        rf"(^\s*\.param\s+"
        rf"{re.escape(parameter)}"
        rf"\s*=\s*)"

        rf"([^\r\n]*)",

        re.IGNORECASE |
        re.MULTILINE
    )

    new_text, count = pattern.subn(

        rf"\g<1>{value}",

        text,

        count=1
    )

    if count == 0:

        raise ValueError(

            f"Could not find "
            f".param {parameter} "
            f"in SPICE file."
        )

    return new_text


# ============================================================
# MODIFY SP FILE
# ============================================================

def create_modified_sp(
    original_sp,
    row,
    destination_sp,
    temporary_model
):

    text = original_sp.read_text(
        encoding="utf-8",
        errors="ignore"
    )

    # --------------------------------------------------------
    # Change all .PARAM values
    # --------------------------------------------------------

    for parameter in SP_PARAMETERS:

        value = spice_value(
            row[
                parameter.lower()
            ]
        )

        text = modify_sp_parameter(

            text,

            parameter,

            value
        )

    # --------------------------------------------------------
    # Replace .include line
    # --------------------------------------------------------

    include_pattern = re.compile(

        r"(^\s*\.include\s+)"
        r"[^\r\n]+",

        re.IGNORECASE |
        re.MULTILINE
    )

    new_text, count = include_pattern.subn(

        lambda m:
            m.group(1)
            + f'"{temporary_model}"',

        text,

        count=1
    )

    if count == 0:

        raise ValueError(

            f"No .include statement "
            f"found in {original_sp.name}"
        )

    text = new_text

    # --------------------------------------------------------
    # Save modified SPICE file
    # --------------------------------------------------------

    destination_sp.write_text(

        text,

        encoding="utf-8"
    )


# ============================================================
# RUN NGSPICE
# ============================================================

def run_ngspice(
    spice_file
):

    command = [

        str(NGSPICE),

        "-b",

        str(spice_file)
    ]

    process = subprocess.run(

        command,

        stdout=subprocess.PIPE,

        stderr=subprocess.STDOUT,

        text=True,

        cwd=str(spice_file.parent)
    )

    return (

        process.returncode,

        process.stdout
    )


# ============================================================
# EXTRACT CURRENT FROM NGSPICE OUTPUT
# ============================================================

def extract_current(
    output,
    variable_name
):

    """
    Your .sp files contain:

        print ID
        print IG
        print IS
        print IB

    NGSPICE normally prints something similar to:

        ID = 1.234e-09

    This function extracts the numerical value.
    """

    pattern = re.compile(

        rf"\b{variable_name}\b"
        rf"\s*=\s*"
        rf"([-+]?"
        rf"(?:\d+(?:\.\d*)?"
        rf"|\.\d+)"
        rf"(?:[eE][-+]?\d+)?"
        rf")",

        re.IGNORECASE
    )

    matches = pattern.findall(
        output
    )

    if not matches:

        return None

    return float(
        matches[-1]
    )


# ============================================================
# EXTRACT ALL FOUR CURRENTS
# ============================================================

def extract_currents(output):

    return {

        "ID":
            extract_current(
                output,
                "ID"
            ),

        "IG":
            extract_current(
                output,
                "IG"
            ),

        "IS":
            extract_current(
                output,
                "IS"
            ),

        "IB":
            extract_current(
                output,
                "IB"
            ),
    }


# ============================================================
# PROCESS ONE CASE
# ============================================================

def process_case(
    case_name,
    config,
    max_rows=None
):

    print()
    print("=" * 70)
    print(
        f"CASE: {case_name}"
    )
    print("=" * 70)

    csv_file = config["csv"]

    sp_file = config["sp"]

    device = config["device"]

    # --------------------------------------------------------
    # Load CSV
    # --------------------------------------------------------

    df = load_input_csv(
        csv_file
    )

    if max_rows is not None:

        df = df.head(
            max_rows
        )

    print(
        f"SPICE file : {sp_file}"
    )

    print(
        f"Device     : {device}"
    )

    print(
        f"Simulations: {len(df)}"
    )

    results = []

    # --------------------------------------------------------
    # Temporary directory
    # --------------------------------------------------------

    with tempfile.TemporaryDirectory(
        prefix=f"{case_name}_"
    ) as temp_dir:

        temp_dir = Path(
            temp_dir
        )

        # ----------------------------------------------------
        # Process each input row
        # ----------------------------------------------------

        for index, row in df.iterrows():

            sample_id = index + 1

            print(
                f"[{case_name}] "
                f"Running "
                f"{sample_id}/{len(df)}",
                end="\r"
            )

            # =================================================
            # STEP 1
            # Create modified model
            # =================================================

            temporary_model = (

                temp_dir

                / f"model_{sample_id}.pm"
            )

            create_modified_model(

                row,

                device,

                temporary_model
            )

            # =================================================
            # STEP 2
            # Create modified SPICE
            # =================================================

            temporary_sp = (

                temp_dir

                / f"simulation_{sample_id}.sp"
            )

            create_modified_sp(

                sp_file,

                row,

                temporary_sp,

                temporary_model
            )

            # =================================================
            # STEP 3
            # Run NGSPICE
            # =================================================

            return_code, output = (

                run_ngspice(
                    temporary_sp
                )
            )

            # =================================================
            # STEP 4
            # Check simulation
            # =================================================

            if return_code != 0:

                error_file = (

                    OUTPUT_DIR

                    / f"{case_name}_"
                    f"error_{sample_id}.txt"
                )

                error_file.write_text(

                    output,

                    encoding="utf-8"
                )

                raise RuntimeError(

                    f"\n\nNGSPICE FAILED\n"
                    f"Case: {case_name}\n"
                    f"Sample: {sample_id}\n"
                    f"Output saved to:\n"
                    f"{error_file}"
                )

            # =================================================
            # STEP 5
            # Extract currents
            # =================================================

            currents = extract_currents(
                output
            )

            # =================================================
            # Check currents
            # =================================================

            missing = [

                name

                for name, value
                in currents.items()

                if value is None
            ]

            if missing:

                output_file = (

                    OUTPUT_DIR

                    / f"{case_name}_"
                    f"output_{sample_id}.txt"
                )

                output_file.write_text(

                    output,

                    encoding="utf-8"
                )

                raise RuntimeError(

                    f"\n\nCould not extract "
                    f"currents: {missing}\n"
                    f"Case: {case_name}\n"
                    f"Sample: {sample_id}\n"
                    f"NGSPICE output saved to:\n"
                    f"{output_file}"
                )

            # =================================================
            # STEP 6
            # Save input + currents
            # =================================================

            result = {

                "Sample_ID":
                    sample_id,

                # ---------------------------------------------
                # SP PARAMETERS
                # ---------------------------------------------

                "VDD":
                    row["vdd"],

                "TEMP":
                    row["temp"],

                "W":
                    row["w"],

                "VD":
                    row["vd"],

                "VS":
                    row["vs"],

                "VG":
                    row["vg"],

                "VB":
                    row["vb"],

                # ---------------------------------------------
                # MODEL PARAMETERS
                # ---------------------------------------------

                "VTH0":
                    row["vth0"],

                "TOXE":
                    row["toxe"],

                "NDEP":
                    row["ndep"],

                "U0":
                    row["u0"],

                "XJ":
                    row["xj"],

                # ---------------------------------------------
                # CURRENT OUTPUT
                # ---------------------------------------------

                "ID":
                    currents["ID"],

                "IG":
                    currents["IG"],

                "IS":
                    currents["IS"],

                "IB":
                    currents["IB"],
            }

            results.append(
                result
            )

    # ========================================================
    # CREATE RESULT DATAFRAME
    # ========================================================

    result_df = pd.DataFrame(
        results
    )

    # ========================================================
    # SAVE RESULT CSV
    # ========================================================

    output_file = (

        OUTPUT_DIR

        / f"{case_name}_results.csv"
    )

    result_df.to_csv(

        output_file,

        index=False
    )

    print()

    print(
        f"\nCompleted {case_name}"
    )

    print(
        f"Rows: {len(result_df)}"
    )

    print(
        f"Output:"
    )

    print(
        output_file
    )

    return result_df


# ============================================================
# CHECK REQUIRED FILES
# ============================================================

def check_files():

    print()
    print("=" * 70)
    print("CHECKING FILES")
    print("=" * 70)

    # --------------------------------------------------------
    # NGSPICE
    # --------------------------------------------------------

    if not NGSPICE.exists():

        raise FileNotFoundError(

            f"NGSPICE not found:\n"
            f"{NGSPICE}"
        )

    print(
        "[OK] ngspice_con.exe"
    )

    # --------------------------------------------------------
    # MODEL
    # --------------------------------------------------------

    if not MODEL_FILE.exists():

        raise FileNotFoundError(

            f"Model file not found:\n"
            f"{MODEL_FILE}"
        )

    print(
        "[OK] 32nm_LP.pm"
    )

    # --------------------------------------------------------
    # CASE FILES
    # --------------------------------------------------------

    for case_name, config in CASES.items():

        csv_file = config["csv"]

        sp_file = config["sp"]

        if not csv_file.exists():

            raise FileNotFoundError(

                f"\nCSV missing:\n"
                f"{csv_file}"
            )

        print(
            f"[OK] {csv_file.name}"
        )

        if not sp_file.exists():

            raise FileNotFoundError(

                f"\nSPICE missing:\n"
                f"{sp_file}"
            )

        print(
            f"[OK] {sp_file.name}"
        )


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 70)
    print(
        "32nm PVT LEAKAGE DATA GENERATOR"
    )
    print("=" * 70)

    # --------------------------------------------------------
    # Check everything
    # --------------------------------------------------------

    check_files()

    # --------------------------------------------------------
    # IMPORTANT:
    #
    # First test ONLY 1 row.
    #
    # Change to None after successful test.
    # --------------------------------------------------------

    TEST_ROWS = None
    TEST_ROWS = None

    # --------------------------------------------------------
    # Run four cases
    # --------------------------------------------------------

    for case_name, config in CASES.items():

        process_case(

            case_name,

            config,

            max_rows=TEST_ROWS
        )

    print()
    print("=" * 70)
    print(
        "TEST RUN COMPLETED"
    )
    print("=" * 70)

    print()
    print(
        "If the four result CSVs look correct,"
    )

    print(
        "change TEST_ROWS = 1 to TEST_ROWS = None"
    )

    print(
        "to process all 10,000 rows per case."
    )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    main()