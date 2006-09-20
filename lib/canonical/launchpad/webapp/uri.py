# Copyright 2006 Canonical Ltd.  All rights reserved.

"""Functions for working with generic syntax URIs."""

__metaclass__ = type
__all__ = ['Uri', 'InvalidUriError']

import re


# Regular expressions adapted from the ABNF in the RFC

scheme_re = r"(?P<scheme>[a-z][-a-z0-9+.]*)"

userinfo_re = r"(?P<userinfo>(?:[-a-z0-9._~!$&\'()*+,;=:]|%[0-9a-f]{2})*)"
# the following regular expression doesn't quite match the RFC, but should
# be good enough.
host_re = (r"(?P<host>[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}|"
           r"(?:[-a-z0-9._~!$&\'()*+,;=]|%[0-9a-f]{2})*|"
           r"\[[0-9a-z:.]+\])")
port_re = r"(?P<port>[0-9]*)"

authority_re = r"(?P<authority>(?:%s@)?%s(?::%s)?)" % (
    userinfo_re, host_re, port_re)

path_abempty_re = r"(?:/(?:[-a-z0-9._~!$&\'()*+,;=:@]|%[0-9a-f]{2})*)*"
path_noscheme_re = (r"(?:[-a-z0-9._~!$&\'()*+,;=@]|%[0-9a-f]{2})+"
                    r"(?:/(?:[-a-z0-9._~!$&\'()*+,;=:@]|%[0-9a-f]{2})*)*")
path_rootless_re = (r"(?:[-a-z0-9._~!$&\'()*+,;=:@]|%[0-9a-f]{2})+"
                    r"(?:/(?:[-a-z0-9._~!$&\'()*+,;=:@]|%[0-9a-f]{2})*)*")
path_absolute_re = r"/(?:%s)?" % path_rootless_re
path_empty_re = r""

hier_part_re = r"(?P<hierpart>//%s%s|%s|%s|%s)" % (
    authority_re, path_abempty_re, path_absolute_re, path_rootless_re,
    path_empty_re)

relative_part_re = r"(?P<relativepart>//%s%s|%s|%s|%s)" % (
    authority_re, path_abempty_re, path_absolute_re, path_noscheme_re,
    path_empty_re)

query_re = r"(?P<query>(?:[-a-z0-9._~!$&\'()*+,;=:@/?]|%[0-9a-f]{2})*)"
fragment_re = r"(?P<fragment>(?:[-a-z0-9._~!$&\'()*+,;=:@/?]|%[0-9a-f]{2})*)"

uri_re = r"%s:%s(?:\?%s)?(?:#%s)?$" % (
    scheme_re, hier_part_re, query_re, fragment_re)

relative_ref_re = r"%s(?:\?%s)?(?:#%s)?$" % (
    relative_part_re, query_re, fragment_re)

uri_pat = re.compile(uri_re, re.IGNORECASE)
relative_ref_pat = re.compile(relative_ref_re, re.IGNORECASE)

def merge(basepath, relpath, has_authority):
    """Merge two URI path components.

    Follows rules specified in Section 5.2.3 of RFC 3986.
    """
    if has_authority and basepath == '':
        return '/' + relpath
    slash = basepath.rfind('/')
    return basepath[:slash+1] + relpath

def remove_dot_segments(path):
    """Remove '.' and '..' segments from a URI path.

    Follows the rules specified in Section 5.2.4 of RFC 3986.
    """
    output = []
    while path:
        if path.startswith('../'):
            path = path[3:]
        elif path.startswith('./'):
            path = path[2:]
        elif path.startswith('/./') or path == '/.':
            path = '/' + path[3:]
        elif path.startswith('/../') or path == '/..':
            path = '/' + path[4:]
            if len(output) > 0:
                del output[-1]
        elif path in ['.', '..']:
            path = ''
        else:
            if path.startswith('/'):
                slash = path.find('/', 1)
            else:
                slash = path.find('/')
            if slash < 0:
                slash = len(path)
            output.append(path[:slash])
            path = path[slash:]
    return ''.join(output)

def normalise_unreserved(s):
    """Return a version of 's' where no unreserved characters are encoded.

    Unreserved characters are defined in Section 2.3 of RFC 3986.

    Percent encoded sequences are normalised to upper case.
    """
    res = s.split('%')
    unreserved = ('ABCDEFGHIJKLMNOPQRSTUVWXYZ'
                  'abcdefghijklmnopqrstuvwxyz'
                  '0123456789-._~')
    for i, item in enumerate(res):
        if i == 0:
            continue
        try:
            ch = int(item[:2], 16)
        except ValueError:
            continue
        if chr(ch) in unreserved:
            res[i] = chr(ch) + item[2:]
        else:
            res[i] = '%%%02X%s' % (ch, item[2:])
    return ''.join(res)


class InvalidUriError(Exception):
    """Invalid URI"""


class Uri:
    """A class that represents a URI.

    This class can represent arbitrary URIs that conform to the
    generic syntax described in RFC 3986.
    """

    def __init__(self, uri=None, scheme=None, userinfo=None, host=None,
                 port=None, path=None, query=None, fragment=None):
        """Create a Uri instance.

        Can be called with either a string URI or the component parts
        of the URI as keyword arguments.
        """
        assert (uri is not None and scheme is None and userinfo is None and
                host is None and port is None and path is None and
                query is None and fragment is None) or uri is None, (
            "Uri() must be called with a single string argument or "
            "with URI components given as keyword arguments.")

        if uri is not None:
            if isinstance(uri, unicode):
                uri = uri.encode('ASCII')
            match = uri_pat.match(uri)
            if match is None:
                raise InvalidUriError('%s is not a valid URI' % uri)
            self.scheme = match.group('scheme')
            self.userinfo = match.group('userinfo')
            self.host = match.group('host')
            self.port = match.group('port')
            hierpart = match.group('hierpart')
            authority = match.group('authority')
            if authority is None:
                self.path = hierpart
            else:
                # Skip past the //authority part
                self.path = hierpart[2+len(authority):]
            self.query = match.group('query')
            self.fragment = match.group('fragment')
        else:
            if scheme is None:
                raise InvalidUriError('URIs must have a scheme')
            if host is None and (userinfo is not None or port is not None):
                raise InvalidUriError(
                    'host must be given if userinfo or port are')
            if path is None:
                raise InvalidUriError('URIs must have a path')
            self.scheme = scheme
            self.userinfo = userinfo
            self.host = host
            self.port = port
            self.path = path
            self.query = query
            self.fragment = fragment

        # Basic normalisation:
        self.scheme = self.scheme.lower()
        if self.userinfo is not None:
            self.userinfo = normalise_unreserved(self.userinfo)
        if self.host is not None:
            self.host = normalise_unreserved(self.host.lower())
        self.path = normalise_unreserved(remove_dot_segments(self.path))
        if self.query is not None:
            self.query = normalise_unreserved(self.query)
        if self.fragment is not None:
            self.fragment = normalise_unreserved(self.fragment)

    @property
    def authority(self):
        """The authority part of the URI"""
        if self.host is None:
            return None
        authority = self.host
        if self.userinfo is not None:
            authority = '%s@%s' % (self.userinfo, authority)
        if self.port is not None:
            authority = '%s:%s' % (authority, self.port)
        return authority

    @property
    def hier_part(self):
        """The hierarchical part of the URI"""
        authority = self.authority
        if authority is None:
            return self.path
        else:
            return '//%s%s' % (authority, self.path)

    def __str__(self):
        uri = '%s:%s' % (self.scheme, self.hier_part)
        if self.query is not None:
            uri += '?%s' % self.query
        if self.fragment is not None:
            uri += '#%s' % self.fragment
        return uri

    def __repr__(self):
        return '%s(%r)' % (self.__class__.__name__, str(self))

    def replace(self, **parts):
        """Replace one or more parts of the URI, returning the result."""
        if not parts:
            return self
        baseparts = dict(
            scheme=self.scheme,
            userinfo=self.userinfo,
            host=self.host,
            port=self.port,
            path=self.path,
            query=self.query,
            fragment=self.fragment)
        baseparts.update(parts)
        return self.__class__(**baseparts)
        
    def resolve(self, reference):
        """Resolve the given URI reference relative to this URI.

        Uses the rules from Section 5.2 of RFC 3986 to resolve the new
        URI.
        """
        # If the reference is a full URI, then return it as is.
        try:
            return self.__class__(reference)
        except InvalidUriError:
            pass
        
        match = relative_ref_pat.match(reference)
        if match is None:
            raise InvalidUriError("Invalid relative reference")

        parts = dict(scheme=self.scheme)
        authority = match.group('authority')
        if authority is not None:
            parts['userinfo'] = match.group('userinfo')
            parts['host'] = match.group('host')
            parts['port'] = match.group('port')
            # Skip over the //authority part
            parts['path'] = remove_dot_segments(
                match.group('relativepart')[2+len(authority):])
            parts['query'] = match.group('query')
        else:
            path = match.group('relativepart')
            query = match.group('query')
            if path == '':
                parts['path'] = self.path
                if query is not None:
                    parts['query'] = query
                else:
                    parts['query'] = self.query
            else:
                if path.startswith('/'):
                    parts['path'] = remove_dot_segments(path)
                else:
                    parts['path'] = merge(self.path, path,
                                          has_authority=self.host is not None)
                    parts['path'] = remove_dot_segments(parts['path'])
                parts['query'] = query
            parts['userinfo'] = self.userinfo
            parts['host'] = self.host
            parts['port'] = self.port
        parts['fragment'] = match.group('fragment')

        return self.__class__(**parts)

    def append(self, path):
        """Append the given path to this URI.

        The path must not start with a slash, but a slash is added to
        base URI (before appending the path), in case it doesn't end
        with a slash.
        """
        assert not path.startswith('/')
        basepath = self.path
        if not basepath.endswith('/'):
            basepath += '/'
        return self.replace(path=basepath+path, query=None, fragment=None)

    def contains(self, other):
        """Returns True if the URI 'other' is contained by this one."""
        if (self.scheme != other.scheme or
            self.authority != other.authority):
            return False
        if self.path == other.path:
            return True
        basepath = self.path
        if not basepath.endswith('/'):
            basepath += '/'
        return other.path.startswith(basepath)
