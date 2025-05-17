import json, os, datetime, copy
from datetime import date, datetime

from helper import logger, load_epic_metadata, date_range, get_initials, full_rt, format_timeline_for_chartjs, previous_day
from JiraWrapper import JiraWrapper

#-----------------------------------------------------------------------------------------------------------
# JiraClient Class
#-----------------------------------------------------------------------------------------------------------

class JiraClient(JiraWrapper):
    def __init__(self):
        super().__init__()


    def get_all_rt_epics(self):
        #returns json object for front-end order selection
        epic_list = []

        for raw_epic in self._rt_epic_data:
            try:
                key = raw_epic.get("key", "")
                fields = raw_epic.get("fields", {})
                if key.startswith("RT-"):
                    created_time = datetime.strptime(fields["created"][:19], "%Y-%m-%dT%H:%M:%S")
                    epic_list.append({
                        "rt_num": key,
                        "summary": fields.get("summary", ""),
                        "created": created_time
                    })
            except Exception as e:
                logger.warning(f"Failed to parse epic data: {e}")

        return epic_list


    def get_repair_data_from_epic(self, epic_key):
        #filters repair status and comments for display on the front end.
        #used to get an idea of how long specific repairs take, and how long the specific repairs took

        for issue in self.load_issues_from_file(epic_key, type="task"):
            fields = issue['fields']
            serial = fields['summary'] 
            rt_num = issue['key']
            board_model = None
            if fields.get('customfield_10230', None):
                board_model = fields['customfield_10230']['value'] 
            raw_summary = fields.get('customfield_10245', None)
            repair_summary = (raw_summary or 'N/A').replace("\n", "-") # remove newline chars, keep it a single line
            events = []

            # add the status changes to events
            changelog = issue.get('changelog', None)
            if changelog:
                for history in changelog['histories']:
                    for item in history['items']:
                        if item['field'] == "status":
                            timestamp = datetime.strptime(history['created'][:19], "%Y-%m-%dT%H:%M:%S")
                            events.append({
                                "type": "status_change",
                                "from": item['fromString'],
                                "to": item['toString'],
                                "time": timestamp,
                                "length": None,
                                "author": history.get('author', {}).get('displayName', '**')
                            })

            # sort events chronologically
            events.sort(key=lambda x: x["time"])

            # calc status time durations
            for i, event in enumerate(events):
                if event["type"] == "status_change":
                    next_status_time = None
                    for j in range(i + 1, len(events)):
                        if events[j]["type"] == "status_change":
                            next_status_time = events[j]["time"]
                            break
                    if next_status_time:
                        event["length"] = next_status_time - event["time"]
                    else:
                        event["length"] = -1  # Final status, no next one

            # add comments to events
            for comment in fields.get('comment', {}).get('comments', {}):
                events.append({
                    "type": "comment",
                    "author": comment.get('author', {}).get('displayName', '**'),
                    "time": datetime.strptime(comment['created'][:19], "%Y-%m-%dT%H:%M:%S"),
                    "body": comment.get('body', {})
                })

            # sort events chronologically
            events.sort(key=lambda x: x["time"])


            image_extensions = (".png", ".jpeg", ".jpg") #skip comments with images
            advanced_repair = False
            awaiting_functional_test = False
            scrap = False
            filtered_events = []

            #filter events / set flags
            for event in events:
                if event['type'] == "status_change":
                    if event['to'] == "Advanced Repair":
                        advanced_repair = True
                        filtered_events.append(event)
                    if event['to'] == "Awaiting Functional Test":
                        awaiting_functional_test = True
                        filtered_events.append(event)
                    if event['to'] == "Scrap":
                        scrap = True

                if event['type'] == "comment":
                    if not any(ext in event["body"] for ext in image_extensions):
                        event['body'] = event['body'].replace("\n", "-")
                        filtered_events.append(event)


            if advanced_repair and awaiting_functional_test and not scrap:
                yield { "serial": serial,
                        "rt_num": rt_num,
                        "board_model": board_model if board_model else 'N/A',
                        "repair_summary": repair_summary,
                        "events": filtered_events
                }


    def update_jira_with_board_data(self, board_data):
        # function for updating the board data scraped from the arc tester

        valid_board_models = [
            "NBS1906",
            "BHB42831",
            "NBP1901",
            "BHB42603",
            "BHB42631",
            "BHB42841",
            "BHB42601",
            "BHB56801",
            "BHB42621",
            "BHB42651",
            "BHB56903",
            "BHB68606",
            "BHB68603",
            "A3HB70601",
            "BHB68701"
        ]

        serial = board_data.get("serial")
        board_model = board_data.get("boardModel")

        if not serial:
            logger.warning("No serial number provided. Skipping.")
            return

        if not board_model:
            logger.warning(f"No board model found for serial {serial}. Skipping update.")
            return

        # JQL to find the issue by serial (assumed to be in the summary)
        jql = f'summary ~ "{serial}" AND issuetype = Task'

        try:
            issues = list(self.search_issues(jql, batch_size=1))
            if not issues:
                logger.warning(f"No JIRA issue found for serial: {serial}. Skipping update.")
                return

            issue = issues[0]
            fields_to_update = {}

            # Current field values
            current_board_model = getattr(issue.fields, "customfield_10230", None)
            current_frequency = getattr(issue.fields, "customfield_10229", None)
            current_hashrate = getattr(issue.fields, "customfield_10153", None)

            # Board Model - only update if different
            if not current_board_model or current_board_model.value != board_model:
                if board_model in valid_board_models:
                    fields_to_update["customfield_10230"] = {"value": board_model}
                else:
                    logger.warning(f"Invalid board model detected. {board_model} not in JIRA options.")

            # Optional: Frequency
            if "frequency" in board_data and (not current_frequency or current_frequency.strip() != board_data["frequency"]):
                fields_to_update["customfield_10229"] = board_data["frequency"]

            # Optional: Hashrate
            if "hashRate" in board_data and (not current_hashrate or current_hashrate.strip() != board_data["hashRate"]):
                fields_to_update["customfield_10153"] = board_data["hashRate"]

            if fields_to_update:
                issue.update(fields=fields_to_update)
                logger.info(f"Updated {serial} with: {fields_to_update}")
            else:
                logger.info(f"No updates needed for {serial}")

        except Exception as e:
            logger.error(f"Error updating board data for serial {serial}: {e}")




    def parse_status_history(self, issue_data):
        #parses status history changes, for populating a timeline

        events = []

        # Grab creation time as the first known time
        created_time = datetime.strptime(issue_data["fields"]["created"][:19], "%Y-%m-%dT%H:%M:%S")

        # Extract status change events from changelog
        if "changelog" in issue_data and "histories" in issue_data["changelog"]:
            for history in issue_data["changelog"]["histories"]:
                for item in history.get("items", []):
                    if item.get("field") == "status":
                        change_time = datetime.strptime(history["created"][:19], "%Y-%m-%dT%H:%M:%S")
                        events.append({
                            "from": item.get("fromString"),
                            "to": item.get("toString"),
                            "time": change_time
                        })

        # Sort the events by time just in case
        events.sort(key=lambda e: e["time"])

        # If there are no events, assume it's been in one status since creation
        if not events:
            return [{
                "status": issue_data["fields"]["status"]["name"],
                "start": created_time,
                "end": None
            }]

        # Build timeline from events
        timeline = []
        previous_status = events[0]["from"] or issue_data["fields"]["status"]["name"]
        previous_time = created_time

        for event in events:
            timeline.append({
                "status": previous_status,
                "start": previous_time,
                "end": event["time"]
            })
            previous_status = event["to"]
            previous_time = event["time"]

        # Add the final status with no end (means it's current)
        timeline.append({
            "status": previous_status,
            "start": previous_time,
            "end": None
        })

        return timeline


#-----------------------------------------------------------------------------------------------------------
# Max/Min Dates Functions
#-----------------------------------------------------------------------------------------------------------


    def get_max_min_hashboard_dates(self, hashboard):
        #get first and last day for a single hashboard

        first_date = None
        last_date = None

        status_timeline = self.parse_status_history(hashboard)

        for update in status_timeline:
            update_start = update['start']
            update_end = update.get('end')  # Use get() to avoid KeyError

            if first_date is None or update_start < first_date:
                first_date = update_start
            if update_end is not None and (last_date is None or update_end > last_date):
                last_date = update_end

        return first_date, last_date


    def get_max_min_epic_dates(self, epic_key):
        #get first and last day of all hashboards within a single epic

        first_date = None
        last_date = None

        epic_data = self.load_issues_from_file(epic_key, type="task")

        for hashboard in epic_data:
            update_start, update_end = self.get_max_min_hashboard_dates(hashboard)

            if first_date is None or update_start < first_date:
                first_date = update_start
            if update_end is not None and (last_date is None or update_end > last_date):
                last_date = update_end
        
        return first_date, last_date



#-----------------------------------------------------------------------------------------------------------
# Timeline Functions
#-----------------------------------------------------------------------------------------------------------


    def simplify_hashboard_timeline(self, hashboard, start_date, end_date):
        #takes the filtered status data for a hashboard. inserts it into a timeline of given length
        #the last status for each day is what ends up in each day-slot

        #create the timeline container
        timeline = {}
        for day in date_range(start_date, end_date):
            timeline[day] = None
        
        #insert the start days (status_timeline is chronological so each slot ends up with the last state of the day)
        status_timeline = self.parse_status_history(hashboard)
        for update in status_timeline:
            update_day = update['start']
            cropped_day = date(update_day.year, update_day.month, update_day.day) #cropped because we only take the day, not the time
            timeline[cropped_day] = update['status']
        
        #extend the states to fill blank spots where no status changes happened
        last_status = None
        for day in timeline:
            if last_status is None:
                last_status = timeline[day]
            if timeline[day] is None:
                timeline[day] = last_status
            last_status = timeline[day]

        return timeline


    def build_and_fill_epic_timeline(self, epic_key):
        #creates a timeline container with total counts for each status for each day
        start_date, end_date = self.get_max_min_epic_dates(epic_key)

        if start_date is None and end_date is None:
            logger.warning(f"No data for {epic_key}")
            return None

    # PART 1: create the empty timeline container

        status_list = ["Backlog", "Awaiting Advanced Repair", "Advanced Repair", "Passed Initial Diagnosis", 
                       "Awaiting Functional Test", "Done", "Scrap", "Hashboard Replacement Program", "Total Boards"]
        
        blank_day = {}
        for status in status_list:
            blank_day[status] = []

        timeline = {}
        for day in date_range(start_date, end_date):
            timeline[day] = copy.deepcopy(blank_day)

    # PART 2: insert hb statuses into timeline container

        epic_data = self.load_issues_from_file(epic_key, type="task")

        #'backlog' and 'advance repair' left overnight should be considered an error, force them into 'awating advanced repair'
        convert = {
            "Advanced Repair": "Awaiting Advanced Repair",
            "Backlog": "Awaiting Advanced Repair"
        }

        #insert each hashboard timeline into the epic timeline
        for hashboard in epic_data:
            serial = hashboard['fields']['summary']
            hb_timeline = self.simplify_hashboard_timeline(hashboard, start_date, end_date)
            for day in hb_timeline:
                hb_status = hb_timeline[day]
                if hb_status is not None:
                    if(hb_status in convert.keys()):
                        converted_status = convert[hb_status]
                        timeline[day][converted_status].append(serial)
                    else:
                        timeline[day][hb_status].append(serial)
                    timeline[day]['Total Boards'].append(serial)

    # PART 3: prune leading days
        #when hasboard replacement program is used, the hbr hashboard will mess up the timeline and greatly extend the beginning date
        
        pruned_timeline = {}
        START = False

        status_totals = {}
        for status in status_list:
            status_totals[status] = 0

        #set up a trigger that filters out all leading days with very low count (less than 5)
        for day in timeline:
            if len(timeline[day]['Total Boards']) > 4:
                START = True
            if START:
                if len(timeline[day]['Done']) == len(timeline[day]['Total Boards']): #stop when all boards are in 'done' state
                    break
                pruned_timeline[day] = {}
                for hb_status in timeline[day]:
                    pruned_timeline[day][hb_status] = timeline[day][hb_status].copy()
                    status_totals[hb_status] += len(timeline[day][hb_status])

    # PART 4: remove statuses that have 0 boards on every single day, a.k.a. remove unused statuses

        #find the statuses that have 0 counts in status_totals
        zero_count_status = []
        for status in status_totals:
            if status_totals[status] == 0:
                zero_count_status.append(status)

        #remove statuses that have 0 action
        filtered_timeline = {}
        for day in pruned_timeline:
            filtered_timeline[day] = {}
            for hb_status in pruned_timeline[day]:
                if hb_status not in zero_count_status:
                    filtered_timeline[day][hb_status] = pruned_timeline[day][hb_status].copy()

        #jsonify cant serialize datetime as a key, so convert to iso format (YYYY-MM-DD)
        timeline_str_keys = {day.isoformat(): data for day, data in filtered_timeline.items()}

        return timeline_str_keys


    def create_epic_timeline_data(self, epic):
    #used for sending packaged data to front end
        timeline = self.build_and_fill_epic_timeline(epic)
        epic_summary = self.get_epic_summary(epic)

        epic_data = {
            "rt": epic,
            "title": epic_summary,
            "timeline": timeline
        }
        
        return epic_data





            



