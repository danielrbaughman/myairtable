# Add Language

Ultrathink.

Add support for the following language: $ARGUMENTS

- This will be a significant undertaking, so you'll first need to thoroughly analyze all the existing supported languages to get a sense of how they work, and create a detailed plan for implementation. After the plan is complete, break it down into epic/features/tasks in beads.
  - After creating the first draft of the plan (v1), critique the plan and generate v2 of the plan. Use the `plan-critic` agent for this task. Then present v2 of the plan to me for my review.
- We want to get as close as possible to full parity with the existing supported languages.
- You'll probably need to create a custom client for the Airtable API, unless told otherwise.
- One of the primary goals is to make the generated code feel properly idiomatic for the target language. So make design choices with that in mind. The code should feel "normal"/"natural" to the target language.
- Concerning Testing:
  - You'll need to create unit tests equivalent to the existing unit tests in this repo. Check all languages to see what needs to be made. Ensure full test parity with the existing supported languages.
  - You'll need to create integration tests equivalent to the existing unit tests in `../myairtable-tests`. These are tests to see if the generated code works properly with real data. Be careful to reach full parity with the tests in the other languages. These tests are essential for ensuring that the generated code actually works.
    - The test files should be structured in a manner similar to those in the other languages.
    - Structure the task dependencies in a manner that allows you to get to some form of integration testing as quickly as possible, so you can discover mistakes early.
  - As one of your first tasks, setup the boilerplate for testing, both in the `myairtable` and `../myairtable-tests` repos.
  - For each task, make sure tests equivalent to the existing tests in other languages are added where applicable. Do not move on to another task until the tests exist and pass.
  - Before completing each task, compare the tests you made with the existing relevant tests, to ensure you didn't miss anything.
- Concerning Scripts:
  - `myairtable` has a `checks.sh` script, which you should run before completing each task. It will help detect issues in the code.
    - As one of your first tasks, add whatever new checks need to be added for the target language.
  - `../myairtable-tests` has a `test.sh` script, which will regenerate the code, run checks, and run unit tests. This should be the primary way you run the integration tests. Be sure to run it before completing each task.
    - As one of your first tasks, add whatever new checks need to be added for the target language.
- Feel free to ask me clarifying questions before you begin.

Use the following MCP tools to help you, both for planning and implementing the plan.

- Context7
- Sequential Thinking
- GitHub
