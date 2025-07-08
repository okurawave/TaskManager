import json
import os

import google.generativeai as genai
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
else:
    print("Warning: GEMINI_API_KEY not found in .env file. Gemini functionality will not work.")

# Tool definition for Function Calling as provided in the issue
TOOLS_DEFINITION = [
    {
        "function_declarations": [
            {
                "name": "add_task",
                "description": "Adds a new task to the list. If multiple tasks are requested, call this function for each.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "title": {"type": "STRING", "description": "The specific content of the task."},
                        "due_date": {"type": "STRING", "description": "The task's due date, interpreted from relative expressions into 'YYYY-MM-DD HH:MM' format."},
                        "assignee": {"type": "STRING", "description": "The name or mention of the person assigned to the task."}
                    },
                    "required": ["title"]
                }
            },
            {
                "name": "list_tasks",
                "description": "Displays a list of tasks matching the given criteria. If no criteria, shows all pending tasks.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "assignee": {"type": "STRING", "description": "Filter tasks by assignee name. 'Me' or 'my tasks' refers to the requester."},
                        "due_date_range": {"type": "STRING", "description": "Filter by due date, e.g., 'today', 'this week', 'overdue'."}
                    }
                }
            },
            {
                "name": "update_task",
                "description": "Updates an existing task's information.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "target_task_id": {"type": "NUMBER", "description": "The ID of the task to update."},
                        "target_task_title": {"type": "STRING", "description": "The current title of the task to update."},
                        "new_title": {"type": "STRING", "description": "The new title for the task."},
                        "new_due_date": {"type": "STRING", "description": "The new due date."},
                        "new_assignee": {"type": "STRING", "description": "The new assignee."}
                    }
                }
            },
            {
                "name": "complete_task",
                "description": "Marks a specified task as completed.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "target_task_id": {"type": "NUMBER", "description": "The ID of the task to complete."},
                        "target_task_title": {"type": "STRING", "description": "The title of the task to complete."}
                    }
                }
            }
        ]
    }
]

# Placeholder for the main function to interact with Gemini
async def get_intent_and_entities(user_message: str):
    """
    Sends the user message to Gemini with function calling tools
    and returns the parsed function call (intent) and arguments (entities).
    Returns (None, None) if no function call is made or an error occurs.
    """
    if not genai.is_configured():
        print("Error: Gemini API is not configured. Check GEMINI_API_KEY.")
        return None, None

    try:
        # Using a model that supports function calling, e.g., 'gemini-pro' or a specific version
        # The exact model name might need adjustment based on availability and features.
        # For Vertex AI, the endpoint and model name would be different.
        # This example assumes the `google-generativeai` library for Gemini API.
        model = genai.GenerativeModel(model_name="gemini-1.0-pro", tools=TOOLS_DEFINITION) # Or "gemini-1.5-flash" etc.

        # The prompt engineering might need refinement for best results.
        # We're directly sending the user message.
        # Adding context like "You are a helpful assistant managing tasks." could be beneficial.
        # For now, keeping it simple.
        chat = model.start_chat() # Use start_chat for conversational context if needed, or generate_content directly
        response = await chat.send_message_async(user_message) # Use async version

        # Check for function call in response
        if response.candidates and response.candidates[0].content.parts:
            for part in response.candidates[0].content.parts:
                if part.function_call:
                    function_name = part.function_call.name
                    args = {key: val for key, val in part.function_call.args.items()}
                    return function_name, args

        print("Gemini did not return a function call.")
        return None, None # No function call detected

    except Exception as e:
        print(f"Error interacting with Gemini API: {e}")
        # Depending on the error, you might want to retry or handle specific exceptions
        return None, None

if __name__ == '__main__':
    # Basic test (requires GEMINI_API_KEY to be set)
    async def main_test():
        if not GEMINI_API_KEY:
            print("GEMINI_API_KEY not set. Skipping test.")
            return

        test_message = "add a task 'Buy groceries' by tomorrow evening and assign it to John"
        print(f"Testing with message: \"{test_message}\"")
        function_name, args = await get_intent_and_entities(test_message)

        if function_name:
            print(f"Detected function: {function_name}")
            print(f"Arguments: {args}")
        else:
            print("Could not determine function call from Gemini.")

    # Running the async test (in a real bot, this would be part of the bot's event loop)
    # For simple script testing:
    import asyncio
    asyncio.run(main_test())
    print("Gemini_utils.py test run complete.")
