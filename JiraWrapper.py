from jira import JIRA
from jira.exceptions import JIRAError
from datetime import datetime
from dotenv import load_dotenv
import os, time, json

from helper import logger, full_rt
from issueWrapper import Epic


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
        self.data_directory = "jira_dumps"
        self.epic_metadata_file = "epic-list.json"
        self.epic_prune_file = "epic_prune.json"

        # Load epic metadata into memory
        rt_epic_data = self.load_epic_metadata() 

        self.epics = {}

        #load epics from epic metadata
        for epic_data in rt_epic_data:
            key = epic_data.get("key", "")
            fields = epic_data.get("fields", {})
            if key.startswith("RT-"):
                created_time = datetime.strptime(fields["created"][:19], "%Y-%m-%dT%H:%M:%S")
                created_date = created_time.strftime("%Y-%m-%d")
                title=fields.get("summary", "")
            
                epic = Epic(key=key, title=title, start_date=created_date)

                issue_file = os.path.join(self.data_directory,f"{key}.json")
                if os.path.exists(issue_file):
                    with open(issue_file, "r") as issue_f:
                        issue_data = json.load(issue_f)
                        epic.load_json(issue_data)

                self.epics[key] = epic


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


    def load_epic_metadata(self):
        #returns epic metadata from file
        epic_metadata_file = os.path.join(self.data_directory, self.epic_metadata_file)
        try:
            with open(epic_metadata_file, 'r', encoding='utf-8') as f:
                epic_metadata = json.load(f)
        except Exception as e:
            epic_metadata = None

        if epic_metadata is None:
            epic_metadata = self.get_epics_from_jira()
            try:
                with open(epic_metadata_file, 'w', encoding='utf-8') as f:
                    json.dump(epic_metadata, f, indent=2)
            except Exception as e:
                logger.exception(f"Failed to write epic list file: {e}")
                return None
            
        epic_prune_list = self.get_epic_prune_list()
        filtered_epics = []
        for epic in epic_metadata:
            if epic['key'] not in epic_prune_list:
                filtered_epics.append(epic)
        
        return filtered_epics


    def get_epics_from_jira(self):
        #returns all epic issues from RT project
        epic_metadata = []

        try:
            jql = 'issuetype = Epic AND project = RT'
            for item in self.search_issues(jql, paginate=True, batch_size=100):
                if isinstance(item, dict):
                    continue  # Skip progress updates if any
                if item.key.startswith("RT-"):
                    epic_metadata.append(item.raw)
        except Exception as e:
            logger.exception(f"Failed to fetch RT epics: {e}")
            return None
        
        return epic_metadata


    def get_jira_issues_from_epic(self, epic_key, expand=None, batch_size=100, yield_progress=False):
        #yields all issues from epic key
        full_key = full_rt(epic_key)
        jql = f'"Epic Link" = {full_key}'

        for item in self.search_issues(jql, expand=expand, batch_size=batch_size, yield_progress=yield_progress):
            yield item


    def get_epic_prune_list(self):
        #returns the content of the epic prune file
        file_path = os.path.join(self.data_directory, self.epic_prune_file)
        if not os.path.exists(file_path):
            logger.exception(f"File '{file_path}' not found. Returning empty list.")
            return []

        try:
            with open(file_path, 'r') as f:
                prune_list = json.load(f)
                return prune_list
        except json.JSONDecodeError as e:
            logger.exception(f"Error parsing JSON in '{file_path}': {e}. Returning empty list.")
            return []


    def dump_issues_to_files(self, epic_key):
        #dumps all task issues to file for a given epic

        full_key = full_rt(epic_key)
        file_path = os.path.join(self.data_directory, f"{full_key}.json")
        os.makedirs(self.data_directory, exist_ok=True)

        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"Deleted file {file_path}")
        except Exception as e:
            logger.exception(f"Failed to delete {file_path}: {e}")

        logger.info(f"Dumping all task issues for {full_key}...")

        issue_data = []

        try:
            #collect the issues
            for issue in self.get_jira_issues_from_epic(full_key, expand="changelog,comment", yield_progress=True):
                if isinstance(issue, dict) and issue.get("progress_update"):
                    yield issue
                else:
                    issue_data.append(issue.raw)

            #dump issues to file
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(issue_data, f, indent=2, ensure_ascii=False)

                #load the new data into the epic model
                self.epics[epic_key].issues = None
                self.epics[epic_key].load_json(issue_data)

            logger.info(f"Saved {len(issue_data)} issues to {file_path}")
        except Exception as e:
            logger.exception(f"Failed to dump {full_key}: {e}")