# -*- coding: utf-8 -*-
# Copyright (C) 2004-2008 Tristan Seligmann and Jonathan Jacobs
# Copyright (C) 2012-2014 Bastian Kleineidam
# Copyright (C) 2015-2017 Tobias Gruetzmacher

from __future__ import absolute_import, division, print_function

import os
import re
import sys
import time
import json
import codecs

try:
    from os import replace as rename
except ImportError:
    from os import rename

import requests
from lxml import html

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))  # noqa

from dosagelib.util import unescape, get_page
from dosagelib import scraper


def first_lower(x):
    return x[0].lower()


class ComicListUpdater(object):
    dup_templates = ()
    excluded_comics = ()

    START = "# START AUTOUPDATE"
    END = "# END AUTOUPDATE"

    def __init__(self, name):
        self.json = name.replace(".py", ".json")
        self.session = requests.Session()
        self.sleep = 0

    def get_url(self, url, expand=True):
        """Get an HTML page and parse it with LXML."""
        print("Parsing", url, file=sys.stderr)
        try:
            data = html.document_fromstring(get_page(url, self.session).text)
            if expand:
                data.make_links_absolute(url)
            if self.sleep > 0:
                time.sleep(self.sleep)
            return data
        except IOError as msg:
            print("ERROR:", msg, file=sys.stderr)
            raise

    def should_skip(self, name):
        if contains_case_insensitive(self.res, name):
            # we cannot handle two comics that only differ in case
            print("INFO: skipping possible duplicate", repr(name),
                  file=sys.stderr)
            return True
        return False

    def get_results(self):
        """Collect comics and save dictionary in JSON file."""
        self.res = {}
        self.collect_results()

        if not self.res:
            print("ERROR:", "did not match any comics", file=sys.stderr)
            return

        with codecs.open(self.json, 'wb', 'utf-8') as f:
            json.dump(self.res, f, sort_keys=True, indent=2,
                      separators=(',', ': '))

    def add_comic(self, name, data, count=None):
        """Add a collected comic with a specific number of comics."""
        name = format_name(name)
        if not self.should_skip(name):
            self.res[name] = {'count': count, 'data': data}

    def collect_results(self):
        raise NotImplementedError

    def print_results(self, args):
        """Print all comics that have at least the given number of minimum
        comic strips."""
        min_comics, filename = args
        min_comics = int(min_comics)
        oldf = codecs.open(filename, 'r', 'utf-8')
        newf = codecs.open(filename + '.new', 'w', 'utf-8')
        with oldf, newf:
            indent = self.copy_until_start(oldf, newf)
            with codecs.open(self.json, 'rb', 'utf-8') as f:
                data = json.load(f)
            for name, entry in sorted(data.items(), key=first_lower):
                self.write_entry(newf, name, entry, min_comics, indent)
            self.copy_after_end(oldf, newf)
        rename(filename + '.new', filename)

    def copy_until_start(self, src, dest):
        for line in src:
            dest.write(line)
            if line.strip().startswith(self.START):
                return line.find(self.START)
        raise RuntimeError("can't find start marker!")

    def copy_after_end(self, src, dest):
        skip = True
        for line in src:
            if line.strip().startswith(self.END):
                skip = False
            if not skip:
                dest.write(line)
        if skip:
            raise RuntimeError("can't find end marker!")

    def write_entry(self, fp, name, entry, min_comics, indent):
        if name in self.excluded_comics:
            return
        count = entry['count']
        if count and count < min_comics:
            return
        dup = self.find_dups(name)
        fp.write(" " * indent)
        if dup is not None:
            fp.write(u"# %s has a duplicate in %s\n" % (name, dup))
        else:
            fp.write(self.get_entry(
                truncate_name(name),
                entry['data']).replace("\n", "\n" + (" " * indent)) + "\n")

    def find_dups(self, name):
        """Check if comic name already exists."""
        names = [(tmpl % name).lower() for tmpl in self.dup_templates]
        if names:
            for scraperobj in scraper.get_scrapers():
                lname = scraperobj.name.lower()
                if lname in names:
                    return scraperobj.name
        return None

    def get_entry(self, name, data):
        """Return an entry for the module generator."""
        raise NotImplementedError

    def run(self):
        if len(sys.argv) > 1:
            self.print_results(sys.argv[1:])
        else:
            self.get_results()


def contains_case_insensitive(adict, akey):
    """Check if key is in adict. The search is case insensitive."""
    for key in adict:
        if key.lower() == akey.lower():
            return True
    return False


def capfirst(text):
    """Uppercase the first character of text."""
    if not text:
        return text
    return text[0].upper() + text[1:]


def save_result(res, json_file):
    """Save result to file."""
    with codecs.open(json_file, 'wb', 'utf-8') as f:
        json.dump(res, f, sort_keys=True, indent=2, separators=(',', ': '))


def load_result(json_file):
    """Load contents of a json file."""
    with codecs.open(json_file, 'rb', 'utf-8') as f:
        return json.load(f)


def truncate_name(text):
    """Ensure the comic name does not exceed 50 characters."""
    return text[:50]


def asciify(name):
    """Remove non-ascii characters from string."""
    return re.sub("[^0-9a-zA-Z_]", "", name)


def format_name(text):
    """Format a comic name."""
    name = unescape(text)
    name = "".join(capfirst(x) for x in name.split(" "))
    name = asciify(name.replace(u'&', u'And').replace(u'@', u'At').replace('ñ', 'n'))
    return name
