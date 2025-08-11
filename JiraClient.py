from helper import logger, date_range
from JiraWrapper import JiraWrapper
from issueWrapper import Story, Task, Epic

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
            issue_count = len(epic.tasks)
            epic_list.append({
                "rt_num": epic.key,
                "summary": epic.title,
                "created": epic.start_date,
                "issue_count": issue_count
            })

        return epic_list
    
    
    def get_total_epic(self, epic_key):
        return self.epics[epic_key].to_dict()
    

    def get_serial_from_key_and_epic(self, issue_key, epic_key):
        issue = None

        for check_issue in self.epics[epic_key].tasks:
            if check_issue.key == issue_key:
                issue = check_issue
                break

        if issue is None: #check stories if its not found in tasks
            for check_issue in self.epics[epic_key].stories:
                if check_issue.key == issue_key:
                    issue = check_issue
                    break
        
        if issue is None:
            return "Not Found"
        
        return issue.serial


    def create_issue_summary_by_serial_from_epic(self, serial, epic_key):
        issue = None

        for check_issue in self.epics[epic_key].tasks:
            if check_issue.serial == serial:
                issue = check_issue
                break

        if issue is None: #check stories if its not found in tasks
            for check_issue in self.epics[epic_key].stories:
                if check_issue.serial == serial:
                    issue = check_issue
                    break
        
        return self.create_issue_summary(issue, epic_key)


    def create_issue_summary(self, issue, epic_key):
        #compiles hashboard data, repair summary, status changes, and comments for display on the front end.
        
        if issue is None:
            return {   
            "serial": "NoneType",
            "assignee": "NoneType",
            "rt_num": "NoneType",
            "board_model": 'NoneType',
            "repair_summary": "Issue not found",
            "events": []
        }       

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

        # sort events chronologically, so we can calc status lengths properly
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
                    duration = next_status_time - event["time"]
                    total_minutes = int(duration.total_seconds() // 60)
                    hours, minutes = divmod(total_minutes, 60)
                    event["length"] = f"{hours:01}h {minutes:02}m"
                else:
                    event["length"] = "Current Status"  # Final status, no next one
                

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

        filtered_events = []

        #filter events / set flags
        for event in events:

            event['time'] = event['time'].strftime("%Y-%m-%d %H:%M")
            if event['type'] == "status_change":
                filtered_events.append(event)


            if event['type'] == "comment":
                event['body'] = event['body'].replace("\n", "-")
                filtered_events.append(event)

        result = {
            "serial": issue.serial,
            "rt_num": issue.key,
            "assignee": issue.assignee,
            "repair_summary": issue.repair_summary.replace('\n', '-') if issue.repair_summary else 'N/A',
            "events": filtered_events
        }

        if issue.type == "Story":
            serial_list = []

            for linked_issue in issue.linked_issues:
                serial_list.append(self.get_serial_from_key_and_epic(linked_issue, epic_key))

            result["linked_issues"] = serial_list
        else:
            result["board_model"] = issue.board_model if issue.board_model else 'N/A'

        return result 


    def get_issue_summary_from_epic(self, epic_key):
        issue_list = []

        for issue in self.epics[epic_key].tasks:
            last_timestamp = None
            summary = self.create_issue_summary(issue, epic_key)
            for event in summary['events']:
                last_timestamp = event['time']
            summary['time'] = last_timestamp
            issue_list.append(summary)

        issue_list.sort(key=lambda x: x["time"])
        for issue in issue_list:
            yield issue


    def get_repair_data_from_epic(self, epic_key):
        # filters repair status and comments using create_issue_summary
        # yields only issues that passed through Advanced Repair & Awaiting Functional Test, and were NOT scrapped
        
        issue_list = []
        image_extensions = (".png", ".jpeg", ".jpg") #skip comments with images

        for issue in self.epics[epic_key].tasks:
            summary = self.create_issue_summary(issue, epic_key)
            events = summary["events"]

            advanced_repair = False
            awaiting_functional_test = False
            scrap = False
            last_timestamp = None

            filtered_events = []

            for event in events:
                if event['type'] == "status_change":
                    if event['to'] == "Advanced Repair":
                        filtered_events.append(event)
                        advanced_repair = True
                        last_timestamp = event['time']
                    elif event['to'] == "Awaiting Functional Test":
                        filtered_events.append(event)
                        awaiting_functional_test = True
                        last_timestamp = event['time']
                    elif event['to'] == "Scrap":
                        scrap = True
                elif event['type'] == "comment":
                    if not any(ext in event["body"] for ext in image_extensions):
                        filtered_events.append(event)
                        last_timestamp = event['time']

            if advanced_repair and awaiting_functional_test and not scrap:
                summary["time"] = last_timestamp
                summary['events'] = filtered_events
                issue_list.append(summary)

        issue_list.sort(key=lambda x: x["time"])
        for issue in issue_list:
            yield issue
            


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
            "BHB68701",
            "BHB68703"
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
        issues = self.epics[epic_key].tasks


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



    def simplify_issue_timeline(self, issue, start_date, end_date):
        # Build blank timeline
        created_date = issue.created.date()
        timeline = {day: None for day in date_range(created_date, end_date)}

        # Insert status change events into timeline
        for change in issue.status_history:
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

        #if self.epics[epic_key].issues is None: #this needs work, doesnt work right
        #    for _ in self.dump_issues_to_files(epic_key): #supposed to auto download the jira issues if they are missing
        #        pass

        epic_data = {
            "rt": epic_key,
            "title": self.epics[epic_key].title,
            "timeline": self.build_and_fill_epic_timeline(epic_key)
        }

        return epic_data


    def build_and_fill_epic_timeline(self, epic_key, format_date = True):
            #creates a timeline container with total counts for each status for each day
            start_date, end_date = self.get_max_min_epic_dates(epic_key)

            if start_date is None and end_date is None:
                logger.warning(f"No data for {epic_key}")
                return None

            #override
            start_date = self.epics[epic_key].start_date.date()

        # PART 1: create the empty timeline container

            timeline = {}
            status_list = ['Total Boards', 'Total Chassis', 'Total Processed']
            for day in date_range(start_date, end_date):
                timeline[day] = {}
                for status in status_list:
                    timeline[day][status] = []

        # PART 2: insert hb statuses into timeline container
            issues = self.epics[epic_key].tasks

            # Advanced Repair or Backlog overnight is an error, shift it to Awating advanced repair
            convert_status = {
                "Advanced Repair": "Awaiting Advanced Repair",
                "Backlog": "Awaiting Advanced Repair"
            }

            total_good = ['Awaiting Functional Test', 'Passed Initial Diagnosis']

            #insert each hashboard timeline into the epic timeline
            for issue in issues:
                hb_timeline = self.simplify_issue_timeline(issue, start_date, end_date)

                for day in hb_timeline:
                    if day not in timeline:
                        continue
                    hb_status = hb_timeline[day]
                    hb_obj = {"serial": issue.serial, 'assignee': issue.assignee, 'board_model': issue.board_model}
                    if hb_status is not None:
                        if hb_status in total_good:
                            timeline[day]['Total Processed'].append(hb_obj)
                        if hb_status in 'Scrap':
                            timeline[day]['Total Processed'].append(hb_obj)
                        if hb_status in convert_status:
                            hb_status = convert_status[hb_status] 
                        if hb_status not in status_list:
                            status_list.append(hb_status)
                        if hb_status not in timeline[day]:
                            timeline[day][hb_status] = []
                        timeline[day][hb_status].append(hb_obj)
                    timeline[day]['Total Boards'].append(hb_obj)

        # PART 3: insert chassis status into the timeline
            issues = self.epics[epic_key].stories

            for issue in issues:
                chassis_timeline = self.simplify_issue_timeline(issue, start_date, end_date)

                for day in chassis_timeline:
                    if day in timeline:
                        chassis_status = chassis_timeline[day]
                        chassis_obj = {"serial": issue.serial, "assignee": issue.assignee}
                        if chassis_status in ["Ready to Ship"]:
                            if chassis_status not in status_list:
                                status_list.append(chassis_status)
                            if chassis_status not in timeline[day]:
                                timeline[day][chassis_status] = []
                            timeline[day][chassis_status].append(chassis_obj)
                        timeline[day]['Total Chassis'].append(chassis_obj)


        # PART 4: prune leading days
            #when hasboard replacement program is used, the hbr hashboard will mess up the timeline and greatly extend the beginning date

            pruned_timeline = {}
            START = False
            START = True #overrides the pruning and prevents it. just send the timeline as-is.

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

            if not format_date:
                return pruned_timeline

            #jsonify cant serialize datetime as a key, so convert to iso format (YYYY-MM-DD)
            timeline_str_keys = {day.isoformat(): data for day, data in pruned_timeline.items()}

            return timeline_str_keys


#-----------------------------------------------------------------------------------------------------------
# Order Summary Functions
#-----------------------------------------------------------------------------------------------------------

    def get_all_order_summaries(self):
        summary_data = []

        for epic_key in self.epics:
            epic_summary = self.get_order_summary(epic_key)
            summary_data.append(epic_summary)

        return {
            "labels": {
                "rt_num": "Epic Key",
                "summary": "Summary",
                "created": "Created Date",
                "board_count": "Board Count",
                'chassis_count': "Chassis Count",
                'is_closed': "Order Closed",
                'status_counts': "Status Counts"
            },
            "order": [
                "rt_num",
                "summary",
                "created",
                "board_count",
                "chassis_count",
                "is_closed",
                "status_counts"
            ],
            "data": summary_data
        }        


    def get_order_summary(self, epic_key):

        epic = self.epics[epic_key]

        board_count = len(epic.tasks)
        chassis_count = len(epic.stories)

        done_count = 0
        for issue in self.epics[epic_key].tasks:
            last_status = issue.status_history[-1].to_status
            if last_status == 'Done':
                done_count += 1
        is_closed = "Open"
        if done_count == board_count:
            if done_count != 0:
                is_closed = "Closed"
            else:
                is_closed = ""

        status_counts = {"Passed Initial Diagnosis": 0, "Awaiting Functional Test": 0, "Scrap": 0}
        if board_count > 0:
            epic_timeline = self.build_and_fill_epic_timeline(epic_key=epic_key, format_date=False)
            if epic_timeline:
                last_day = None
                for day in epic_timeline:
                    last_day = day
                last_day_data = epic_timeline[last_day]
                for status in last_day_data:
                    if status in status_counts:
                        if last_day_data[status]:
                            status_counts[status] = len(last_day_data[status])
                reported_total = 0
                for status in status_counts:
                    reported_total += status_counts[status]
                if board_count != reported_total:
                    status_counts['_ERROR'] = F"MISSING {board_count - reported_total} BOARDS"

        return {
            "rt_num": epic.key,
            "summary": epic.title,
            "created": epic.start_date,
            "board_count": board_count,
            'chassis_count': chassis_count,
            'is_closed': is_closed,
            'status_counts': status_counts
        }