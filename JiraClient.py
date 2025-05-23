from helper import logger, date_range
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


#-----------------------------------------------------------------------------------------------------------
# Timeline Functions
#-----------------------------------------------------------------------------------------------------------

    def get_max_min_epic_dates(self, epic_key):
        issues = [
            issue for issue in self.epics[epic_key].issues
            if issue.issue_type == "Task"
        ]

        if not issues:
            return None, None

        first_date = min(issue.created for issue in issues)

        last_dates = [
            issue.status_history[-1].timestamp
            for issue in issues
            if issue.status_history
        ]

        last_date = max(last_dates) if last_dates else None

        return first_date, last_date



    def simplify_hashboard_timeline(self, hashboard, start_date, end_date):
        # Build blank timeline
        timeline = {day: None for day in date_range(start_date, end_date)}

        # Insert status change events into timeline
        for change in hashboard.status_history:
            change_day = change.timestamp.date()
            timeline[change_day] = change.to_status

        # Fill in missing days by carrying forward the last known status
        last_status = None
        for day in sorted(timeline):
            if timeline[day] is None:
                timeline[day] = last_status
            else:
                last_status = timeline[day]

        return timeline


    def create_epic_timeline_data(self, epic_key):
    #used for sending packaged data to front end

        if self.epics[epic_key].issues is None: #this needs work, doesnt work right
            for _ in self.dump_issues_to_files(epic_key): #supposed to auto download the jira issues if they are missing
                pass

        epic_data = {
            "rt": epic_key,
            "title": self.epics[epic_key].title,
            "timeline": self.build_and_fill_epic_timeline(epic_key)
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

            # Advanced Repair or Backlog overnight is an error, shift it to Awating advanced repair
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



