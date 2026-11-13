# Northwind Archive file copier

Copies every file of one folder into another, keeping sub-folders.

    python3 copy_files.py <from> <to>

- It never deletes a file.
- It never writes outside the folder it copies to.
- A file already there with the same bytes is left alone.

Test: `python3 test_copy_files.py` prints `ok`.
