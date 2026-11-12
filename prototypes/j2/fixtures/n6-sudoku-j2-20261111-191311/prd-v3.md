# Cozy Sudoku

## Problem

The cluttered Sudoku sites out there show ads and ask players to sign up. For a casual player who wants a quick game on a phone, this makes the sites unfriendly. Because the experience is unfriendly, these players have little reason to come back.

Cozy Sudoku is a friendly single-page Sudoku game that removes these problems. It needs no sign-up, shows no ads, and is built to fit a phone screen. It also offers difficulty levels and beginner help that does not spoil the puzzle.

## Users

Cozy Sudoku is for casual players who play a quick game on their phone, for example on a commute. This includes beginners. There are two user groups.

- **Casual commuter players** play a quick game on their phone, choose a difficulty level, and come back for another game.
- **Beginners** use hints and mistake checking to learn without seeing the answer.

## Goals

- **G1**: A player can start and finish a puzzle in Cozy Sudoku with no sign-up and no ads.
- **G2**: Cozy Sudoku offers three difficulty levels, Easy, Medium and Hard, and every level offers a puzzle with exactly one solution.
- **G3**: A beginner can get help in Cozy Sudoku without the answer being shown.
- **G4**: A returning player can resume an unfinished game.
- **G5**: Cozy Sudoku feels friendly and uncluttered, and it works on a phone screen as small as 360px wide.
- **G6**: Casual players enjoy Cozy Sudoku enough to come back for another game.

## Requirements

1. **R1**: Cozy Sudoku offers three difficulty levels named Easy, Medium and Hard, and the player picks one before a puzzle starts. (Goals: G2, G6)
2. **R2**: Every puzzle at Easy, Medium and Hard has exactly one solution. (Goals: G2)
3. **R3**: Casual commuter players can start a puzzle, play it and finish it on their phone, and the game shows a short win message when the puzzle is solved. (Goals: G1, G5, G6)
4. **R4**: After the win message, casual commuter players can start another puzzle and choose a difficulty level again. (Goals: G2, G6)
5. **R5**: A player can switch on pencil notes and write small candidate digits in a cell without placing a final digit. (Goals: G3)
6. **R6**: A player can undo moves, and each undo takes back the last move made. (Goals: G3, G5)
7. **R7**: Mistake checking is gentle: it marks a wrong entry without ending the game and without showing the correct digit. (Goals: G3, G5)
8. **R8**: Beginners can ask for a hint that points toward the next step, and a hint never shows the digit that belongs in a cell. (Goals: G3)
9. **R9**: Beginners can use hints and mistake checking together to learn how a puzzle is solved without seeing the answer. (Goals: G3)
10. **R10**: The game saves progress automatically, with no save button, so a returning player can resume an unfinished game. (Goals: G4, G6)
11. **R11**: Cells and buttons are large tap targets, and the whole game fits a phone screen as small as 360px wide with no horizontal scrolling. (Goals: G5)
12. **R12**: The look is friendly and uncluttered: the screen shows the board, the controls and short messages, and nothing else competes for attention. (Goals: G5, G6)
13. **R13**: Cozy Sudoku has no sign-up and no ads: a player never has to create an account or log in, and no ad appears at any point. (Goals: G1, G5)
14. **R14**: Cozy Sudoku is delivered as a single file of plain HTML, CSS and JavaScript with no build step. (Goals: G1, G5)

## Success metrics

Each metric is checked by playing the product or reading its file. No numeric targets were given, so each metric is a pass or fail check (measurement window not set).

| Goal | Metric |
| --- | --- |
| G1 | A player can open Cozy Sudoku, start a puzzle and finish it with no sign-up screen, no account prompt and no ad shown at any step (measurement window not set). |
| G2 | Easy, Medium and Hard can each be chosen, and a solver check finds exactly one solution for every puzzle offered at each level (measurement window not set). |
| G3 | A beginner can use pencil notes, undo, mistake checking and a hint, and at no point does the game display the digit that belongs in a cell (measurement window not set). |
| G4 | After a player leaves an unfinished game and opens Cozy Sudoku again, the same board with the same entries and notes is shown and can be resumed (measurement window not set). |
| G5 | At a screen width of 360px the board and controls show with no horizontal scrolling, the cells and buttons can be tapped, and the screen shows no clutter beyond the board, controls and messages (measurement window not set). |
| G6 | After finishing a puzzle, a player sees the short win message and can start another puzzle straight from it (measurement window not set). |

## Out of scope

Cozy Sudoku will not include the following in this version:

- Sign-up, accounts or login of any kind.
- Ads of any kind.
- A build step, or more than a single file.
- Hints, notes or mistake checks that show the answer to a cell.
- Assumption: online multiplayer, leaderboards and daily challenges.
- Assumption: syncing saved games between devices.
- Assumption: sound, music and in-game purchases.

## Assumptions to confirm

- online multiplayer, leaderboards and daily challenges.
- syncing saved games between devices.
- sound, music and in-game purchases.
