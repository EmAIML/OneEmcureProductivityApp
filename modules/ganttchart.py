import pandas as pd
import matplotlib.pyplot as plt
import os
from datetime import datetime
import boto3
import json
import tempfile


def call_haiku(prompt):
    """
    Calls AWS Bedrock's Claude 3 Haiku model with the given prompt using Messages API.
    Returns the model's completion.
    """
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


def generate_gantt_chart(excel_path, include_saturday=True, include_sunday=True):
    # your existing code with date filtering logic based on these two params

    """
    Reads Excel, generates a Gantt chart in Excel using colored cells (not image),
    and adds Claude 3 Haiku AI analysis.
    """

    # Read Excel
    df = pd.read_excel(excel_path)

    # Validate columns
    required_columns = ['Task', 'Start Date', 'End Date']
    if not all(col in df.columns for col in required_columns):
        raise ValueError(f"Excel must contain the columns: {', '.join(required_columns)}")

    # Clean and parse dates
    df['Start Date'] = pd.to_datetime(df['Start Date'])
    df['End Date'] = pd.to_datetime(df['End Date'])

    # Add duration (including both start and end)
    df['Duration (Days)'] = (df['End Date'] - df['Start Date']).dt.days + 1

    # --- Claude AI Summary ---
    prompt = f"""You are a smart project analyst. Below is a table of tasks with their start and end dates:

{df[['Task', 'Start Date', 'End Date', 'Duration (Days)']].to_string(index=False)}

1. Identify any long tasks (duration > 10 days).
2. Suggest how to optimize the schedule if possible.
3. Summarize the overall timeline in 3-4 sentences."""
    haiku_summary = call_haiku(prompt)

    # --- Determine full date range ---
    all_dates = pd.date_range(df['Start Date'].min(), df['End Date'].max())

    # Remove Saturdays or Sundays if not included
    if not include_saturday and not include_sunday:
        all_dates = all_dates[~all_dates.weekday.isin([5, 6])]
    elif not include_saturday:
        all_dates = all_dates[~all_dates.weekday.isin([5])]
    elif not include_sunday:
        all_dates = all_dates[~all_dates.weekday.isin([6])]
    # else: include both days, do nothing

    # --- Prepare Excel Writer ---
    output_excel = os.path.splitext(excel_path)[0] + '_gantt_output.xlsx'
    writer = pd.ExcelWriter(output_excel, engine='xlsxwriter')
    workbook = writer.book

    # --- Sheet 1: Task List ---
    df.to_excel(writer, index=False, sheet_name='Task List')

    # --- Sheet 2: Gantt Chart ---
    gantt_sheet = workbook.add_worksheet('Gantt Chart')

    # Write headers (dates)
    gantt_sheet.write(0, 0, 'Task')
    for idx, date in enumerate(all_dates):
        gantt_sheet.write(0, idx + 1, date.strftime('%Y-%m-%d'))

    # Define fill color for task durations
    fill_format = workbook.add_format({'bg_color': '#4F81BD'})

    # Fill Gantt chart rows
    for row_idx, task in df.iterrows():
        gantt_sheet.write(row_idx + 1, 0, task['Task'])

        for col_idx, date in enumerate(all_dates):
            if task['Start Date'] <= date <= task['End Date']:
                gantt_sheet.write(row_idx + 1, col_idx + 1, '', fill_format)

    # Adjust column widths
    gantt_sheet.set_column(0, 0, 25)
    gantt_sheet.set_column(1, len(all_dates), 12)

    # --- Sheet 3: AI Summary ---
    summary_sheet = workbook.add_worksheet('AI Summary')
    summary_sheet.write('A1', 'Project Analysis from Claude 3 Haiku:')
    summary_sheet.write('A3', haiku_summary)

    writer.close()
    return output_excel

