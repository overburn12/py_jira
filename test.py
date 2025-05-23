from JiraWrapper import JiraWrapper


jira = JiraWrapper()

for epic_key in jira.epics:
    epic = jira.epics[epic_key]
    issues = epic.issues

    if len(issues) > 0:
        print(f"{epic.key}: {epic.title}")
        for issue in issues:
            print(f"{issue.serial} ({issue.board_model}) {issue.issue_type} - {issue.created}")