# herdr-cooperate

Coordinate coding agents working in a shared repository through [herdr](https://github.com/).

The `herdr-cooperate` skill provides a workflow for declaring task and file ownership, checking live peer state, coordinating shared Git operations, and recording handoffs. The bundled `scripts/coordinate.py` helper publishes declarations and reports relevant changes. It does not edit files or run Git mutations.

## Use

Read [`SKILL.md`](SKILL.md) and follow its workflow when coordinating work. The helper requires a live herdr connection and a verified pane ID (or `HERDR_PANE_ID`):

```sh
python3 scripts/coordinate.py \
  --task 'Describe the task' \
  --file path/to/file \
  --model unknown \
  --effort unknown
```

Run the helper without arguments to check the current coordination state. See `python3 scripts/coordinate.py --help` for all options.

## Tests

Run the helper's unit tests with:

```sh
python3 -m unittest discover -s scripts -p 'test_*.py'
```

## License

This project is licensed under the MIT License. See [`LICENSE`](LICENSE).
