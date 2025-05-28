
(function () {
  class IssueComment {
    constructor(author, timestamp, body) {
      this.author = author;
      this.timestamp = timestamp;
      this.body = body;
    }

    toDict() {
      return {
        author: this.author,
        timestamp: this.timestamp.toISOString().replace('T', ' ').split('.')[0],
        body: this.body
      };
    }

    static fromJson(comment) {
      return new IssueComment(
        comment.author.displayName,
        new Date(comment.created),
        comment.body
      );
    }
  }

  class StatusChange {
    constructor(author, fromStatus, toStatus, timestamp) {
      this.author = author;
      this.from_status = fromStatus;
      this.to_status = toStatus;
      this.timestamp = timestamp;
    }

    toDict() {
      return {
        author: this.author,
        from_status: this.from_status,
        to_status: this.to_status,
        timestamp: this.timestamp.toISOString().replace('T', ' ').split('.')[0]
      };
    }

    static fromJson(history, item) {
      return new StatusChange(
        history.author.displayName,
        item.fromString,
        item.toString,
        new Date(history.created)
      );
    }
  }

  class JiraIssue {
    constructor({ key, serial, created, assignee = null, repair_summary = null, comments = [], status_history = [] }) {
      this.key = key;
      this.serial = serial;
      this.created = created;
      this.assignee = assignee;
      this.repair_summary = repair_summary;
      this.comments = comments;
      this.status_history = status_history;
    }

    toDict() {
      return {
        key: this.key,
        serial: this.serial,
        created: this.created.toISOString().replace('T', ' ').split('.')[0],
        assignee: this.assignee,
        repair_summary: this.repair_summary,
        comments: this.comments.map(c => c.toDict()),
        status_history: this.status_history.map(s => s.toDict())
      };
    }

    static commonFields(issue) {
      const fields = issue.fields;
      const created = new Date(fields.created);
      const assignee = fields.assignee ? fields.assignee.displayName : null;

      const comments = (fields.comment?.comments || [])
        .map(IssueComment.fromJson)
        .sort((a, b) => a.timestamp - b.timestamp);

      const status_history = (issue.changelog?.histories || [])
        .flatMap(h => h.items
          .filter(i => i.field === "status")
          .map(i => StatusChange.fromJson(h, i))
        )
        .sort((a, b) => a.timestamp - b.timestamp);

      return {
        key: issue.key,
        serial: fields.summary,
        created,
        assignee,
        repair_summary: fields.customfield_10245,
        comments,
        status_history
      };
    }
  }

  class Task extends JiraIssue {
    constructor(data) {
      super(data);
      this.type = 'Task';
      this.board_model = data.board_model || null;
    }

    toDict() {
      const data = super.toDict();
      data.type = this.type;
      data.board_model = this.board_model;
      return data;
    }

    static fromJson(issue) {
      const data = JiraIssue.commonFields(issue);
      const cf = issue.fields.customfield_10230;
      data.board_model = (typeof cf === 'object' && cf?.value) || null;
      return new Task(data);
    }
  }

  class Story extends JiraIssue {
    constructor(data) {
      super(data);
      this.type = 'Story';
      this.linked_issues = data.linked_issues || [];
    }

    toDict() {
      const data = super.toDict();
      data.type = this.type;
      data.linked_issues = this.linked_issues;
      return data;
    }

    static fromJson(issue) {
      const data = JiraIssue.commonFields(issue);
      const links = [];
      for (const link of issue.fields.issuelinks || []) {
        if (link.outwardIssue) links.push(link.outwardIssue.key);
        else if (link.inwardIssue) links.push(link.inwardIssue.key);
      }
      data.linked_issues = links;
      return new Story(data);
    }
  }

  class Epic {
    constructor(key, title, start_date, tasks = [], stories = []) {
      this.key = key;
      this.title = title;
      this.start_date = start_date;
      this.tasks = tasks;
      this.stories = stories;
    }

    toDict() {
      return {
        key: this.key,
        title: this.title,
        start_date: this.start_date.toISOString().replace('T', ' ').split('.')[0],
        tasks: this.tasks.map(t => t.toDict()),
        stories: this.stories.map(s => s.toDict())
      };
    }

    loadJson(jsonData) {
      this.tasks = [];
      this.stories = [];
      for (const issue of jsonData) {
        const issueType = issue.fields.issuetype.name;
        if (issueType === 'Task') {
          this.tasks.push(Task.fromJson(issue));
        } else if (issueType === 'Story') {
          this.stories.push(Story.fromJson(issue));
        }
      }
    }
  }

  // Make classes available globally
  window.AppModels = {
    IssueComment,
    StatusChange,
    JiraIssue,
    Task,
    Story,
    Epic
  };
})();

