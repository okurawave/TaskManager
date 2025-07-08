import asyncio  # Required for gemini_utils if it uses async features directly in its functions
import os
from datetime import datetime, timedelta

import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv

import gemini_utils
import google_sheets  # Assuming this will have a class or direct functions

# Load environment variables from .env file
load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
REMINDER_CHANNEL_ID = os.getenv("REMINDER_CHANNEL_ID")
# SPREADSHEET_ID and GOOGLE_CREDS_PATH are used by google_sheets.py internally

# --- Bot Setup ---
# Define intents
# Needs message content to read commands, and members to resolve user mentions if desired for assignees
intents = discord.Intents.default()
intents.message_content = True
intents.members = True  # If you need to map mentions to user IDs accurately or get member objects

# Bot prefix (can be empty if only mentions are used, but good for traditional commands too)
# For this project, primary interaction is via mentions.
bot = commands.Bot(command_prefix="!", intents=intents)  # Prefix can be changed or removed

# --- Global Variables / Bot State (if necessary) ---
# Example: worksheet instance, if you want to initialize it once
gs_worksheet = None

# --- Event Handlers ---
@bot.event
async def on_ready():
    """Called when the bot is successfully connected and ready."""
    print(f'{bot.user.name} has connected to Discord!')
    print(f'Bot ID: {bot.user.id}')
    print(f'Successfully loaded {len(bot.commands)} commands.')  # If using traditional commands

    global gs_worksheet
    try:
        gs_worksheet = google_sheets.get_sheet()
        google_sheets.init_sheet(gs_worksheet)  # Ensure headers exist
        print("Successfully connected to Google Sheets and initialized worksheet.")
    except Exception as e:
        print(f"Error connecting to Google Sheets on startup: {e}")
        gs_worksheet = None  # Ensure it's None if connection failed

    # Start any background tasks, like reminders, here
    if REMINDER_CHANNEL_ID and REMINDER_CHANNEL_ID.isdigit():
        print(f"Reminder channel ID: {REMINDER_CHANNEL_ID}. Starting reminder loop.")
        reminder_loop.start()
    else:
        print("REMINDER_CHANNEL_ID not set or invalid. Reminder loop not started.")


@tasks.loop(hours=24)  # Adjust timing as needed, e.g., time=datetime.time(hour=8) for 8 AM daily
async def reminder_loop():
    """Periodically checks for upcoming tasks and sends reminders."""
    global gs_worksheet
    if not gs_worksheet:
        print("Reminder loop: Google Sheet not available.")
        return
    if not REMINDER_CHANNEL_ID or not REMINDER_CHANNEL_ID.isdigit():
        print("Reminder loop: Invalid or no REMINDER_CHANNEL_ID set.")
        return

    channel = bot.get_channel(int(REMINDER_CHANNEL_ID))
    if not channel:
        print(f"Reminder loop: Could not find channel with ID {REMINDER_CHANNEL_ID}.")
        return

    print("Reminder loop: Checking for tasks due in the next 7 days...")
    try:
        tasks = google_sheets.read_tasks(gs_worksheet,
                                         due_date_range="next_seven_days",
                                         status=google_sheets.STATUS_PENDING)
        if not tasks:
            # await channel.send("No tasks due in the next 7 days. Relax! 🏖️") # Optional: message if no tasks
            print("Reminder loop: No upcoming tasks found.")
            return

        # Group tasks
        today = datetime.now().date()
        tomorrow = today + timedelta(days=1)

        due_today_tasks = []
        due_tomorrow_tasks = []
        upcoming_tasks = []  # Within 2-7 days

        for task in tasks:
            if not task.get(google_sheets.COL_DUE_DATE):
                continue
            try:
                task_due_date = datetime.strptime(task[google_sheets.COL_DUE_DATE].split(" ")[0], "%Y-%m-%d").date()
                if task_due_date == today:
                    due_today_tasks.append(task)
                elif task_due_date == tomorrow:
                    due_tomorrow_tasks.append(task)
                elif today < task_due_date < (today + timedelta(days=7)):  # Exclude today and tomorrow, up to 6 days ahead
                    upcoming_tasks.append(task)
            except ValueError:
                print(f"Reminder loop: Invalid date format for task ID {task.get(google_sheets.COL_TASK_ID)}")
                continue

        # Build message
        reminder_message_parts = ["**📅 Weekly Task Reminders!**\n"]

        async def format_task_list(task_list, title_prefix=""):
            lines = []
            for task in task_list:
                task_id = task.get(google_sheets.COL_TASK_ID, 'N/A')
                task_title = task.get(google_sheets.COL_TITLE, 'No Title')
                due_date_str = task.get(google_sheets.COL_DUE_DATE, '')
                assignee_id = task.get(google_sheets.COL_ASSIGNEE_ID, '')

                line = f"- **ID {task_id}:** {task_title}"
                if due_date_str:  # Show specific due date/time
                    line += f" (Due: {due_date_str})"
                if assignee_id:
                    try:
                        user = await bot.fetch_user(int(assignee_id)) if assignee_id.isdigit() else None
                        assignee_display = user.mention if user else assignee_id  # Mention if possible
                        line += f" (Assigned: {assignee_display})"
                    except (discord.NotFound, ValueError):
                        line += f" (Assigned: {assignee_id})"
                lines.append(line)
            return lines

        if due_today_tasks:
            reminder_message_parts.append("\n**🔥 Due Today:**")
            reminder_message_parts.extend(await format_task_list(due_today_tasks))

        if due_tomorrow_tasks:
            reminder_message_parts.append("\n**⏰ Due Tomorrow:**")
            reminder_message_parts.extend(await format_task_list(due_tomorrow_tasks))

        if upcoming_tasks:
            reminder_message_parts.append("\n**🗓️ Upcoming (Next 7 Days):**")
            reminder_message_parts.extend(await format_task_list(upcoming_tasks))

        if len(reminder_message_parts) > 1:  # More than just the header
            full_message = "\n".join(reminder_message_parts)
            # Handle Discord message length limits
            if len(full_message) > 2000:
                # Simple truncation for now. A better way would be multiple messages.
                await channel.send(full_message[:1990] + "\n...(truncated)")
            else:
                await channel.send(full_message)
            print("Reminder loop: Sent reminder message.")
        else:
            print("Reminder loop: No tasks matched criteria for reminder message after grouping.")    


    except Exception as e:
        print(f"Error in reminder_loop: {e}")
        await channel.send(f"⚠️ Error encountered while generating task reminders: {e}")

@reminder_loop.before_loop
async def before_reminder_loop():
    """Ensures the bot is ready before the reminder loop starts."""
    await bot.wait_until_ready()
    print("Reminder loop: Bot is ready, loop will start.")


@bot.event
async def on_message(message: discord.Message):
    """Called when a message is sent to any channel the bot can see."""
    if message.author == bot.user:
        return  # Ignore messages from the bot itself

    # Check if the bot is mentioned
    if bot.user.mentioned_in(message):
        print(f"Bot mentioned by {message.author} in {message.channel}: {message.content}")

        # Extract the content of the message, removing the bot mention
        # This can be tricky if the mention is not always at the beginning.
        # A simple approach for now:
        clean_content = message.content
        for mention in message.mentions:
            if mention.id == bot.user.id:
                clean_content = clean_content.replace(f'<@!{bot.user.id}>', '').replace(f'<@{bot.user.id}>', '').strip()
                break

        if not clean_content:
            await message.channel.send("You mentioned me, but didn't provide a command. How can I help?")
            return

        if not gs_worksheet:
            await message.channel.send("Sorry, I'm having trouble connecting to the task database. Please try again later.")
            return

        # Send to Gemini for intent parsing
        try:
            # Ensure gemini_utils.get_intent_and_entities is awaitable if it does I/O
            function_name, args = await gemini_utils.get_intent_and_entities(clean_content)

            if function_name:
                # Dispatch to appropriate handlers based on function_name
                if function_name == "add_task":
                    await handle_add_task(message, args)
                elif function_name == "list_tasks":
                    await handle_list_tasks(message, args)
                elif function_name == "update_task":
                    await handle_update_task(message, args)
                elif function_name == "complete_task":
                    await handle_complete_task(message, args)
                else:
                    await message.channel.send(f"I recognized the action `{function_name}` but don't know how to handle it yet.")
            else:
                await message.channel.send("I'm not sure how to help with that. Could you try rephrasing?")

        except Exception as e:
            print(f"Error processing message with Gemini or dispatching: {e}")
            await message.channel.send("Sorry, I encountered an error trying to understand that.")
            # Potentially log the error to a file or monitoring system

    # Allow processing traditional commands as well, if any are defined
    # await bot.process_commands(message)

# --- Date Helper ---

def parse_relative_due_date(due_date_str: str) -> str:
    """
    Parses a due_date string which might be relative (e.g., "today", "tomorrow")
    or already in 'YYYY-MM-DD HH:MM' or 'YYYY-MM-DD' format.
    Returns 'YYYY-MM-DD 23:59' for relative dates, or appends default time if only date is given.
    """
    if not due_date_str:
        return None

    now = datetime.now()
    due_date_str_lower = due_date_str.lower()

    if "today" in due_date_str_lower:
        target_date = now
    elif "tomorrow" in due_date_str_lower:
        target_date = now + timedelta(days=1)
    # Add more relative terms like "next monday" etc. if Gemini doesn't fully resolve them
    # For now, assume Gemini provides 'YYYY-MM-DD HH:MM' or these simple terms
    else:
        try:
            # Try parsing as YYYY-MM-DD HH:MM
            dt_obj = datetime.strptime(due_date_str, "%Y-%m-%d %H:%M")
            return dt_obj.strftime("%Y-%m-%d %H:%M")
        except ValueError:
            try:
                # Try parsing as YYYY-MM-DD
                dt_obj = datetime.strptime(due_date_str, "%Y-%m-%d")
                return dt_obj.strftime("%Y-%m-%d 23:59")  # Default end of day
            except ValueError:
                # If it's not a recognized relative term or format, return as is or handle error
                # For now, returning None, assuming Gemini should mostly provide valid dates
                # Or, if Gemini provides "evening", "morning", it should also provide the date.
                # This function primarily handles "today", "tomorrow" and format standardization.
                print(f"Could not parse due date string: {due_date_str}")
                return None  # Or raise an error / return original to show user

    # For "today", "tomorrow", default to end of day if no specific time is given by Gemini
    # Gemini's spec says "YYYY-MM-DD HH:MM", so this might be redundant if Gemini is perfect.
    time_part = "23:59"  # Default time
    if len(due_date_str_lower.split()) > 1 and ":" in due_date_str_lower:  # e.g. "tomorrow 10:00"
        # This part is tricky if Gemini gives "tomorrow evening" vs "tomorrow 17:00"
        # Assuming Gemini's output `due_date` string will be the primary source if specific.
        # If Gemini's output is just "tomorrow", we use default end of day.
        # If Gemini's output is "tomorrow 17:00", `parse_relative_due_date` might not be called for "tomorrow"
        # This logic path is mostly for "today", "tomorrow" if Gemini passes them as such.
        pass  # Keep default time for now, rely on Gemini for specifics.

    return target_date.strftime(f"%Y-%m-%d {time_part}")


# --- Command Handlers ---
async def handle_add_task(message: discord.Message, args: dict):
    """Handles the 'add_task' intent from Gemini."""
    global gs_worksheet
    if not gs_worksheet:
        await message.channel.send("Database connection is not available.")
        return

    title = args.get("title")
    due_date_str = args.get("due_date")  # This is what Gemini provides
    assignee_str = args.get("assignee")  # This could be a name or a Discord mention

    if not title:
        await message.channel.send("Please provide a title for the task.")
        return

    # Parse due_date
    parsed_due_date = None
    if due_date_str:
        # Gemini is expected to convert "tomorrow evening" to "YYYY-MM-DD 17:00" (example)
        # This helper is more a fallback or for standardizing if Gemini sends "YYYY-MM-DD"
        parsed_due_date = parse_relative_due_date(due_date_str)
        if not parsed_due_date:
            # If parse_relative_due_date couldn't understand it, and it's not None
            # it implies Gemini sent something unexpected or the format from Gemini was not YYYY-MM-DD HH:MM
            # For now, we'll try to use what Gemini sent if our parser fails,
            # assuming Gemini adheres to its output spec.
            # A better approach might be to validate Gemini's output format strictly here.
            if ':' not in due_date_str and len(due_date_str) == 10:  # Looks like YYYY-MM-DD
                 parsed_due_date = f"{due_date_str} 23:59"
            else:  # Assume it's in the correct "YYYY-MM-DD HH:MM" or some other format we pass directly
                 parsed_due_date = due_date_str


    # Resolve assignee
    assignee_id = None
    if assignee_str:
        # Check if assignee_str is a Discord mention <@USER_ID> or <@!USER_ID>
        if message.mentions:  # Check actual mentions in the message object
            for user_mention in message.mentions:
                # Check if the string Gemini picked as 'assignee' corresponds to a mentioned user
                # This is a simple check; a more robust way would be to compare the assignee_str
                # with user_mention.name, user_mention.display_name, or the raw mention string.
                if assignee_str == user_mention.mention or assignee_str == user_mention.name or assignee_str == f"<@{user_mention.id}>" or assignee_str == f"<@!{user_mention.id}>":
                    assignee_id = str(user_mention.id)
                    break
        if not assignee_id:
            # If not a direct mention match from message.mentions,
            # it could be a name. Store the name as is, or try to find user by name (more complex).
            # For now, store the string Gemini provided if no direct mention resolved.
            # This means assignee_id in Sheets could be a Discord ID or a name string.
            assignee_id = assignee_str
            # A future improvement: If it's a name, try to look up the user in the server.
            # member = discord.utils.find(lambda m: m.name == assignee_str or m.display_name == assignee_str, message.guild.members)
            # if member: assignee_id = str(member.id)

    try:
        task_id = google_sheets.add_task(gs_worksheet, title, assignee_id, parsed_due_date)
        response_due_date = f" (Due: {parsed_due_date})" if parsed_due_date else ""
        response_assignee = f" for {assignee_str}" if assignee_str else ""  # Use original assignee string for response
        await message.channel.send(f"✅ Task added: '{title}' (ID: {task_id}){response_assignee}{response_due_date}")
    except Exception as e:
        print(f"Error in handle_add_task: {e}")
        await message.channel.send(f"Sorry, I couldn't add the task. Error: {e}")

async def handle_list_tasks(message: discord.Message, args: dict):
    """Handles the 'list_tasks' intent from Gemini."""
    global gs_worksheet
    if not gs_worksheet:
        await message.channel.send("Database connection is not available.")
        return

    assignee_filter_str = args.get("assignee") # From Gemini: "me", name, or mention
    due_date_range_filter = args.get("due_date_range") # From Gemini: "today", "this week", etc.

    target_assignee_id = None
    response_assignee_name = "everyone"

    if assignee_filter_str:
        if assignee_filter_str.lower() in ["me", "my", "my tasks"]:
            target_assignee_id = str(message.author.id)
            response_assignee_name = message.author.display_name
        else:
            # Check for actual mentions first
            mentioned_user = None
            if message.mentions:
                for user_mention in message.mentions:
                    # Check if the assignee_filter_str matches a mention in the message
                    if assignee_filter_str == user_mention.mention or \
                       assignee_filter_str == user_mention.name or \
                       assignee_filter_str == f"<@{user_mention.id}>" or \
                       assignee_filter_str == f"<@!{user_mention.id}>":
                        mentioned_user = user_mention
                        break

            if mentioned_user:
                target_assignee_id = str(mentioned_user.id)
                response_assignee_name = mentioned_user.display_name
            else:
                # If not a direct mention, treat as a name string for filtering.
                # google_sheets.read_tasks will need to handle filtering by a name string
                # or we decide here that only ID-based filtering is done for assignees.
                # For now, let's assume if it's not "me" or a resolvable mention,
                # we pass the string as is, and google_sheets will try to match it.
                target_assignee_id = assignee_filter_str # Pass the name/string
                response_assignee_name = assignee_filter_str


    try:
        # Default to 'pending' status if not otherwise specified by Gemini (which it isn't in current tool)
        tasks = google_sheets.read_tasks(gs_worksheet,
                                         assignee_id=target_assignee_id,
                                         due_date_range=due_date_range_filter,
                                         status=google_sheets.STATUS_PENDING)

        if not tasks:
            filter_desc = ""
            if response_assignee_name != "everyone":
                filter_desc += f" for {response_assignee_name}"
            if due_date_range_filter:
                filter_desc += f" due {due_date_range_filter}"

            await message.channel.send(f"No pending tasks found{filter_desc}.")
            return

        response_lines = [f"**Pending Tasks**"]
        if response_assignee_name != "everyone":
            response_lines[0] += f" for **{response_assignee_name}**"
        if due_date_range_filter:
            response_lines[0] += f" (Due: **{due_date_range_filter}**)"

        response_lines.append("---")

        for task in tasks:
            task_id = task.get(google_sheets.COL_TASK_ID, 'N/A')
            title = task.get(google_sheets.COL_TITLE, 'No Title')
            due = task.get(google_sheets.COL_DUE_DATE, '')
            assignee = task.get(google_sheets.COL_ASSIGNEE_ID, '') # This is an ID or name

            task_line = f"**ID {task_id}:** {title}"
            if due:
                task_line += f" (Due: {due})"
            if assignee: # Try to display a more friendly name if it's an ID
                try:
                    user = await bot.fetch_user(int(assignee)) if assignee.isdigit() else None
                    assignee_display = user.name if user else assignee
                    task_line += f" (Assigned: {assignee_display})"
                except (discord.NotFound, ValueError): # ValueError if assignee is not a digit string
                    task_line += f" (Assigned: {assignee})" # Show the raw assignee if not found or not ID
            response_lines.append(task_line)

        # Discord messages have a length limit (2000 chars)
        # For simplicity, sending one message. Paginate if response is too long.
        full_response = "\n".join(response_lines)
        if len(full_response) > 2000:
            await message.channel.send("\n".join(response_lines[:30]) + "\n...(list too long, truncated)")
        else:
            await message.channel.send(full_response)

    except Exception as e:
        print(f"Error in handle_list_tasks: {e}")
        await message.channel.send(f"Sorry, I couldn't list the tasks. Error: {e}")

async def handle_update_task(message: discord.Message, args: dict):
    """Handles the 'update_task' intent from Gemini."""
    global gs_worksheet
    if not gs_worksheet:
        await message.channel.send("Database connection is not available.")
        return

    task_id_str = args.get("target_task_id")
    # target_title_str = args.get("target_task_title") # Not directly used if ID is primary

    if task_id_str is None: # Check for None explicitly, as 0 is a valid ID (though we start at 1)
        # TODO: If only target_task_title is provided by Gemini,
        # we would need to implement a lookup for task_id by title here.
        # This could involve listing tasks with that title and asking the user to specify an ID.
        # For now, require task_id.
        await message.channel.send("Please specify the Task ID to update. For example: `@Bot update task ID 15 due to next Monday`")
        return

    try:
        task_id = int(task_id_str)
    except ValueError:
        await message.channel.send(f"Invalid Task ID format: '{task_id_str}'. Please use a number.")
        return

    new_title = args.get("new_title")
    new_due_date_str = args.get("new_due_date")
    new_assignee_str = args.get("new_assignee")

    if not any([new_title, new_due_date_str, new_assignee_str]):
        await message.channel.send("Please specify what you want to update (e.g., new title, due date, or assignee).")
        return

    parsed_new_due_date = None
    if new_due_date_str:
        parsed_new_due_date = parse_relative_due_date(new_due_date_str)
        if not parsed_new_due_date:
            # Similar to add_task, attempt to use Gemini's direct output if our parser fails
            if ':' not in new_due_date_str and len(new_due_date_str) == 10: # YYYY-MM-DD
                 parsed_new_due_date = f"{new_due_date_str} 23:59"
            else: # Assume it's in the correct "YYYY-MM-DD HH:MM" or pass as is
                 parsed_new_due_date = new_due_date_str


    new_assignee_id = None # Important: Explicitly None if not changing
    if "new_assignee" in args: # Check if key exists, to allow unsetting assignee
        if new_assignee_str: # If assignee is provided
            if message.mentions:
                for user_mention in message.mentions:
                    if new_assignee_str == user_mention.mention or new_assignee_str == user_mention.name:
                        new_assignee_id = str(user_mention.id)
                        break
            if not new_assignee_id: # Not a mention, or no mentions in message
                new_assignee_id = new_assignee_str # Store as name/string
        else: # new_assignee_str is empty string "" from Gemini (or None, handled by .get default)
            new_assignee_id = "" # Explicitly set to empty string to clear assignee in Sheets

    try:
        # google_sheets.update_task expects None for fields not being updated.
        # So, only pass values if they were provided by Gemini.
        update_kwargs = {}
        if "new_title" in args and new_title is not None: # Check key presence and value
            update_kwargs["new_title"] = new_title
        if "new_due_date" in args and new_due_date_str is not None: # Check key for due date
            update_kwargs["new_due_date"] = parsed_new_due_date # This can be None if parsing failed and str was bad
        if "new_assignee" in args: # Check key presence to allow setting to empty string
            update_kwargs["new_assignee_id"] = new_assignee_id


        if not update_kwargs: # Should be caught earlier, but as a safeguard
            await message.channel.send("No valid fields to update were provided.")
            return

        success = google_sheets.update_task(gs_worksheet, task_id, **update_kwargs)

        if success:
            await message.channel.send(f"🔄 Task (ID: {task_id}) has been updated.")
        else:
            await message.channel.send(f"Could not update task (ID: {task_id}). It might not exist or an error occurred.")
    except Exception as e:
        print(f"Error in handle_update_task: {e}")
        await message.channel.send(f"Sorry, I couldn't update the task. Error: {e}")

async def handle_complete_task(message: discord.Message, args: dict):
    """Handles the 'complete_task' intent from Gemini."""
    global gs_worksheet
    if not gs_worksheet:
        await message.channel.send("Database connection is not available.")
        return

    task_id_str = args.get("target_task_id")
    target_title_str = args.get("target_task_title") # Gemini might provide this

    task_id_to_complete = None

    if task_id_str is not None:
        try:
            task_id_to_complete = int(task_id_str)
        except ValueError:
            await message.channel.send(f"Invalid Task ID format: '{task_id_str}'. Please use a number or specify by title.")
            return # Don't proceed if ID format is bad

    if task_id_to_complete is None and target_title_str:
        # If ID wasn't provided or was invalid, and title is available, try to find task by title.
        # This requires reading tasks and matching titles.
        # For simplicity, this example will show a basic lookup.
        # A more robust version would handle multiple matches by asking the user.
        try:
            # Read pending tasks with the given title
            # Note: This is a simple exact match. You might want more flexible matching.
            # Also, this reads ALL tasks with that title. If multiple, it's an issue.
            tasks_found = google_sheets.read_tasks(gs_worksheet, status=google_sheets.STATUS_PENDING)

            matched_tasks = []
            if tasks_found: # Ensure tasks_found is not None
                for task in tasks_found:
                    if task.get(google_sheets.COL_TITLE, '').lower() == target_title_str.lower():
                        matched_tasks.append(task)

            if len(matched_tasks) == 1:
                task_id_to_complete = int(matched_tasks[0][google_sheets.COL_TASK_ID])
                await message.channel.send(f"Found task '{target_title_str}' with ID {task_id_to_complete}. Marking as complete.")
            elif len(matched_tasks) > 1:
                ids_found = ", ".join([str(t[google_sheets.COL_TASK_ID]) for t in matched_tasks])
                await message.channel.send(f"Multiple tasks found with title '{target_title_str}'. Please specify by ID: {ids_found}")
                return
            else:
                await message.channel.send(f"No pending task found with title '{target_title_str}'. Please check the title or use an ID.")
                return
        except Exception as e:
            print(f"Error looking up task by title '{target_title_str}': {e}")
            await message.channel.send(f"Sorry, I had trouble finding task by title: '{target_title_str}'.")
            return

    if task_id_to_complete is None: # Still no ID after title lookup or if no title provided
        await message.channel.send("Please specify the Task ID or Title to complete. For example: `@Bot complete task ID 15` or `@Bot mark 'Prepare report' as done`")
        return

    # At this point, task_id_to_complete should be an int
    try:
        success = google_sheets.mark_task_complete(gs_worksheet, task_id_to_complete)
        if success:
            await message.channel.send(f"🎉 Great job! Task (ID: {task_id_to_complete}) has been marked as complete.")
        else:
            await message.channel.send(f"Could not mark task (ID: {task_id_to_complete}) as complete. It might not exist or was already completed.")
    except Exception as e:
        print(f"Error in handle_complete_task: {e}")
        await message.channel.send(f"Sorry, I couldn't complete the task. Error: {e}")


# --- Main Bot Execution ---
if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("Error: DISCORD_TOKEN not found in .env file. Bot cannot start.")
    else:
        try:
            bot.run(DISCORD_TOKEN)
        except discord.errors.LoginFailure:
            print("Error: Invalid Discord Bot Token. Please check your .env file.")
        except Exception as e:
            print(f"An unexpected error occurred while trying to run the bot: {e}")
