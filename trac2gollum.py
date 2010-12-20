#!/usr/bin/env python2.7
import sys
import os
import sqlite3
from datetime import datetime
import subprocess
import re

GIT = "/opt/local/bin/git"

def format_user(entry):
    """ git requires users to conform to "A B <ab@c.de>"

    >>> format_user(['', '', '', u'user', u'127.0.0.1'])
    u'user <127.0.0.1>'
    >>> format_user(['', '', '', u'user@home.local', u'127.0.0.1'])
    u'user <user@home.local>'
    >>> format_user(['', '', '', u'user <user@home.local>', u'127.0.0.1'])
    u'user <user@home.local>'
    """
    user = entry[3]
    if u"<" in user and "@" in user:
        return user
    if u"@" in user:
        u, d = user.split(u"@")
        return u"%s <%s>" % (u, user)
    ip = entry[4]
    return u"%s <%s>" % (user, ip)


def format_comment(entry):
    comment = entry[6]
    if not comment:
        return u'Page "%s" updated.' % (entry[0])
    return comment


#
#   I hope you don't need to change anything below this line
#


def getargs():
    """ get database file to read from and git repository to write to from
        commandline
    """
    try:
        read = sys.argv[1]
        write = sys.argv[2]
        print u'Reading "%s", writing "%s".' % (sys.argv[1], sys.argv[2])
        if os.path.isfile(read) and os.path.isdir(os.path.join(write, ".git")):
            r = sqlite3.connect(read)
            return (r, write)
        else:
            print u'ERROR: Either file "%s" or git repository "%s" does not exist.' % (read, write)
            sys.exit(1)
    except IndexError:
        print u'Try: "%s trac.db git-repo' % (sys.argv[0])
        sys.exit(1)


def format_time(timestamp):
    """ return a git compatible timestamp

    >>> format_time(1229442008.852975)
    u'1229442008 0000'
    """
    return str(int(timestamp)) + " 0000".decode("UTF-8")

re_inlinecode = re.compile(r'\{\{\{([^\n]+?)\}\}\}')
# ^\{{3}(?:\n|\r\n?)        # three opening curly braces and newline
# (?:#\!(.+)(?:\n|\r\n?))   # sharp bang + language identifier
# ((?:.+(?:\n|\r\n?)+))     # the code itself
# \}{3}(?:\n|\r\n?)         # three closing curly braces and newline
re_code_with = re.compile(r"^\{{3}(?:\n|\r\n?)(?:#\!(.+)(?:\n|\r\n?))((?:.+(?:\n|\r\n?)+))\}{3}(?:\n|\r\n?)", re.MULTILINE)
re_code_without = re.compile(r"^\{{3}(?:\n|\r\n?)((?:.+(?:\n|\r\n?)+))\}{3}(?:\n|\r\n?)", re.MULTILINE)
re_h4 = re.compile(r'====\s(.+?)\s====')
re_h3 = re.compile(r'===\s(.+?)\s===')
re_h2 = re.compile(r'==\s(.+?)\s==')
re_h1 = re.compile(r'=\s(.+?)\s=')
re_uri = re.compile(r'\[(?:wiki:)?([^\s]+)\s(.+)\]')
re_CamelCaseUri = re.compile(r'([^"\/\!])(([A-Z][a-z0-9]+){2,})')
re_NoUri = re.compile(r'\!(([A-Z][a-z0-9]+){2,})')
re_strong = re.compile(r"'''(.+)'''")
re_italic = re.compile(r"''(.+)''")
re_ul = re.compile(r'(^\s\*)', re.MULTILINE)
re_ol = re.compile(r'^\s(\d+\.)', re.MULTILINE)


def format_text(text):
    """ converts trac wiki to gollum markdown syntax

    >>> format_text(u"= One =\\n== Two ==\\n=== Three ===\\n==== Four ====")
    u'# One\\n## Two\\n### Three\\n#### Four'
    >>> format_text(u"Paragraph with ''italic'' and '''bold'''.")
    u'Paragraph with *italic* and **bold**.'
    >>> format_text(u"Example with [wiki:a/b one link].")
    u'Example with [[one link|a/b]].'
    >>> format_text(u"Beispiel mit [http://blog.fefe.de Fefes Blog] Link.")
    u'Beispiel mit [[Fefes Blog|http://blog.fefe.de]] Link.'
    >>> format_text(u"Beispiel mit CamelCase Link.")
    u'Beispiel mit [[CamelCase]] Link.'
    >>> format_text(u"Beispiel ohne !CamelCase Link.")
    u'Beispiel ohne CamelCase Link.'
    >>> format_text(u"{{{\\n#!sh\\nCode paragraph\\n}}}\\n")
    u'```sh\\nCode paragraph\\n```'
    >>> format_text(u"{{{\\nCode paragraph\\n}}}\\n")
    u'```\\nCode paragraph\\n```'
    >>> format_text(u"{{{inline code}}}\\n\\nand more {{{inline code}}}.")
    u'`inline code`\\n\\nand more `inline code`.'
    >>> format_text(u"\\n * one\\n * two\\n")
    u'\\n* one\\n* two\\n'
    >>> format_text(u"\\n 1. first\\n 2. second\\n")
    u'\\n1. first\\n2. second\\n'
    """
    # TODO: ticket: and source: links are not yet handled
    text = re_inlinecode.sub(r'`\1`', text)
    text = re_code_with.sub(r'```\1\n\2```', text)
    text = re_code_without.sub(r'```\n\1```', text)
    text = re_h4.sub(r'#### \1', text)
    text = re_h3.sub(r'### \1', text)
    text = re_h2.sub(r'## \1', text)
    text = re_h1.sub(r'# \1', text)
    text = re_uri.sub(r'[[\2|' + r'\1]]', text)
    text = re_CamelCaseUri.sub(r'\1[[\2]]', text)
    text = re_NoUri.sub(r'\1', text)
    text = re_strong.sub(r'**\1**', text)
    text = re_italic.sub(r'*\1*', text)
    text = re_ul.sub(r'*', text)
    text = re_ol.sub(r'\1', text)
    return text


def format_page(page):
    """ rename WikiStart to Home

    >>> format_page(u'test')
    u'test'
    >>> format_page(u'WikiStart')
    u'Home'
    """
    if page == u"WikiStart":
        return u"Home"
    # Gollum wiki replaces slash and space with dash:
    return page.replace(u"/", u"-").replace(u" ", u"-")


def read_database(db):
    # get all pages except those generated by the trac system itself (help etc.)
    pages = [x[0] for x in db.execute('select name from wiki where ipnr != "127.0.0.1" group by name', []).fetchall()]
    for page in pages:
        for revision in db.execute('select * from wiki where name is ? order by version', [page]).fetchall():
            result = {}
            result["page"] = format_page(revision[0])
            result["version"] = revision[1]
            result["time"]  = format_time(revision[2])
            result["user"] = format_user(revision)
            result["ip"] = revision[4]
            result["text"] = format_text(revision[5])
            result["comment"] = format_comment(revision)
            yield result



def main():
    db, target = getargs()
    source = read_database(db)
    for entry in source:
        # make paths conform to local filesystem
        page = os.path.normpath(entry["page"] + u".md")
        if not os.path.supports_unicode_filenames:
            page = page.encode("utf-8")
        try:
            open(os.path.join(target, page), "wb").write(entry["text"].encode("utf-8"))
            subprocess.check_call([GIT, "add", page], cwd=target)
            try:
                subprocess.check_call([GIT, "commit", "--author", entry["user"],
                                       "--date", entry["time"], "-m", entry["comment"]], cwd=target)
            # trying to circumvent strange unicode-encoded file name problems:
            except subprocess.CalledProcessError:
                [subprocess.check_call([GIT, "add", x], cwd=target) for x in os.listdir(target)]
                subprocess.check_call([GIT, "commit", "--author", entry["user"],
                                       "--date", entry["time"], "-m", entry["comment"]], cwd=target)

        except Exception, e:
            print "\n\n\nXXX Problem: ", e
            sys.exit(23)
    # finally garbage collect git repository
    subprocess.check_call([GIT, "gc"], cwd=target)


if __name__ == "__main__":
    main()