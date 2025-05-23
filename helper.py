import logging
from datetime import date, timedelta

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


def full_rt(epic_key):
        if not epic_key.startswith("RT-"):
            return "RT-" + epic_key
        else:
            return epic_key
