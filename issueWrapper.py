from dataclasses import dataclass, field
from datetime import datetime
from typing import List

@dataclass
class IssueComment:
    author: str
    timestamp: datetime
    body: str

    @classmethod
    def from_json(cls, comment):
        return cls(
            author=comment['author']['displayName'],
            timestamp=datetime.strptime(comment['created'], "%Y-%m-%dT%H:%M:%S.%f%z"),
            body=comment['body']
        )
    

@dataclass
class StatusChange:
    author: str
    from_status: str
    to_status: str
    timestamp: datetime

    @classmethod
    def from_json(cls, history, item):
        author = history['author']['displayName']
        from_status = item['fromString']
        to_status = item['toString']
        timestamp = datetime.strptime(history['created'], "%Y-%m-%dT%H:%M:%S.%f%z")

        return cls( 
            author=author, from_status=from_status,
            to_status=to_status, timestamp=timestamp
        )
    

@dataclass
class JiraIssue:
    key: str
    issue_type: str
    serial: str
    created: datetime
    board_model: str | None = None
    repair_summary: str | None = None
    comments: List[IssueComment] = field(default_factory=list)
    status_history: List[StatusChange] = field(default_factory=list)

    @classmethod
    def from_json(cls, issue):
        fields = issue['fields']
        issue_type = fields['issuetype']['name']
        serial = fields['summary'] 
        key = issue['key']
        created=datetime.strptime(fields['created'], "%Y-%m-%dT%H:%M:%S.%f%z")
        board_model = None
        cf = fields.get('customfield_10230')
        if cf and isinstance(cf, dict):
            board_model = cf.get('value')
        repair_summary = fields.get('customfield_10245', None)

        status_history = []

        changelog = issue['changelog']
        for history in changelog['histories']:
            for item in history['items']:
                if item['field'] == "status":
                        status_history.append(StatusChange.from_json(history, item))
        status_history.sort(key=lambda s: s.timestamp)

        comments = []

        for comment in fields.get('comment', {}).get('comments', []):
            comments.append(IssueComment.from_json(comment))
        comments.sort(key=lambda s: s.timestamp)

        return cls(
            key=key, serial=serial, repair_summary=repair_summary,
            issue_type=issue_type, board_model=board_model, created=created,
            status_history=status_history, comments=comments
        )


@dataclass
class Epic():
    key: str
    title: str
    start_date: str
    issues: List[JiraIssue] = field(default_factory=list)
    task_count: int = 0
    story_count: int = 0

    def load_json(self, json_data):
        self.task_count = 0
        self.story_count = 0
        if self.issues is None:
            self.issues = []
        for issue in json_data:
            self.issues.append(JiraIssue.from_json(issue))
        for issue in self.issues:
            if issue.issue_type == 'Task':
                self.task_count += 1
            if issue.issue_type == 'Story':
                self.story_count += 1