import json, os, datetime, copy
from datetime import date, datetime

from helper import logger, date_range, get_initials, full_rt, previous_day
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

        for epic_key in self.epics:
            epic = self.epics[epic_key]
            issue_count = len(epic.issues)
            epic_list.append({
                "rt_num": epic.key,
                "summary": epic.title,
                "created": epic.start_date,
                "issue_count": issue_count
            })

        return epic_list


    def get_repair_data_from_epic(self, epic_key):
        #filters repair status and comments for display on the front end.
        #used to get an idea of how long specific repairs take, and how long the specific repairs took

        issues = self.epics[epic_key].issues

        for issue in issues:
            if issue.issue_type != 'Task':
                continue

            events = []

            # add the status changes to events
            for status_change in issue.status_history:
                events.append({
                    "type": "status_change",
                    "from": status_change.from_status,
                    "to": status_change.to_status,
                    "time": status_change.timestamp,
                    "length": None,
                    "author": status_change.author
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
            for comment in issue.comments:
                events.append({
                    "type": "comment",
                    "author": comment.author,
                    "time": comment.timestamp,
                    "body": comment.body
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
                yield { "serial": issue.serial,
                        "rt_num": issue.key,
                        "board_model": issue.board_model if issue.board_model else 'N/A',
                        "repair_summary": issue.repair_summary.replace('\n', '-') if issue.repair_summary else 'N/A',
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




    def parse_status_history(self, issue):
        #I THINK THIS CAN BE DELETED

        #parses status history changes, for populating a timeline

        events = []

        # Extract status change events from changelog
        for status_change in issue.status_history:
            events.append({
                "from": status_change.from_status,
                "to": status_change.to_status,
                "time": status_change.timestamp
            })

        # Sort the events by time just in case
        events.sort(key=lambda e: e["time"])

        # If there are no events, assume it's been in one status since creation
        if not events:
            print("FFFFFUUUUUUUCCCCCCKKKKKKK!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!1")
            return [{
                "status": "Backlog",
                "start": issue.created,
                "end": None
            }]

        # Build timeline from events
        timeline = []
        previous_status = events[0]["from"]
        previous_time = issue.created

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

        issues = self.epics[epic_key].issues

        for issue in issues:
            if issue.issue_type != "Task":
                continue

            update_start, update_end = self.get_max_min_hashboard_dates(issue)

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


    def create_epic_timeline_data(self, epic):
    #used for sending packaged data to front end

        if self.epics[epic].issues is None: #this needs work, doesnt work right
            for _ in self.dump_issues_to_files(epic_key=epic):
                pass

        timeline = self.build_and_fill_epic_timeline(epic)
        epic_summary = self.epics[epic].title

        epic_data = {
            "rt": epic,
            "title": epic_summary,
            "timeline": timeline
        }

        return epic_data


    def build_and_fill_epic_timeline(self, epic_key):
            #creates a timeline container with total counts for each status for each day
            start_date, end_date = self.get_max_min_epic_dates(epic_key)

            if start_date is None and end_date is None:
                logger.warning(f"No data for {epic_key}")
                return None

        # PART 1: create the empty timeline container

            timeline = {}
            for day in date_range(start_date, end_date):
                timeline[day] = {'Total Boards': []}

        # PART 2: insert hb statuses into timeline container

            issues = self.epics[epic_key].issues
            status_list = ['Total Boards']

            # Advanced Repair overnight is an error, shift it to Awating advanced repair
            convert_status = {
                "Advanced Repair": "Awaiting Advanced Repair",
                "Backlog": "Awaiting Advanced Repair"
            }

            #insert each hashboard timeline into the epic timeline
            for issue in issues:
                if issue.issue_type != "Task":
                    continue

                hb_timeline = self.simplify_hashboard_timeline(issue, start_date, end_date)

                for day in hb_timeline:
                    hb_status = hb_timeline[day]
                    if hb_status is not None:
                        if hb_status in convert_status:
                            hb_status = convert_status[hb_status] 
                        if hb_status not in status_list:
                            status_list.append(hb_status)
                        if hb_status not in timeline[day]:
                            timeline[day][hb_status] = []
                        timeline[day][hb_status].append(issue.serial)
                        timeline[day]['Total Boards'].append(issue.serial)

        # PART 3: prune leading days
            #when hasboard replacement program is used, the hbr hashboard will mess up the timeline and greatly extend the beginning date
            
            pruned_timeline = {}
            START = False

            #set up a trigger that filters out all leading days with very low count (less than 5)
            for day in timeline:
                if len(timeline[day]['Total Boards']) > 4:
                    START = True
                if START:
                    if 'Done' in timeline[day]:
                        if len(timeline[day]['Done']) == len(timeline[day]['Total Boards']): #stop when all boards are in 'done' state
                            break
                    pruned_timeline[day] = {}
                    for status in status_list:
                        pruned_timeline[day][status] = None
                        if status in timeline[day]:
                            if pruned_timeline[day][status] is None:
                                pruned_timeline[day][status] = []
                            pruned_timeline[day][status] = timeline[day][status].copy()

            #jsonify cant serialize datetime as a key, so convert to iso format (YYYY-MM-DD)
            timeline_str_keys = {day.isoformat(): data for day, data in pruned_timeline.items()}

            return timeline_str_keys



