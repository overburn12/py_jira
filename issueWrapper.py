from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict

@dataclass
class IssueComment:
    author: str
    timestamp: datetime
    body: str

    def to_dict(self):
        return{
            'author': self.author,
            'timestamp': self.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            'body': self.body
        }

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

    def to_dict(self):
        return{
            'author': self.author,
            'from_status': self.from_status,
            'to_status': self.to_status,
            'timestamp': self.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        }

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
    serial: str
    created: datetime
    assignee: Optional[str] = None
    repair_summary: Optional[str] = None
    comments: List['IssueComment'] = field(default_factory=list)
    status_history: List['StatusChange'] = field(default_factory=list)

    def to_dict(self):
        return{
            'key': self.key,
            'serial': self.serial,
            'created': self.created.strftime("%Y-%m-%d %H:%M:%S"),
            'assignee': self.assignee,
            'repair_summary': self.repair_summary,
            'comments': [c.to_dict() for c in self.comments],
            'status_history': [s.to_dict() for s in self.status_history]
        }

    @classmethod
    def common_fields(cls, issue):
        fields = issue['fields']
        return {
            'key': issue['key'],
            'serial': fields['summary'],
            'created': datetime.strptime(fields['created'], "%Y-%m-%dT%H:%M:%S.%f%z"),
            'assignee': (fields.get('assignee') or {}).get('displayName'),
            'repair_summary': fields.get('customfield_10245'),
            'comments': sorted(
                [IssueComment.from_json(c) for c in fields.get('comment', {}).get('comments', [])],
                key=lambda c: c.timestamp
            ),
            'status_history': sorted(
                [
                    StatusChange.from_json(h, i)
                    for h in issue['changelog']['histories']
                    for i in h['items'] if i['field'] == "status"
                ],
                key=lambda s: s.timestamp
            )
        }


@dataclass
class Task(JiraIssue):
    type: str = "Task"
    board_model: Optional[str] = None

    def to_dict(self):
        data = super().to_dict()
        data['type'] = self.type
        data['board_model'] = self.board_model
        return data

    @classmethod
    def from_json(cls, issue: Dict):
        data = cls.common_fields(issue)
        cf = issue['fields'].get('customfield_10230')
        data['board_model'] = cf.get('value') if isinstance(cf, dict) else None
        return cls(**data)


@dataclass
class Story(JiraIssue):
    type: str = "Story"
    linked_issues: List[str] = field(default_factory=list)

    def to_dict(self):
        data = super().to_dict()
        data['type'] = self.type
        data['linked_issues'] = self.linked_issues
        return data

    @classmethod
    def from_json(cls, issue: Dict):
        data = cls.common_fields(issue)
        # You'll need to extract linked issue keys here based on your JIRA config
        issuelinks = issue['fields'].get('issuelinks', [])
        links = []
        for link in issuelinks:
            if 'outwardIssue' in link:
                links.append(link['outwardIssue']['key'])
            elif 'inwardIssue' in link:
                links.append(link['inwardIssue']['key'])
        data['linked_issues'] = links
        return cls(**data)
    

@dataclass
class Epic:
    key: str
    title: str
    start_date: datetime
    tasks: List[Task] = field(default_factory=list)
    stories: List[Story] = field(default_factory=list)

    def to_dict(self):
        return{
            'key': self.key,
            'title': self.title,
            'start_date': self.start_date.strftime("%Y-%m-%d %H:%M:%S"),
            'tasks': [t.to_dict() for t in self.tasks],
            'stories': [s.to_dict() for s in self.stories]
        }

    def load_json(self, json_data):
        self.tasks.clear()
        self.stories.clear()
        for issue in json_data:
            issue_type = issue['fields']['issuetype']['name']
            if issue_type == 'Task':
                self.tasks.append(Task.from_json(issue))
            elif issue_type == 'Story':
                self.stories.append(Story.from_json(issue))