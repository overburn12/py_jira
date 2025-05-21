from dataclasses import dataclass

@dataclass
class JiraIssue:
    summary: str
    key: str

@dataclass
class Epic(JiraIssue):
    issues: list

@dataclass
class Hashboard(JiraIssue):
    start_date: str