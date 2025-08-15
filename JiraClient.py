from helper import logger, date_range
from JiraWrapper import JiraWrapper
from issueWrapper import Story, Task, Epic
from datetime import datetime, timedelta

#-----------------------------------------------------------------------------------------------------------
# JiraClient Class
#-----------------------------------------------------------------------------------------------------------

class JiraClient(JiraWrapper):
    def __init__(self):
        super().__init__()
        self.holidays = [
            "2025-01-01",  # New Year's Day
            "2025-01-20",  # MLK Jr. Day
            "2025-02-17",  # Presidents' Day
            "2025-05-26",  # Memorial Day
            "2025-06-19",  # Juneteenth
            "2025-07-04",  # Independence Day
            "2025-09-01",  # Labor Day
            "2025-10-13",  # Columbus Day
            "2025-11-11",  # Veterans Day
            "2025-11-27",  # Thanksgiving
            "2025-12-25"   # Christmas
        ]

    def calculate_business_days(self, start_date, end_date):
        """Calculate number of business days between two dates, excluding weekends and federal holidays."""
        if not start_date or not end_date:
            return 0
            
        # Convert to date objects if they're datetime objects
        start_date_obj = start_date.date() if hasattr(start_date, 'date') else start_date
        end_date_obj = end_date.date() if hasattr(end_date, 'date') else end_date
        
        # Convert holiday strings to date objects
        holiday_dates = set()
        for holiday_str in self.holidays:
            try:
                holiday_date = datetime.strptime(holiday_str, "%Y-%m-%d").date()
                holiday_dates.add(holiday_date)
            except ValueError:
                continue
        
        business_days = 0
        current_date = start_date_obj
        
        while current_date <= end_date_obj:
            # Check if it's a weekday (Monday=0, Sunday=6) and not a holiday
            if current_date.weekday() < 5 and current_date not in holiday_dates:
                business_days += 1
            current_date += timedelta(days=1)
        
        return business_days

    def get_all_rt_epics(self):
        #returns json object for front-end order selection
        epic_list = []

        for epic_key in self.epics:
            epic = self.epics[epic_key]
            epic_list.append({
                "rt_num": epic.key,
                "summary": epic.title,
                "created": epic.start_date,
                "is_closed": self.is_order_closed(epic_key),
                "issue_count": len(epic.tasks)
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

    def epic_start_date(self, epic_key):
        issues = self.epics[epic_key].tasks
        epic = self.epics[epic_key]

        if not issues:
            return None

        # First date should be the epic start date or the earliest relevant issue activity
        epic_start_date = epic.start_date.date() if hasattr(epic.start_date, 'date') else epic.start_date
        first_date = datetime.combine(epic_start_date, datetime.min.time())
        return first_date

    def epic_end_date(self, epic_key):
        issues = self.epics[epic_key].tasks
        epic = self.epics[epic_key]

        if not issues:
            return None

        epic_start_date = epic.start_date.date() if hasattr(epic.start_date, 'date') else epic.start_date

        # Find the first date when all tasks are in 'Done' status
        last_date = None
        
        # Get all possible dates from status history across all issues, but only on or after epic start date
        all_dates = set()
        for issue in issues:
            if issue.status_history:
                for change in issue.status_history:
                    change_date = change.timestamp.date()
                    # Only consider status changes on or after epic start date
                    if change_date >= epic_start_date:
                        all_dates.add(change_date)
        
        if all_dates:
            # Sort dates chronologically
            sorted_dates = sorted(all_dates)
            
            # Check each date to see if all tasks are 'Done'
            for date in sorted_dates:
                all_done = True
                
                for issue in issues:
                    # Get the status of this issue on this date
                    issue_status = None
                    
                    # Find the most recent status change on or before this date, but only consider changes on or after epic start date
                    for change in sorted(issue.status_history, key=lambda x: x.timestamp):
                        change_date = change.timestamp.date()
                        if change_date >= epic_start_date and change_date <= date:
                            issue_status = change.to_status
                        elif change_date > date:
                            break
                    
                    # If this issue is not 'Done' on this date, not all are done
                    if issue_status != 'Done':
                        all_done = False
                        break
                
                # If all issues are 'Done' on this date, this is our last_date
                if all_done:
                    last_date = datetime.combine(date, datetime.min.time())
                    break
        
        # If no date found where all are 'Done', fall back to max of last status changes (but only after epic start date)
        if last_date is None:
            last_dates = []
            for issue in issues:
                if issue.status_history:
                    for change in reversed(issue.status_history):  # Start from most recent
                        if change.timestamp.date() >= epic_start_date:
                            last_dates.append(change.timestamp)
                            break
            last_date = max(last_dates) if last_dates else None

        return last_date

    def get_max_min_epic_dates(self, epic_key):
        return self.epic_start_date(epic_key), self.epic_end_date(epic_key)



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


    def get_first_date_from_timeline(self, epic_key):
        timeline = self.build_and_fill_epic_timeline(epic_key, format_date=False)
        if timeline is None:
            return None
        timeline_keys = list(timeline.keys())
        if timeline_keys:
            return min(timeline_keys)
        return None

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

            total_proccessed = ['Awaiting Functional Test', 'Passed Initial Diagnosis', 'Scrap', 'Done']

            #insert each hashboard timeline into the epic timeline
            for issue in issues:
                hb_timeline = self.simplify_issue_timeline(issue, start_date, end_date)

                for day in hb_timeline:
                    if day not in timeline:
                        continue
                    hb_status = hb_timeline[day]
                    hb_obj = {"serial": issue.serial, 'assignee': issue.assignee, 'board_model': issue.board_model}
                    if hb_status is not None:
                        if hb_status in total_proccessed:
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
                        if chassis_status in ["Ready to Ship"] and chassis_status not in ["Done"]:
                            if chassis_status not in status_list:
                                status_list.append(chassis_status)
                            if chassis_status not in timeline[day]:
                                timeline[day][chassis_status] = []
                            timeline[day][chassis_status].append(chassis_obj)
                        timeline[day]['Total Chassis'].append(chassis_obj)


        # PART 4: prune leading days
            #when hasboard replacement program is used, the hbr hashboard will mess up the timeline and greatly extend the beginning date

            pruned_timeline = {}
            timeline_days = list(timeline.keys())
            START = False
            START_COUNT = 1

            #set up a trigger that filters out all leading days with very low count (less than START_COUNT value)
            for day in timeline:
                current_day_meets_criteria = len(timeline[day]['Total Boards']) >= START_COUNT
                next_day_meets_criteria = False
                try:
                    current_index = timeline_days.index(day)
                    if current_index + 1 < len(timeline_days):
                        next_day = timeline_days[current_index + 1]
                        next_day_meets_criteria = len(timeline[next_day]['Total Boards']) >= START_COUNT
                except ValueError:
                    pass  # day not found in timeline_days (shouldn't happen)
                if current_day_meets_criteria or next_day_meets_criteria:
                    START = True
                if START:
                    if ('Done' in timeline[day] and 
                        len(timeline[day]['Done']) == len(timeline[day]['Total Boards'])):
                            break
                    
                    pruned_timeline[day] = {}
                    for status in status_list:
                        pruned_timeline[day][status] = None
                        if status in timeline[day]:
                            if pruned_timeline[day][status] is None:
                                pruned_timeline[day][status] = []
                            pruned_timeline[day][status] = timeline[day][status].copy()

            # Fallback: If no days met the start criteria, include all timeline data
            if not START:
                for day in timeline:
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
                "board_count": "Boards",
                'chassis_count': "Chassis",
                'is_closed': "Order State",
                'status_counts': "Status Counts",
                'first_date': "Start Date",
                'last_date': "Close Date",
                'day_count': "Days",
                'process_rate': "per Day"
            },
            "order": [
                "rt_num",
                "created",
                "summary",
                "board_count",
                "chassis_count",
                "first_date",
                "last_date",
                "day_count",
                "process_rate",
                "is_closed",
                "status_counts"
            ],
            "data": summary_data
        }        


    def is_order_closed(self, epic_key):
        """
        returns true if the order is closed, returns false if the order is open, returns none if the order has no data.
        an order is considered closed when all the tasks are in the 'Done' status on the same day.
        """
        epic = self.epics[epic_key]
        board_count = len(epic.tasks)

        done_count = 0
        for issue in epic.tasks:
            last_status = issue.status_history[-1].to_status
            if last_status == 'Done':
                done_count += 1
        if done_count == board_count:
            if done_count != 0:
                return True
            else:
                return None
        return False
    

    def get_board_counts(self, epic_key):
        epic = self.epics[epic_key]
        board_count = len(epic.tasks)
        status_counts = {"Passed Initial Diagnosis": 0, "Awaiting Functional Test": 0, "Scrap": 0}
        
        if board_count > 0:
            epic_timeline = self.build_and_fill_epic_timeline(epic_key=epic_key, format_date=False)
            if epic_timeline:
                # Get all days and reverse them to start from the last day
                timeline_days = list(epic_timeline.keys())
                timeline_days.reverse()  # Start from the most recent day
                
                for day in timeline_days:
                    day_data = epic_timeline[day]
                    temp_status_counts = {"Passed Initial Diagnosis": 0, "Awaiting Functional Test": 0, "Scrap": 0}
                    
                    # Count statuses for this day
                    for status in temp_status_counts:
                        if status in day_data and day_data[status]:
                            temp_status_counts[status] = len(day_data[status])
                    
                    # Check if this day's counts match the board_count
                    reported_total = sum(temp_status_counts.values())
                    
                    if reported_total == board_count:
                        # Found a matching day, return these counts
                        return temp_status_counts
                
                # If we get here, no day matched - return counts from last day with error
                last_day = timeline_days[0]  # First in reversed list is the last day
                last_day_data = epic_timeline[last_day]
                for status in status_counts:
                    if status in last_day_data and last_day_data[status]:
                        status_counts[status] = len(last_day_data[status])
                
                reported_total = sum(status_counts.values())
                status_counts['ERROR'] = f"MISSING {board_count - reported_total} BOARDS"
        
        return status_counts

    def get_order_summary(self, epic_key):
        epic = self.epics[epic_key]
        board_count = len(epic.tasks)
        chassis_count = len(epic.stories)

        order_state = self.is_order_closed(epic_key)
        is_closed = "Open"
        if order_state:
            is_closed = "Closed"
        if order_state is None:
            is_closed = ""

        status_counts = self.get_board_counts(epic_key)
        first_date = self.get_first_date_from_timeline(epic_key)
        _, last_date = self.get_max_min_epic_dates(epic_key)
        
        # Format dates to ISO format (YYYY-MM-DD) without time
        first_date_str = first_date.strftime('%Y-%m-%d') if first_date else None
        last_date_str = last_date.strftime('%Y-%m-%d') if last_date else None
        
        # Calculate day count (how many business days the order was active)
        day_count = 0
        if first_date and last_date:
            day_count = self.calculate_business_days(first_date, last_date)

        # Calculate process rate (boards per day)
        process_rate = 0
        if day_count > 0:
            process_rate = round(board_count / day_count, 1)

        return {
            "rt_num": epic.key,
            "summary": epic.title,
            "created": epic.start_date,
            "board_count": board_count,
            'chassis_count': chassis_count,
            'is_closed': is_closed,
            'status_counts': status_counts,
            'first_date': first_date_str,
            'last_date': last_date_str,
            'day_count': day_count,
            'process_rate': process_rate
        }