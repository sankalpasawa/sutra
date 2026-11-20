# Release note draft: projects (not released: the flag stays 0 in every default, D341)

Written for the person who downloads the app, to go in `docs/release-notes/X.Y.Z.md` only when the owner says release and the checks of "Before publish" are done.

### What is new

- **Projects.** A request the chat splits into steps can now run as a project: several agents at work, some at the same time, one page to watch them and one button to stop them all. It is off until you turn it on.
- **Questions you answer.** Before a step reads GitHub, reads the app's own data, changes several places of your folder, or a plan costs a lot, Sutra asks. Decide for me can answer the ordinary ones. It never answers about your computer's permissions, the app's own data, a plan over 1000 credits, a reviewer's question, or keeping work that went outside its place.

### Good to know

- A step that runs through Codex can change files outside its own place while it works; Sutra finds out after it ends and asks you.
- When a step is tried again, one model call counts as one credit; your dollar limit is the number that holds.
- Sutra checks and counts secret-like words in what the steps send to the model programs, it does not change them, as with any run. It does nothing about what a tool fetches or sends. The tool inputs are emptied from a step's record when it ends.
- Keeping steps apart works among the steps of projects; a normal task of another team can still change the same folder.
