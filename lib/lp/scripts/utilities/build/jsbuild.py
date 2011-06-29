"""build.py - Minifies and creates the JS build directory."""

__metaclass__ = type
__all__ = []


import optparse
import os
import re
import shutil
import sys

from glob import glob

import cssutils
import pkg_resources

HERE = os.path.dirname(__file__)
BUILD_DIR = os.path.normpath(os.path.join(HERE, '..', '..', '..', 'build'))
DEFAULT_SRC_DIR = os.path.normpath(os.path.join(HERE, '..', '..', '..', 'app', 'javascript'))
PKG_SRC_DIR = pkg_resources.resource_filename(
    pkg_resources.Requirement.parse("lazr-js"), "lazrjs")

ESCAPE_STAR_PROPERTY_RE = re.compile(r'\*([a-zA-Z0-9_-]+):')
UNESCAPE_STAR_PROPERTY_RE = re.compile(r'([a-zA-Z0-9_-]+)_ie_star_hack:')
URL_RE = re.compile("url\([ \"\']*([^ \"\']+)[ \"\']*\)")

from jsmin import JavascriptMinify


def relative_path(from_file, to_file):
    """Return the relative path between from_file and to_file."""
    dir_from, base_from = os.path.split(from_file)
    dir_to, base_to = os.path.split(to_file)
    path = os.path.relpath(dir_to, dir_from)
    if path == ".":
        return base_to
    return os.path.join(path, base_to)


class ComboFile:
    """A file made up of several combined files.

    It offers support for detecting if the file needs updating and updating it
    from it source files.
    """

    def __init__(self, src_files, target_file):
        self.src_files = src_files
        self.target_file = target_file

    def needs_update(self):
        """Return True when the file needs to be updated.

        This is usually because the target file doesn't exist yet or because
        one of the source file was modified.
        """
        # If the target file doesn't exist, we need updating!
        if not os.path.exists(self.target_file):
            return True

        # Check if the target file was modified after all the src files.
        target_mtime = os.stat(self.target_file).st_mtime
        for src_file in self.src_files:
            if os.stat(src_file).st_mtime > target_mtime:
                return True
        else:
            return False

    def log(self, msg):
        sys.stdout.write(msg + '\n')

    def update(self):
        """Update the file from its source files."""
        target_fh = open(self.target_file, 'w')
        try:
            for src_file in self.src_files:
                self.log("Processing '%s'" % os.path.basename(src_file))
                target_fh.write(self.get_file_header(src_file))
                fh = open(src_file)
                content = fh.read()
                fh.close()
                try:
                    target_fh.write(self.filter_file_content(content, src_file))
                except Exception:
                    os.remove(self.target_file)
                    raise
        finally:
            target_fh.close()

    def get_comment(self, msg):
        """Return a string wrapped in a comment to be include in the output.

        Can be used to help annotate the output file.
        """
        return ''

    def get_file_header(self, path):
        """Return a string to include before outputting a file.

        Can be used by subclasses to output a file reference in the combined
        file. Default implementation returns nothing.
        """
        return ''

    def filter_file_content(self, file_content, path):
        """Hook to process the file content before being combined."""
        return file_content


class JSComboFile(ComboFile):
    """ComboFile for JavaScript files.

    Outputs the filename before each combined file and make sure that
    each file content has a new line.
    """

    def get_comment(self, msg):
        return "// %s\n" % msg

    def get_file_header(self, path):
        return self.get_comment(relative_path(self.target_file, path))

    def filter_file_content(self, file_content, path):
        return file_content + '\n'


class CSSComboFile(ComboFile):
    """FileCombiner for CSS files.

    It uses the cssutils.CSSParser to convert all url() instances
    to the new location, and minify the result.
    """

    def __init__(self, src_files, target_file, resource_prefix="",
                 minify=True, rewrite_urls=True):
        super(CSSComboFile, self).__init__(src_files, target_file)
        self.resource_prefix = resource_prefix.rstrip("/")
        self.minify = minify
        self.rewrite_urls = rewrite_urls

    def get_comment(self, msg):
        return "/* %s */\n" % msg

    def get_file_header(self, path):
        return self.get_comment(relative_path(self.target_file, path))

    def filter_file_content(self, file_content, path):
        """URLs are made relative to the target and the CSS is minified."""
        if self.rewrite_urls:
            src_dir = os.path.dirname(path)
            relative_parts = relative_path(self.target_file, src_dir).split(
                os.path.sep)
            def fix_relative_url(match):
                url = match.group(1)
                # Don't modify absolute URLs or 'data:' urls.
                if (url.startswith("http") or
                    url.startswith("/") or
                    url.startswith("data:")):
                    return match.group(0)
                parts = relative_parts + url.split("/")
                result = []
                for part in parts:
                    if part == ".." and result and result[-1] != "..":
                        result.pop(-1)
                        continue
                    result.append(part)
                return "url(%s)" % "/".join(
                    filter(None, [self.resource_prefix] + result))
            file_content = URL_RE.sub(fix_relative_url, file_content)

        if self.minify:
            old_serializer = cssutils.ser
            cssutils.setSerializer(cssutils.serialize.CSSSerializer())
            try:
                cssutils.ser.prefs.useMinified()

                stylesheet = ESCAPE_STAR_PROPERTY_RE.sub(
                    r'\1_ie_star_hack:', file_content)
                parser = cssutils.CSSParser(raiseExceptions=True)
                css = parser.parseString(stylesheet)
                stylesheet = UNESCAPE_STAR_PROPERTY_RE.sub(
                    r'*\1:', css.cssText)
                return stylesheet + "\n"
            finally:
                cssutils.setSerializer(old_serializer)
        return file_content + "\n"


class Builder:

    def __init__(self, name='lazr', build_dir=BUILD_DIR, src_dir=PKG_SRC_DIR,
                 extra_files=None, exclude_regex='', file_type='raw'):
        """Create a new Builder.

        :param name: The name of the package we are building. This will
            be used to compute the standalone JS and CSS files.
        :param build_dir: The directory containing the build tree.
        :param src_dir: The directory containing the source files.
        :param extra_files: List of files that should be bundled in the
            standalone file.
        :param exclude_regex: A regex that will exclude file paths from the
            final rollup.  -min and -debug versions will still be built.
        :param file_type: A string specifying which type of files to include
            in the final rollup.  Default is to use the raw, unmodified JS
            file.  Possible values are 'raw', 'min', and 'debug'.  File types
            are identified by their basename suffix: foo.js, foo-min.js,
            foo-debug.js, etc.
        """
        self.name = name
        self.build_dir = build_dir
        self.src_dir = src_dir
        # We need to support the case where this is being invoked directly
        # from source rather than a package. If this is the case, the package
        # src directory won't exist.
        if not os.path.exists(src_dir):
            self.src_dir = DEFAULT_SRC_DIR
        self.built_files = []
        self.skins = {}
        if extra_files is None:
            self.extra_files = []
        else:
            self.extra_files = extra_files

        self.exclusion_regex = exclude_regex
        self.file_type = file_type

        self.log("Using filter: " + self.file_type)

    def log(self, msg):
        sys.stdout.write(msg + '\n')

    def fail(self, msg):
        """An error was encountered, abort build."""
        sys.stderr.write(msg + '\n')
        sys.exit(1)

    def file_is_excluded(self, filepath):
        """Is the given file path excluded from the rollup process?"""
        if not self.exclusion_regex:
            # Include everything.
            return False
        return re.search(self.exclusion_regex, filepath)

    def ensure_build_directory(self, path):
        """Make sure that the named relative path is a directory."""
        target_dir = os.path.join(self.build_dir, path)
        if os.path.exists(target_dir):
            if not os.path.isdir(target_dir):
                self.fail(
                    "The target path, '%s', is not a directory!" % target_dir)
        else:
            self.log('Creating %s' % target_dir)
            os.makedirs(target_dir)
        return target_dir

    def ensure_link(self, src, dst):
        """Make sure that src is linked to dst."""
        if os.path.lexists(dst):
            if not os.path.islink(dst):
                self.fail(
                    "The target path, '%s', is not a symbolic link! " % dst)
        else:
            self.log('Linking %s -> %s' % (src, dst))
            os.symlink(src, dst)

    def link_and_minify(self, component, js_file):
        """Create raw, debug and min version of js_file."""
        component_dir = os.path.join(self.build_dir, component)
        basename = os.path.splitext(os.path.basename(js_file))[0]

        raw_file = os.path.join(component_dir, basename + '.js')
        rel_js_file = relative_path(raw_file, js_file)
        self.ensure_link(rel_js_file, raw_file)

        debug_file = os.path.join(component_dir, basename + '-debug.js')
        self.ensure_link(rel_js_file, debug_file)

        min_file = os.path.join(component_dir, basename + '-min.js')
        if (not os.path.exists(min_file)
            or os.stat(min_file).st_mtime < os.stat(js_file).st_mtime):
            self.log("Minifying %s into %s." % (js_file, min_file))
            js_in = open(js_file, 'r')
            min_out = open(min_file, 'w')
            minifier = JavascriptMinify()
            minifier.minify(js_in, min_out)
            js_in.close()
            min_out.close()

        self.built_files.append(
            {'raw': raw_file,
             'debug': debug_file,
             'min': min_file})

    def build_assets(self, component_name):
        """Build a component's "assets" directory."""
        join = os.path.join
        isdir = os.path.isdir

        assets_path = join(component_name, 'assets')
        src_assets_dir = join(self.src_dir, assets_path)
        if not isdir(src_assets_dir):
            return

        target_assets_dir = self.ensure_build_directory(assets_path)
        # Symlink everything except the skins subdirectory.
        self.link_directory_content(
            src_assets_dir, target_assets_dir,
            lambda src: not src.endswith('skins'))

        src_skins_dir = join(src_assets_dir, 'skins')
        if not isdir(src_skins_dir):
            return

        # Process sub-skins.
        for skin in os.listdir(src_skins_dir):
            self.build_skin(component_name, skin)

    def link_directory_content(self, src_dir, target_dir, link_filter=None):
        """Link all the files in src_dir into target_dir.

        This doesn't recurse into subdirectories, but will happily link
        subdirectories. It also skips linking backup files.

        :param link_filter: A callable taking the source file as a parameter.
            If the filter returns False, no symlink will be created. By
            default a symlink is created for everything.
        """
        for name in os.listdir(src_dir):
            if name.endswith('~'):
                continue
            src = os.path.join(src_dir, name)
            if link_filter and not link_filter(src):
                continue
            target = os.path.join(target_dir, name)
            self.ensure_link(relative_path(target, src), target)

    def build_skin(self, component_name, skin_name):
        """Build a skin for a particular component."""
        join = os.path.join

        skin_dir = join(component_name, 'assets', 'skins', skin_name)
        src_skin_dir = join(self.src_dir, skin_dir)
        target_skin_dir = self.ensure_build_directory(skin_dir)

        # Link everything in there
        self.link_directory_content(src_skin_dir, target_skin_dir)

        # Holds all the combined files that are part of the skin
        skin_files = self.skins.setdefault(skin_name, [])

        # Create the combined core+skin CSS file.
        for skin_file in glob(join(src_skin_dir, '*-skin.css')):
            module_name = os.path.basename(skin_file)[:-len('-skin.css')]

            target_skin_file = join(target_skin_dir, '%s.css' % module_name)
            skin_files.append(target_skin_file)

            # Combine files from the build directory so that
            # relative paths are sane.
            css_files = [
                os.path.join(target_skin_dir, os.path.basename(skin_file))]
            core_css_file = join(
                self.src_dir, component_name, 'assets',
                '%s-core.css' % module_name)
            if os.path.exists(core_css_file):
                css_files.insert(0, core_css_file)

            combined_css = CSSComboFile(css_files, target_skin_file)
            if combined_css.needs_update():
                self.log('Combining %s into %s...' % (
                    ", ".join(map(os.path.basename, css_files)),
                    target_skin_file))
                combined_css.update()

    def update_combined_js_file(self):
        # Compile all the files in one JS file.  Apply the filter to see
        # which file extensions we should include.
        build_file = os.path.join(self.build_dir, "%s.js" % self.name)

        included_files = []
        extra_files = [f for f in self.extra_files if f.endswith('.js')]
        built_files = [f[self.file_type] for f in self.built_files]

        included_files.extend(extra_files)
        included_files.extend(built_files)
        files_to_combine = [f for f in included_files
                            if not self.file_is_excluded(f)]

        combined_js = JSComboFile(files_to_combine, build_file)
        if combined_js.needs_update():
            self.log('Updating %s...' % build_file)
            combined_js.update()

    def update_combined_css_skins(self):
        """Create one combined CSS file per skin."""
        extra_css_files = [f for f in self.extra_files if f.endswith('.css')]
        for skin_name in self.skins:
            skin_build_file = os.path.join(self.build_dir, "%s-%s.css" %
                (self.name, skin_name))

            css_files = extra_css_files + self.skins[skin_name]
            combined_css = CSSComboFile(css_files, skin_build_file)
            if combined_css.needs_update():
                self.log('Updating %s...' % skin_build_file)
                combined_css.update()

    def find_components(self):
        """Find all of the project sub-component names and directories."""
        for name in os.listdir(self.src_dir):
            path = os.path.join(self.src_dir, name)
            if not os.path.isdir(path):
                continue
            yield name, path

    def do_build(self):
        for name, cpath in self.find_components():
            files_to_link = glob(os.path.join(cpath, '*.js'))
            if len(files_to_link) == 0:
                continue
            self.ensure_build_directory(name)

            for js_file in files_to_link:
                self.link_and_minify(name, js_file)

            self.build_assets(name)

        self.update_combined_js_file()
        self.update_combined_css_skins()


def get_options():
    """Parse the command line options."""
    parser = optparse.OptionParser(
        usage="%prog [options] [extra_files]",
        description=(
            "Create a build directory of CSS/JS files. "
            ))
    parser.add_option(
        '-n', '--name', dest='name', default='lazr',
        help=('The basename of the generated compilation file. Defaults to '
            '"lazr".'))
    parser.add_option(
        '-b', '--builddir', dest='build_dir', default=BUILD_DIR,
        help=('The directory that should contain built files.'))
    parser.add_option(
        '-s', '--srcdir', dest='src_dir', default=PKG_SRC_DIR,
        help=('The directory containing the src files.'))
    parser.add_option(
        '-x', '--exclude', dest='exclude', default='',
        metavar='REGEX',
        help=('Exclude any files that match the given regular expression.'))
    parser.add_option(
        '-f', '--filetype', dest='file_type', default='min',
        help=('Only bundle files in the source directory that match the '
              'specified file-type filter. Possible values are '
              '[min, raw, debug]. [default: %default]'))
    return parser.parse_args()


def main():
    options, extra= get_options()

    Builder(
       name=options.name,
       build_dir=options.build_dir,
       src_dir=options.src_dir,
       extra_files=extra,
       exclude_regex=options.exclude,
       file_type=options.file_type,
       ).do_build()
