# Release notes

`scripts/release.py` needs one file here for each release, `X.Y.Z.md`, committed with the version bump. The script puts its text in front of the release text the
workflows write (the download table), so write it for the person who downloads the app: what is new or fixed, in a few plain lines, no jargon, no names.

    ### What is new in 0.7.0

    - **One thing you can now do.** One sentence on what it is for.
    - **Another.** ...

A release without notes is possible (`--no-notes`) and carries only the download table.
