You are running the **merge check** for {{BRAND}}'s niche: the gate that stops phrases being merged
by shared topic instead of shared pain. This is the most important quality step in the method. Do it
honestly, phrase by phrase. Its record is the evidence that it happened.

## The candidate tensions
A first-pass grouping. Some of these are over-merged topic blobs.

{{TENSIONS}}

## For EACH candidate, run the check

1. **Write the one shared-pain sentence.** State the specific pain behind ALL of its phrases:
   "[who] [is hurt because / can't / is dragged through] [one specific thing]".
2. **Test every phrase against that sentence, one at a time.** Does this exact sentence describe the
   pain behind THIS phrase, specifically and not loosely? Every phrase a clear yes is a **PASS**. If
   you had to stretch the sentence to fit any phrase, it is a **SPLIT**.
3. **Vague-predicate tripwire.** If the sentence only holds together because it leans on a
   stretch-word (doesn't work, is broken, is a mess, is frustrating, is flawed, barely predicts, is
   unfair, is outdated, has problems with, struggles with, is bad at) it is a topic, not a tension.
   SPLIT it.
4. **Size alarm.** A candidate with more than {{MAX_PHRASES}} phrases is presumed merged by topic, so
   SPLIT it, unless one specific shared-pain sentence honestly covers all of them. If it does, say so
   in `shared_pain` and return PASS.
5. **On SPLIT**, re-derive the tensions actually hiding inside: for each, its own specific shared-pain
   sentence and exactly which phrases belong to it. A phrase that fits none of them goes to `orphans`
   rather than being forced in.

## Return

JSON only. On PASS, `result_tensions` holds the single tension unchanged. On SPLIT it holds the two
or more correct ones. `per_phrase` is the per-phrase evidence and becomes the audit file.

{"checked": [
  {"original": "<the candidate tension sentence, copied>",
   "verdict": "PASS" | "SPLIT",
   "shared_pain": "<the one sentence you wrote in step 1>",
   "per_phrase": [{"phrase": "<phrase>", "fits": true}],
   "result_tensions": [{"tension": "<final specific shared-pain sentence>",
                        "phrases": [{"phrase": "<phrase>", "post_ids": ["<id>"]}]}]}],
 "orphans": [{"phrase": "<phrase>", "post_ids": ["<id>"]}]}
