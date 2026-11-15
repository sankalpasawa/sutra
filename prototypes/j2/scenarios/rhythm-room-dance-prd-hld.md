# Rhythm Room Dance Studio: PRD and HLD only, from selected workflows of a run template

A brief for a partial run: only the PRD and HLD workflows of the run template
**Still Point Yoga: PRD, HLD and LLD** (`still-point-yoga-prd-hld-and-lld`, made from a live run). Every fact below is made up.

| | |
|---|---|
| Run template | `still-point-yoga-prd-hld-and-lld`, selected workflows W-1 to W-12 of 17 |
| Selected | W-1 to W-6 (PRD: Problem, Users, Goals, Requirements, Success metrics, Out of scope) and W-7 to W-12 (HLD: Purpose and scope, Pages, Components, Data flow, Hosting and deployment, Risks) |
| Not selected | W-13 to W-17 (LLD) |
| Start page | `/?view=simple&template=still-point-yoga-prd-hld-and-lld&workflows=W-1,W-2,W-3,W-4,W-5,W-6,W-7,W-8,W-9,W-10,W-11,W-12` |
| Flags | `J2_RUN_TEMPLATES=1 J2_TEMPLATE_LIBRARY=1`, and `J2_LIBRARY_DIR` set to a copy of `library/` |
| Asked for | PRD and HLD only; no LLD, no website |
| Success | about 0 templates created; 12 workflows, every one from the template |

Both stages are selected whole, so each document is complete and is checked by Audit as usual. W-9 (HLD
Components) depends on W-4 (PRD Requirements), which is in the selection.

## Brief

Write the PRD and the HLD only, for a one-page website for Rhythm Room Dance Studio, a dance studio. Do not
write an LLD and do not build the website.

Studio name: Rhythm Room Dance Studio
Address: 3rd Floor, 8 Sample Lane, Bengaluru 560001 (shown as text, no embedded map)

Weekly classes (day, time, class, price in rupees):
- Monday 6:00 pm Salsa Beginners 700
- Wednesday 7:00 pm Bollywood Basics 600
- Thursday 6:30 pm Contemporary 750
- Saturday 10:00 am Kids Hip Hop 500
- Sunday 11:00 am Open Floor 400

The page has a class booking form with the fields name, email, class and preferred date. The form sends the
booking to hello@rhythmroom.example.

Payment is made at the studio. No online payment is taken.

Do not show a phone number. Do not show teacher names. The page must work on phones. Do not make any other
detail up.

## If the team asks

- Budget or decision questions: answer `1` when option 1 is "add credits and keep going". Never answer
  "finish" or "don't".
- A fact that is not above: say it is not available and must be left out.
