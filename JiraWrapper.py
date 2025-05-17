from jira import JIRA
from jira.exceptions import JIRAError
from dotenv import load_dotenv
import os, time, json
import logging

from helper import logger, load_epic_metadata, date_range, get_initials, full_rt, format_timeline_for_chartjs, previous_day


logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

logger = logging.getLogger(__name__)

load_dotenv()


#-----------------------------------------------------------------------------------------------------------
# JiraClient Class
#-----------------------------------------------------------------------------------------------------------

class JiraWrapper:
    def __init__(self):
        self.server = os.getenv('SERVER')
        self.email = os.getenv('EMAIL')
        self.token = os.getenv('JIRA_TOKEN')
        self.root_cert = os.getenv('ROOT_CERT')
        self.last_request_time = 0
        self.RATE_LIMIT_DELAY = 1.0
        self.jira = self.connect()

        # Load local metadata into memory
        self._rt_epic_data = load_epic_metadata() 

        # if it doesnt exist, then grab from jira and load it
        if self._rt_epic_data is None:
            self.dump_all_rt_epics_metadata()
            self._rt_epic_data = load_epic_metadata()


    def connect(self):
        options = {'server': self.server}
        if self.root_cert:
            cert_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), self.root_cert)
            options['verify'] = cert_path

        try:
            return JIRA(options=options, basic_auth=(self.email, self.token))
        except Exception as e:
            logger.error(f"Failed to connect to JIRA: {e}")
            return None


    def search_issues(self, jql_str, max_retries=10, batch_size=100, paginate=True, expand=None, yield_progress=False, **kwargs):
        if not self.jira:
            logger.error("No JIRA connection.")
            return

        retries = 0
        start_at = 0

        while True:
            elapsed = time.time() - self.last_request_time
            if elapsed < self.RATE_LIMIT_DELAY:
                time.sleep(self.RATE_LIMIT_DELAY - elapsed)

            try:
                issues = self.jira.search_issues(
                    jql_str,
                    startAt=start_at,
                    maxResults=batch_size,
                    expand=expand,
                    **kwargs
                )
                self.last_request_time = time.time()

                if not issues:
                    break

                for issue in issues:
                    yield issue

                if yield_progress:
                    yield {
                        "progress_update": True,
                        "current": start_at + len(issues),
                        "total": issues.total
                    }

                if not paginate or len(issues) < batch_size:
                    break

                start_at += batch_size

            except JIRAError as e:
                if e.status_code == 429:
                    retry_after = int(e.response.headers.get('Retry-After', 10))
                    logger.warning(f"[Retry {retries+1}/{max_retries}] 429 Too Many Requests - Backing off for {retry_after} seconds...")
                    time.sleep(retry_after)
                    retries += 1
                else:
                    logger.error(f"JIRA API error: {e}")
                    break
            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                break

        if retries > max_retries:
            logger.warning("Max retries reached or unrecoverable error.")


    def get_jira_issues_from_epic(self, epic_key, expand=None, batch_size=100, include_progress=False):
        full_key = full_rt(epic_key)
        jql = f'"Epic Link" = {full_key}'

        for item in self.search_issues(jql, expand=expand, batch_size=batch_size, yield_progress=include_progress):
            yield item


    def dump_all_rt_epics_metadata(self, output_dir="jira_dumps", filename="epic-list.json"):
        os.makedirs(output_dir, exist_ok=True)
        epic_data = []
        key_list = []

        try:
            jql = 'issuetype = Epic AND project = RT'
            for item in self.search_issues(jql, paginate=True, batch_size=100):
                if isinstance(item, dict):
                    continue  # Skip progress updates if any
                if item.key.startswith("RT-"):
                    key_list.append(f"{item.key} - {item.fields.summary}")
                    epic_data.append(item.raw)
        except Exception as e:
            logger.exception(f"Failed to fetch RT epics: {e}")
            return {"error": f"Failed to fetch RT epics: {e}"}

        output_path = os.path.join(output_dir, filename)
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(epic_data, f, indent=2)
            logger.info(f"Saved {len(epic_data)} epics to {output_path}")
        except Exception as e:
            logger.exception(f"Failed to write epic list file: {e}")
            return {"error": f"Failed to write epic list file: {e}"}

        self._rt_epic_data = epic_data
        return {
            "message": f"Saved {len(epic_data)} epics to {output_path}",
            "epic_list": key_list
        }


    def get_epic_summary(self, epic_key):
        #returns the summary/title of the requested epic RT

        full_key = full_rt(epic_key)

        for epic in self._rt_epic_data:
            if epic.get("key") == full_key:
                return epic.get("fields", {}).get("summary")

        return f"Epic {full_key} not found."



    def dump_issues_to_files(self, epic_key, output_dir="jira_dumps"):
        #dumps all task issues to file for a given epic

        full_key = full_rt(epic_key)
        os.makedirs(output_dir, exist_ok=True)

        logger.info(f"Dumping all task issues for {full_key}...")

        file_path = os.path.join(output_dir, f"{full_key}.json")
        issue_data = []

        try:
            #collect the issues
            for issue in self.get_jira_issues_from_epic(full_key, expand="changelog,comment"):
                issue_data.append(issue.raw)  

            #dump issues to file
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(issue_data, f, indent=2, ensure_ascii=False)


            logger.info(f"Saved {len(issue_data)} issues to {file_path}")
        except Exception as e:
            logger.exception(f"Failed to dump {full_key}: {e}")



    def load_issues_from_file(self, epic_key, type="all", output_dir="jira_dumps"):
        valid_type = ["task", "child", "all"]
        if type not in valid_type:
            logger.exception(f"load_issues_from_file() Wrong issue type used: {type}")
            return None
        
        full_key = full_rt(epic_key)
        epic_file = os.path.join(output_dir, f"{full_key}.json")

        # Check for file, generate if needed
        if not os.path.isfile(epic_file):
            self.dump_issues_to_files(epic_key, output_dir)

        try:
            with open(epic_file, 'r', encoding='utf-8') as f:
                epic_data =  json.load(f)
                if type.lower() == "all":
                    return epic_data
                filtered_epic_data = []
                for issue in epic_data:
                    #issue_type = issue.get("fields", {}).get("issuetype", {}).get("name", "").lower()
                    issue_type = issue['fields']['issuetype']['name'].lower()
                    if issue_type == type.lower():
                        filtered_epic_data.append(issue)
                return filtered_epic_data


        except Exception as e:
            logger.exception(f"Failed to load issue file for {full_key}: {e}")
            return None
