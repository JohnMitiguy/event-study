"""Shared settings for the hypothesis (property-based) tests.

hypothesis generates many random inputs per test and, when one fails,
shrinks it to a small example and prints it. It keeps failing examples (and
some caches) in a .hypothesis/ folder in the project root and replays them
first on the next run. That folder has its own .gitignore, so git ignores it.

- deadline=None: no per-example time limit. The first call builds the NYSE
  calendar and file writes on Windows can be slow, which would otherwise
  give flaky "took too long" failures.
- print_blob=True: a failure also prints a @reproduce_failure line that
  replays exactly that example.
"""

from hypothesis import settings

settings.register_profile("project", deadline=None, print_blob=True)
settings.load_profile("project")
