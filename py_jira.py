from jira import JIRA
from datetime import datetime
from dotenv import load_dotenv
import os

load_dotenv()


def connect_jira():
    server = os.getenv('SERVER')
    email = os.getenv('EMAIL')
    token = os.getenv('JIRA_TOKEN')

    jira_options = {
        'server': server 
    }

    try:
        jira = JIRA(options=jira_options, basic_auth=(email, token))
    except Exception as e:
        print(f"Failed to connect to JIRA: {e}")
        return ''
    
    return jira


def get_all_rt_epics(jira):
    try:
        jql = 'issuetype = Epic AND project = RT ORDER BY created DESC'
        epics = jira.search_issues(jql, maxResults=1000)
        epic_list = []
        for epic in epics:
            if epic.key.startswith("RT-"):
                created_time = datetime.strptime(epic.fields.created[:19], "%Y-%m-%dT%H:%M:%S")
                epic_list.append({
                    "rt_num": epic.key,
                    "summary": epic.fields.summary,
                    "created": created_time
                })
        return epic_list
    except Exception as e:
        print(f"Failed to fetch RT epics: {e}")
        return []


def get_hashboards_from_epic(jira, epic_key):
    jql = f'"Epic Link" = {epic_key} AND issuetype = Task'

    start_at = 0
    max_results = 10

    try:
        while True:
            issues = jira.search_issues(
                jql,
                startAt=start_at,
                maxResults=max_results,
                expand="changelog,comment"
            )
            if not issues:
                break

            # send progress update
            yield ({
                "progress_update": True,
                "current": start_at,
                "total": issues.total
            })

            for issue in issues:
                # Only look at tasks (hashboard level tickets)
                if issue.fields.issuetype.name.lower() != "task":
                    continue

                serial = issue.fields.summary  # Assuming serial is stored in the summary
                rt_num = issue.key
                board_model = getattr(issue.fields, 'customfield_10230', None)
                repair_summary = getattr(issue.fields, 'customfield_10245', None)
                events = []

                # add the status changes
                if hasattr(issue, 'changelog'):
                    for history in issue.changelog.histories:
                        for item in history.items:
                            if item.field == "status":
                                timestamp = datetime.strptime(history.created[:19], "%Y-%m-%dT%H:%M:%S")
                                events.append({
                                    "type": "status_change",
                                    "from": item.fromString,
                                    "to": item.toString,
                                    "time": timestamp,
                                    "length": None,
                                    "author": history.author.displayName if history.author else "Unknown"
                                })

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

                # Grab comments
                if hasattr(issue.fields, 'comment') and hasattr(issue.fields.comment, 'comments'):
                    for comment in issue.fields.comment.comments:
                        events.append({
                            "type": "comment",
                            "author": comment.author.displayName if comment.author else "Unknown",
                            "time": datetime.strptime(comment.created[:19], "%Y-%m-%dT%H:%M:%S"),
                            "body": comment.body
                        })

                events.sort(key=lambda x: x["time"])

                # --- Build hashboard data
                yield ({
                    "serial": serial,
                    "rt_num": rt_num,
                    "board_model": board_model.value if board_model else 'N/A',
                    "repair_summary": repair_summary,
                    "events": events
                })

            if len(issues) < max_results:
                break  # No more pages to fetch
            start_at += max_results

    except Exception as e:
        print(f"Failed to search issues under epic {epic_key}: {e}")
        return
        

def filter_single_result(hb):
    if 'progress_update' in hb:
        return hb
    
    image_extensions = (".png", ".jpeg", ".jpg")

    advanced_repair = False
    awaiting_functional_test = False
    scrap = False

    if hb['repair_summary']:
        repair_summary = hb['repair_summary'].replace("\n", "-")
    else:
        repair_summary = 'N/A'

    temp_hb = {
        "serial": hb['serial'],
        "rt_num": hb['rt_num'],
        "board_model": hb['board_model'],
        "repair_summary": repair_summary,
        "events": []
    }

    for thing in hb['events']:
        if thing['type'] == "status_change":
            if thing['to'] == "Advanced Repair":
                advanced_repair = True
                temp_hb['events'].append(thing)
            if thing['to'] == "Awaiting Functional Test":
                awaiting_functional_test = True
                temp_hb['events'].append(thing)
            if thing['to'] == "Scrap":
                scrap = True

        if thing['type'] == "comment":
            if not any(ext in thing["body"] for ext in image_extensions):
                thing['body'] = thing['body'].replace("\n", "-")
                temp_hb['events'].append(thing)

    if advanced_repair and awaiting_functional_test and not scrap:
        return temp_hb
    else:
        return None
    
