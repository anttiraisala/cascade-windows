# Language rule

**Everything that goes into the project and its repository must be in English**, whatever language the conversation with the maintainer is in.

## Conversation

- Reply to the maintainer in the language they write in (for example Finnish). This applies to explanations, questions and status updates in the chat.
- Write every project artifact in English, regardless of the chat language.

## What must be in English

- Source code: identifiers (variables, functions, classes, files, folders), string constants, log messages, error messages and exceptions
- Code comments: inline and block comments, docstrings, JSDoc/KDoc/Javadoc, TODO/FIXME notes
- User-facing text: UI texts, labels, buttons, menus, placeholders, tooltips, notifications, validation messages, empty and error states, in-game text
- Documentation: README, CONTRIBUTING, CHANGELOG, architecture and design documents, ADRs, API docs, setup guides, rule notes
- Configuration and metadata: config file comments, package descriptions, environment variable descriptions
- Tests: test names, descriptions, assertion messages and test data labels
- Data files: data labels, seed data, table and column names, migration descriptions
- Version control: commit messages, branch names, pull request titles and descriptions

## Localization

- Do not write Finnish (or any other language) into the UI or code unless the maintainer explicitly asks for localization or i18n support.
- If localization is requested, keep English as the source and default language. Put translations in separate resource files (for example i18n JSON files). Source keys stay in English.

## Handling non-English input

- When the maintainer describes a feature, name, requirement or text in another language, translate it into clear, idiomatic English before using it in code, UI, data files or docs.
- Do not copy non-English text verbatim into any project file. The only exception is a literal string the maintainer explicitly provides and that must stay in its original language (for example a translation example requested for i18n).
- If a term has no good English equivalent, choose the closest natural English term and mention the choice briefly in the chat.

## Consistency check

Before reporting any task as done, verify that no non-English text has slipped into code, comments, docs, UI, data files or commit messages. Fix any such text first.
