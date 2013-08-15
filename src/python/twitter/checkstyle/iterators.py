"""
File iterators for determining over which files checkstyle should be run.
"""

from difflib import SequenceMatcher
from functools import partial
import os

from twitter.common.dirutil.fileset import Fileset

try:
  from git import Diff, Repo
  HAS_GIT = True
except ImportError:
  HAS_GIT = False


def path_iterator(args, options):
  for path in args:
    if os.path.isdir(path):
      for filename in Fileset.rglobs('*.py', root=path)():
        yield os.path.join(path, filename), None
    elif os.path.isfile(path):
      yield path, None


def read_blob(blob):
  """Helper to read a blob which may possibly be unstaged and in the working tree."""
  if blob.hexsha != Diff.NULL_HEX_SHA:
    return blob.data_stream.read()
  else:
    with open(blob.path) as fp:
      return fp.read()


def diff_lines(old, new):
  matcher = SequenceMatcher(None, read_blob(old).splitlines(1), read_blob(new).splitlines(1))
  # From get_opcodes documentation:
  # |      'replace':  a[i1:i2] should be replaced by b[j1:j2]
  # |      'delete':   a[i1:i2] should be deleted.
  # |                  Note that j1==j2 in this case.
  # |      'insert':   b[j1:j2] should be inserted at a[i1:i1].
  # |                  Note that i1==i2 in this case.
  # |      'equal':    a[i1:i2] == b[j1:j2]
  for opcode in matcher.get_opcodes():
    match_type, start_line_old, stop_line_old, start_line_new, stop_line_new = opcode
    if match_type in ('insert', 'replace'):
      for lineno in range(start_line_new, stop_line_new):
        # Line numbers are off-by-one in PythonFile
        yield lineno + 1


def tuple_from_diff(diff):
  """
    From GitPython:

    It contains two sides a and b of the diff, members are prefixed with
    "a" and "b" respectively to inidcate that.

    Diffs keep information about the changed blob objects, the file mode, renames,
    deletions and new files.

    There are a few cases where None has to be expected as member variable value:

        ``New File``::

            a_mode is None
            a_blob is None

        ``Deleted File``::

            b_mode is None
            b_blob is None
  """
  # New file => check all
  if diff.b_blob and not diff.a_blob and diff.b_blob.path.endswith('.py'):
    return diff.b_blob.path, None

  # Check diff lines between two
  if diff.a_blob and diff.b_blob and diff.b_blob.path.endswith('.py'):
    paths = diff.b_blob.path.split('\t')  # Handle rename, which are "old.py\tnew.py"
    paths = paths[1] if len(paths) != 1 else paths[0]
    return paths, partial(diff_lines, diff.a_blob, diff.b_blob)


def git_iterator(args, options):
  if not HAS_GIT:
    raise ValueError('Git has not been enabled for this checkstyle library!')

  repo = Repo()
  diff_commit = repo.rev_parse(options.diff or 'master')
  for filename, line_filter in filter(None, map(tuple_from_diff, diff_commit.diff(None))):
    yield filename, line_filter
