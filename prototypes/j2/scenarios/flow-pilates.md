# Flow Pilates Studio: documents and website, no run template chosen (auto-reuse)

A brief for a new run that starts WITHOUT a run template, with `J2_AUTO_REUSE=1`. After Identity writes the first
charter, code scores every run template in the library against it and either picks the most similar one ("Using
similar run template <name> (match 0.xx)") or starts from scratch ("No similar run template (best <name> 0.xx)").
Section templates are adapted from the nearest existing ones before a new one is created. Every fact below is made up.

| | |
|---|---|
| Run template | none chosen: the run picks one itself, or none |
| Start page | `/?view=simple` |
| Flags | `STUDIO_PROVIDER=claude-cli J2_AUTO_REUSE=1 J2_BUDGET=500`, and `J2_LIBRARY_DIR` set to a copy of `library/` |
| Asked for | PRD, HLD, LLD and a one-page website |
| Success | a similar run template is picked by itself; about 0 templates created for the documents; website sections adapted, not created, where the library has a section template |

## Brief

Write the PRD, HLD and LLD, then build a one-page website, for Flow Pilates Studio, a pilates studio.

Studio name: Flow Pilates Studio
Address: Unit 3, 9 Sample Lane, Pune 411004 (shown as text, no embedded map)

Weekly classes (day, time, class, price in rupees):
- Monday 7:00 am Mat Basics 500
- Tuesday 6:30 pm Reformer Flow 800
- Wednesday 7:00 am Core Strength 600
- Friday 6:30 pm Stretch and Release 550
- Saturday 9:00 am Weekend Mat Class 500

The page has a class booking form with the fields name, email, class and preferred date. The form sends the
booking to bookings@flowpilates.example.

Payment is made at the studio. No online payment is taken.

Do not show a phone number. Do not show teacher names. The page must work on phones. Do not make any other
detail up.

## If the team asks

- Budget or decision questions: answer `1` when option 1 is "add credits and keep going". Never answer
  "finish" or "don't".
- A fact that is not above: say it is not available and must be left out.
