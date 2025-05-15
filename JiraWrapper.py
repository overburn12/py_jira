from jira import JIRA
from jira.exceptions import JIRAError
from dotenv import load_dotenv
import os, time
import logging


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

