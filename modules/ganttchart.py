# modules/ganttchart.py
import pandas as pd
import os
from datetime import datetime
import json
from difflib import SequenceMatcher
from dateutil import parser
import boto3

# keep your call_haiku function (unchanged)
def call_haiku(prompt):
    bedrock = boto3.client(
        service_name='bedrock-runtime',
        region_name='ap-south-1'
    )

    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 1000,
        "temperature": 0.5,
        "top_p": 0.9,
    })

    response = bedrock.invoke_model(
        modelId='anthropic.claude-3-haiku-20240307-v1:0',
        body=body,
        contentType='application/json'
    )

    response_body = json.loads(response['body'].read())
    return response_body['content'][0]['text'].strip()


def fuzzy_find_column(df_columns, expected_names):
    """
    Try to match any column name to an expected_names list using:
      - exact / partial contains
      - fuzzy similarity fallback
    """
    df_cols = [c.lower().strip() for c in df_columns]

    # first pass: contains
    for expected in expected_names:
        expected_low = expected.lower()
        for idx, col in enumerate(df_cols):
            if expected_low in col:
                return df_columns[idx]

    # second pass: fuzzy similarity
    best_match = None
    best_ratio = 0.0
    for expected in expected_names:
        for idx, col in enumerate(df_cols):
            ratio = SequenceMatcher(None, expected.lower(), col).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = idx

    if best_ratio >= 0.45:
        return df_columns[best_match]
    return None


def smart_date_parse(value):
    """Parses nearly ANY date format including Excel serials."""
    if pd.isna(value):
        return pd.NaT
    
    # Excel serial number (float/int)
    if isinstance(value, (int, float)):
        try:
            return pd.Timestamp('1899-12-30') + pd.to_timedelta(int(value), unit='D')
        except:
            pass

    s = str(value).strip()
    if s == "":
        return pd.NaT

    # try multiple formats
    formats = [
        "%Y-%m-%d", "%d-%m-%Y", "%m-%d-%Y",
        "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d",
        "%d.%m.%Y", "%Y.%m.%d",
        "%d %b %Y", "%d %B %Y", "%b %d %Y", "%B %d %Y",
        "%Y%m%d", "%d%m%Y"
    ]

    for fmt in formats:
        try:
            return datetime.strptime(s, fmt)
        except:
            continue

    # final fallback → dateutil
    try:
        return parser.parse(s, dayfirst=False)
    except:
        try:
            return parser.parse(s, dayfirst=True)
        except:
            return pd.NaT



def generate_gantt_chart(excel_path, include_saturday=True, include_sunday=True):
    """
    Reads excel_path, detects Task/Start/End columns flexibly, parses dates,
    writes a Gantt excel and returns (output_excel_path, meta_dict).
    meta_dict contains keys: open_tasks (list), project_start, project_end
    """
    # read
    df = pd.read_excel(excel_path, engine='openpyxl')

    # detect columns
    task_col = fuzzy_find_column(df.columns, [
    "task","activity","activities","work","job","item","milestone","phase","title","task name","activity name",
    "description","summary"
    ])

    start_col = fuzzy_find_column(df.columns, [
    "start","start date","begin","from","launch","kickoff","starting","startday","planned start",
    "date start","begins","starting date"
    ])

    end_col = fuzzy_find_column(df.columns, [
    "end","end date","finish","to","deadline","completion","close","closing","planned end",
    "enddate","finish date","ending","ending date"
     ])

    if not task_col or not start_col or not end_col:
        # helpful: list detected columns and reason
        raise ValueError(f"Could not detect Task/Start/End columns. Found columns: {list(df.columns)}")

    # rename for consistency
    df = df.rename(columns={task_col: "Task", start_col: "Start Date", end_col: "End Date"})

    # parse dates robustly
    df["Start Date"] = df["Start Date"].apply(smart_date_parse)
    df["End Date"] = df["End Date"].apply(smart_date_parse)

    # find tasks with missing start or end
    missing_start = df[df["Start Date"].isna()]["Task"].tolist()
    missing_end = df[df["End Date"].isna()]["Task"].tolist()

    # If Start Date missing, raise — can't plot
    if len(missing_start) > 0:
        raise ValueError(f"The following tasks have missing/invalid Start Dates: {missing_start}")

    # For tasks with missing End Date, treat as open-ended: set to today for plotting
    today = pd.Timestamp.today().normalize()
    df.loc[df["End Date"].isna(), "End Date"] = today

    # Duration (days, inclusive)
    df["Duration (Days)"] = (df["End Date"] - df["Start Date"]).dt.days + 1

    # Prepare AI prompt (include weekend handling & open tasks)
    weekend_msg = []
    if not include_saturday:
        weekend_msg.append("Saturdays excluded")
    if not include_sunday:
        weekend_msg.append("Sundays excluded")
    weekend_info = ", ".join(weekend_msg) if weekend_msg else "All days included"

    open_tasks_msg = "No open-ended tasks."
    if missing_end:
        open_tasks_msg = "Open-ended tasks (no End Date provided): " + ", ".join(map(str, missing_end))

    prompt = f"""
      You are an expert project analyst. Analyze the project schedule below and generate a clear, structured summary.

      Weekend rules applied:
      - Saturdays included: {include_saturday}
      - Sundays included: {include_sunday}

      Additional logic notes:
      {weekend_info}
      {open_tasks_msg}

      Project Data:
      {df[['Task','Start Date','End Date','Duration (Days)']].to_string(index=False)}

      Please provide:
      1. Overall project timeline (start date, end date, total duration).
      2. Whether weekends were counted or excluded in calculations (mention Saturday/Sunday rules clearly).
      3. Key milestones (earliest starting task and latest ending task).
      4. Top 3 longest tasks (if duration > 10 days).
      5. List of overlapping/parallel tasks with short explanation.
      6. A concise 2–3 sentence final conclusion summarizing project pace and workload distribution.
    """

    try:
        haiku_summary = call_haiku(prompt)
    except Exception as e:
        # don't fail entire processing if AI call fails — provide fallback text
        haiku_summary = f"(AI summary failed: {e})"

    # date range
    all_dates = pd.date_range(df["Start Date"].min(), df["End Date"].max())
    if not include_saturday:
        all_dates = all_dates[all_dates.weekday != 5]
    if not include_sunday:
        all_dates = all_dates[all_dates.weekday != 6]

    # create output excel path
    base = os.path.splitext(excel_path)[0]
    output_excel = f"{base}_gantt_output.xlsx"

    # write excel
    writer = pd.ExcelWriter(output_excel, engine="xlsxwriter", datetime_format='yyyy-mm-dd')
    df.to_excel(writer, index=False, sheet_name="Task List")

    workbook = writer.book
    gantt_sheet = workbook.add_worksheet("Gantt Chart")
    # header row
    gantt_sheet.write(0, 0, "Task")
    for i, d in enumerate(all_dates):
        gantt_sheet.write(0, i + 1, d.strftime("%Y-%m-%d"))

    fill_fmt = workbook.add_format({"bg_color": "#4F81BD"})
    # write rows
    for r, row in df.iterrows():
        gantt_sheet.write(r + 1, 0, row["Task"])
        for c, d in enumerate(all_dates):
            if row["Start Date"] <= d <= row["End Date"]:
                gantt_sheet.write(r + 1, c + 1, "", fill_fmt)

    gantt_sheet.set_column(0, 0, 30)
    gantt_sheet.set_column(1, len(all_dates), 12)

    # AI summary sheet
    summary_sheet = workbook.add_worksheet("AI Summary")
    summary_sheet.write("A1", "Project Analysis:")
    summary_sheet.write("A3", haiku_summary)

    writer.close()

    meta = {
        "open_tasks": missing_end,
        "project_start": df["Start Date"].min(),
        "project_end": df["End Date"].max(),
        "ai_summary": haiku_summary
    }

    return output_excel, meta
