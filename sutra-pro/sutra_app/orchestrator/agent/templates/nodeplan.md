STEPS OF THE PROJECT:
{steps}
OWNER REQUEST:
{message}
For each step, say what it asks for beyond its team's defaults. `scope`: the paths of the owner's working folder this step would change (at most 5, relative, written with `/`); leave it empty when the step changes no file in the folder or truly needs the whole folder. `needs`: `sutra` when the step must read the app's own data, `github` when it must read GitHub; leave it empty for everything else. These are requests only: Sutra's rules and the owner decide. Do not invent paths: name a path only when the request names it or it is plainly implied. Use only the refs listed in STEPS OF THE PROJECT.
SCHEMA:
{schema}
Answer with ONE JSON object that matches SCHEMA.
