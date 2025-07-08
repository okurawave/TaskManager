import os
from datetime import datetime, timedelta

import gspread
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials

# It's good practice to define constants for column names
COL_TASK_ID = "task_id"
COL_TITLE = "title"
COL_STATUS = "status"
COL_ASSIGNEE_ID = "assignee_id"
COL_DUE_DATE = "due_date"
COL_CREATED_AT = "created_at"

STATUS_PENDING = "pending"
STATUS_COMPLETED = "completed"

# Load environment variables
load_dotenv()

SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
WORKSHEET_NAME = os.getenv("WORKSHEET_NAME", "Tasks") # Default to "Tasks"
GOOGLE_CREDS_PATH = os.getenv("GOOGLE_CREDS_PATH")

def get_sheet():
    """Authenticates with Google Sheets and returns the specific worksheet."""
    if not GOOGLE_CREDS_PATH:
        raise ValueError("GOOGLE_CREDS_PATH environment variable not set.")
    if not SPREADSHEET_ID:
        raise ValueError("SPREADSHEET_ID environment variable not set.")

    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_file(GOOGLE_CREDS_PATH, scopes=scopes)
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(SPREADSHEET_ID)
        worksheet = spreadsheet.worksheet(WORKSHEET_NAME)
        return worksheet
    except Exception as e:
        print(f"Error connecting to Google Sheets: {e}")
        # In a real bot, you might want to raise this or handle it more gracefully
        # For now, we'll let it propagate to alert during development
        raise

def init_sheet(worksheet):
    """Initializes the worksheet with headers if it's empty."""
    headers = [COL_TASK_ID, COL_TITLE, COL_STATUS, COL_ASSIGNEE_ID, COL_DUE_DATE, COL_CREATED_AT]
    if not worksheet.row_values(1): # Check if the first row is empty
        worksheet.append_row(headers)
        print(f"Initialized worksheet '{WORKSHEET_NAME}' with headers.")

# --- Placeholder functions to be implemented ---

def get_next_task_id(worksheet):
    """Gets the next available task_id. Assumes task_id is in the first column."""
    try:
        task_ids = worksheet.col_values(1) # Get all values from the first column (task_id)
        if not task_ids or len(task_ids) <= 1: # Only headers or empty
            return 1

        # Convert to int, filter out non-numeric values (like the header)
        numeric_ids = [int(id_val) for id_val in task_ids[1:] if id_val.isdigit()]
        if not numeric_ids:
            return 1
        return max(numeric_ids) + 1
    except Exception as e:
        print(f"Error getting next task ID: {e}")
        raise

def add_task(worksheet, title: str, assignee_id: str = None, due_date: str = None):
    """Adds a new task to the sheet.
    Due_date should be in 'YYYY-MM-DD HH:MM' format or None.
    Assignee_id can be None.
    """
    try:
        task_id = get_next_task_id(worksheet)
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        status = STATUS_PENDING

        row = [
            task_id,
            title,
            status,
            assignee_id if assignee_id else "", # Store empty string if None for Sheets
            due_date if due_date else "",       # Store empty string if None
            created_at
        ]
        worksheet.append_row(row)
        print(f"Task '{title}' added with ID {task_id}.")
        return task_id
    except Exception as e:
        print(f"Error adding task '{title}': {e}")
        raise # Re-raise to allow calling function to handle

def read_tasks(worksheet, assignee_id: str = None, due_date_range: str = None, status: str = STATUS_PENDING):
    """Reads tasks, optionally filtering by assignee, due date range, and status.
    due_date_range can be 'today', 'this_week', or a specific 'YYYY-MM-DD'.
    Returns a list of dictionaries, where each dictionary represents a task.
    """
    # NOTE: This function fetches all records from the worksheet and then filters them in Python.
    # This can lead to performance issues with a large number of tasks.
    # Consider migrating to a more scalable database backend or implementing
    # more efficient filtering within the Google Sheets API if future versions of gspread support it.
    try:
        all_tasks_with_headers = worksheet.get_all_records()
        if not all_tasks_with_headers:
            return []

        tasks = []
        for task_record in all_tasks_with_headers:
            # Ensure all expected columns are present, defaulting if necessary
            task = {
                COL_TASK_ID: task_record.get(COL_TASK_ID),
                COL_TITLE: task_record.get(COL_TITLE),
                COL_STATUS: task_record.get(COL_STATUS),
                COL_ASSIGNEE_ID: task_record.get(COL_ASSIGNEE_ID, ""),
                COL_DUE_DATE: task_record.get(COL_DUE_DATE, ""),
                COL_CREATED_AT: task_record.get(COL_CREATED_AT)
            }
            tasks.append(task)

        # Filter by status
        if status:
            tasks = [task for task in tasks if task[COL_STATUS] == status]

        # Filter by assignee_id
        if assignee_id:
            tasks = [task for task in tasks if task[COL_ASSIGNEE_ID] == assignee_id]

        # Filter by due_date_range
        if due_date_range:
            today = datetime.now().date()
            filtered_by_date = []
            for task in tasks:
                if not task[COL_DUE_DATE]:
                    continue
                try:
                    # Due dates in sheet are 'YYYY-MM-DD HH:MM' or 'YYYY-MM-DD'
                    task_due_date_str = task[COL_DUE_DATE].split(" ")[0]
                    task_due_date = datetime.strptime(task_due_date_str, "%Y-%m-%d").date()

                    if due_date_range == "today":
                        if task_due_date == today:
                            filtered_by_date.append(task)
                    elif due_date_range == "this_week":
                        # This week starts on Monday and ends on Sunday
                        start_of_week = today - timedelta(days=today.weekday())
                        end_of_week = start_of_week + timedelta(days=6)
                        if start_of_week <= task_due_date <= end_of_week:
                            filtered_by_date.append(task)
                    elif due_date_range == "next_seven_days":
                        end_date = today + timedelta(days=7)
                        if today <= task_due_date < end_date: # Tasks due from today up to (but not including) 7 days from now
                             filtered_by_date.append(task)
                    # Add more conditions here if needed, e.g., specific date 'YYYY-MM-DD'
                    elif task_due_date_str == due_date_range : # Exact date match
                         filtered_by_date.append(task)
                except ValueError:
                    # Handle tasks with improperly formatted due dates if necessary
                    print(f"Warning: Task ID {task.get(COL_TASK_ID)} has invalid due date format: {task[COL_DUE_DATE]}")
                    continue
            tasks = filtered_by_date

        return tasks
    except Exception as e:
        print(f"Error reading tasks: {e}")
        raise

def update_task(worksheet, task_id: int, new_title: str = None, new_assignee_id: str = None, new_due_date: str = None):
    """Updates an existing task.
    Task_id is used to find the task.
    None for a parameter means no change for that field.
    Returns True if update was successful, False otherwise.
    """
    try:
        # Retrieve all task IDs from the first column and map them to their row indices
        task_ids = worksheet.col_values(1)  # Assuming task IDs are in the first column
        task_id_to_row = {int(task_id): idx + 1 for idx, task_id in enumerate(task_ids) if task_id.isdigit()}

        # Find the row index for the given task_id
        row_index = task_id_to_row.get(task_id)
        if not row_index:
            print(f"Task ID {task_id} not found for update.")
            return False
        current_row_values = worksheet.row_values(row_index)

        # Create a mapping from header to index for safety, or assume fixed column order
        headers = worksheet.row_values(1)
        header_map = {header: i for i, header in enumerate(headers)}

        # Prepare the updated row
        updated_row = list(current_row_values) # Make a mutable copy

        if new_title is not None:
            updated_row[header_map[COL_TITLE]] = new_title
        if new_assignee_id is not None: # Allow clearing assignee
            updated_row[header_map[COL_ASSIGNEE_ID]] = new_assignee_id
        if new_due_date is not None: # Allow clearing due date
            updated_row[header_map[COL_DUE_DATE]] = new_due_date

        # Update the entire row
        # Note: gspread cell objects are 1-indexed for rows and columns.
        # worksheet.update() can take a range and a list of lists.
        # For a single row, it's worksheet.update(f'A{row_index}:{chr(ord("A")+len(headers)-1)}{row_index}', [updated_row])
        # Or, more simply if we update cell by cell (less efficient for many changes):
        # worksheet.update_cell(row_index, header_map[COL_TITLE] + 1, updated_row[header_map[COL_TITLE]])

        # Using update with a range for the row for atomicity if possible with current gspread features
        # Constructing the range string like "A2:F2"
        start_cell_label = gspread.utils.rowcol_to_a1(row_index, 1)
        end_cell_label = gspread.utils.rowcol_to_a1(row_index, len(headers))
        worksheet.update(f'{start_cell_label}:{end_cell_label}', [updated_row])

        print(f"Task ID {task_id} updated.")
        return True
    except gspread.exceptions.CellNotFound:
        print(f"Task ID {task_id} not found for update (gspread exception).")
        return False
    except Exception as e:
        print(f"Error updating task ID {task_id}: {e}")
        raise # Or return False depending on desired error handling for the bot

def mark_task_complete(worksheet, task_id: int):
    """Marks a task as complete by setting its status to STATUS_COMPLETED.
    Returns True if successful, False otherwise.
    """
    try:
        cell = worksheet.find(str(task_id), in_column=1) # Find by task_id in the first column
        if not cell:
            print(f"Task ID {task_id} not found to mark as complete.")
            return False

        row_index = cell.row

        # Get header mapping to find status column index robustly
        headers = worksheet.row_values(1)
        try:
            status_col_index = headers.index(COL_STATUS) + 1 # gspread is 1-indexed
        except ValueError:
            print(f"Error: Column '{COL_STATUS}' not found in worksheet headers.")
            return False

        worksheet.update_cell(row_index, status_col_index, STATUS_COMPLETED)
        print(f"Task ID {task_id} marked as complete.")
        return True
    except gspread.exceptions.CellNotFound:
        print(f"Task ID {task_id} not found (gspread exception).")
        return False
    except Exception as e:
        print(f"Error marking task ID {task_id} as complete: {e}")
        raise # Or return False

if __name__ == '__main__':
    # This part is for testing the module directly
    # It requires .env to be set up correctly
    print("Attempting to connect to Google Sheets...")
    try:
        sheet = get_sheet()
        init_sheet(sheet) # Ensure headers are present
        print(f"Successfully connected to worksheet: '{WORKSHEET_NAME}'")

        # Example usage (for testing - will be removed or commented out later)
        # print("Next available task ID:", get_next_task_id(sheet))
        # add_task(sheet, title="Test Task from script", due_date="2024-12-31 18:00")
        # print("Tasks:", read_tasks(sheet))

    except ValueError as ve:
        print(f"Configuration error: {ve}")
    except Exception as e:
        print(f"An error occurred during Google Sheets operations: {e}")
        print("Please ensure your .env file is configured correctly with SPREADSHEET_ID and GOOGLE_CREDS_PATH,")
        print("and that the service account has access to the specified Google Sheet.")
