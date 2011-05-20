# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Utility classes for parsing Debian tag files."""

__all__ = [
    'TagFileParseError',
    'parse_tagfile',
    'parse_tagfile_content'
    ]


import re


class TagFileParseError(Exception):
    """This exception is raised if parse_changes encounters nastiness"""
    pass

re_single_line_field = re.compile(r"^(\S*)\s*:\s*(.*)")
re_multi_line_field = re.compile(r"^(\s.*)")


def parse_tagfile_content(content, dsc_whitespace_rules=0, filename=None):
    """Parses a tag file and returns a dictionary where each field is a key.

    The mandatory first argument is the contents of the tag file as a
    string.

    dsc_whitespace_rules is an optional boolean argument which defaults
    to off.  If true, it turns on strict format checking to avoid
    allowing in source packages which are unextracable by the
    inappropriately fragile dpkg-source.

    The rules are:

    o The PGP header consists of '-----BEGIN PGP SIGNED MESSAGE-----'
      followed by any PGP header data and must end with a blank line.

    o The data section must end with a blank line and must be followed by
      '-----BEGIN PGP SIGNATURE-----'.
    """
    lines = content.splitlines(True)

    error = ""

    changes = {}

    # Reindex by line number so we can easily verify the format of
    # .dsc files...
    index = 0
    indexed_lines = {}
    for line in lines:
        index += 1
        indexed_lines[index] = line[:-1]

    inside_signature = 0

    num_of_lines = len(indexed_lines.keys())
    index = 0
    first_value_for_newline_delimited_field = False
    more_values_can_follow = False
    while index < num_of_lines:
        index += 1
        line = indexed_lines[index]

        # If the line is empty and we're not strictly enforcing whitespace
        # rules, then just continue.
        # If we're enforcing the rules, then check those rules, and maybe
        # complain.
        if line == "":
            if dsc_whitespace_rules:
                index += 1
                if index > num_of_lines:
                    raise TagFileParseError(
                        "%s: invalid .dsc file at line %d" % (
                            filename, index))
                line = indexed_lines[index]
                if not line.startswith("-----BEGIN PGP SIGNATURE"):
                    raise TagFileParseError(
                        "%s: invalid .dsc file at line %d -- "
                        "expected PGP signature; got '%s'" % (
                            filename, index,line))
                inside_signature = 0
                break
            else:
                continue
        if line.startswith("-----BEGIN PGP SIGNATURE"):
            break

        # If we're at the start of a signed section, then consume the
        # signature information, and remember that we're inside the signed
        # data.
        if line.startswith("-----BEGIN PGP SIGNED MESSAGE"):
            inside_signature = 1
            if dsc_whitespace_rules:
                while index < num_of_lines and line != "":
                    index += 1
                    line = indexed_lines[index]
            continue
        slf = re_single_line_field.match(line)
        if slf:
            field = slf.groups()[0]
            changes[field] = slf.groups()[1]

            # If there is no value on this line, we assume this is
            # the first line of a multiline field, such as the 'files'
            # field.
            if changes[field] == '':
                first_value_for_newline_delimited_field = True

            # Either way, more values for this field could follow
            # on the next line.
            more_values_can_follow = True
            continue
        if line.rstrip() == " .":
            changes[field] += '\n' + line
            continue
        mlf = re_multi_line_field.match(line)
        if mlf:
            if more_values_can_follow is False:
                raise TagFileParseError(
                    "%s: could not parse .changes file line %d: '%s'\n"
                    " [Multi-line field continuing on from nothing?]" % (
                        filename, index,line))

            # XXX Michael Nelson 20091001 bug=440014
            # Is there any reason why we're not simply using
            # apt_pkg.ParseTagFile instead of this looong function.
            # If we can get rid of this code that is trying to mimic
            # what ParseTagFile does out of the box, it would be a good
            # thing.

            # The first value for a newline delimited field, such as
            # the 'files' field, has its leading spaces stripped. Other
            # fields (such as a 'binary' field spanning multiple lines)
            # should *not* be l-stripped of their leading spaces otherwise
            # they will be re-parsed incorrectly by apt_get.ParseTagFiles()
            # (for example, from a Source index).
            value = mlf.groups()[0]
            if first_value_for_newline_delimited_field:
                changes[field] = value.lstrip()
            else:
                changes[field] += '\n' + value

            first_value_for_newline_delimited_field = False
            continue
        error += line

    if dsc_whitespace_rules and inside_signature:
        raise TagFileParseError(
            "%s: invalid .dsc format at line %d" % (filename, index))

    changes["filecontents"] = "".join(lines)

    if error:
        raise TagFileParseError(
            "%s: unable to parse .changes file: %s" % (filename, error))

    return changes


def parse_tagfile(filename, dsc_whitespace_rules=0):
    """Parses a tag file and returns a dictionary where each field is a key.

    The mandatory first argument is the filename of the tag file, and
    the contents of that file is passed on to parse_tagfile_content.

    See parse_tagfile_content's docstring for description of the
    dsc_whitespace_rules argument.
    """
    changes_in = open(filename, "r")
    content = changes_in.read()
    changes_in.close()
    if not content:
        raise TagFileParseError( "%s: empty file" % filename )
    return parse_tagfile_content(
        content, dsc_whitespace_rules=dsc_whitespace_rules,
        filename=filename)

