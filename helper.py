import logging, os, json
from datetime import date, timedelta, datetime

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

logger = logging.getLogger(__name__)


def date_range(start_date, end_date):
    current_date = date(start_date.year, start_date.month, start_date.day)
    end_date = date(end_date.year, end_date.month, end_date.day)

    while current_date <= end_date:
        yield current_date
        current_date += timedelta(days=1)


def previous_day(date_obj, day_delta = 1):
    return date_obj - timedelta(days=day_delta)


def get_initials(input_string):
    words = input_string.split()
    initials = [word[0].upper() for word in words]
    return ''.join(initials)


def load_epic_metadata(input_dir="jira_dumps", filename="epic-list.json"):
    input_path = os.path.join(input_dir, filename)

    try:
        with open(input_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        return None
    

def full_rt(epic_key):
        if not epic_key.startswith("RT-"):
            return "RT-" + epic_key
        else:
            return epic_key
        

def format_timeline_for_chartjs(epic_data):
    timeline = epic_data["timeline"]
    
    # Sorted list of date labels
    labels = sorted(timeline.keys())

    # Find all possible status labels from the first day (assumes all days have same keys)
    all_statuses = timeline[labels[0]].keys()

    # Build datasets: one per status
    datasets = []
    for status in all_statuses:
        datasets.append({
            "label": status,
            "data": [timeline[day][status] for day in labels]
        })

    return {
        "labels": labels,
        "datasets": datasets,
        "title": epic_data['title']
    }
