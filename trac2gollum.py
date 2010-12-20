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


def format_comment(entry, final):
    """ creates / formats commit comment.
        "final" is true when content is converted from Trac markup to Markdown.
    """
    comment = entry[6] or (u'Page "%s" updated.' % (entry[0]))
    if final:
        return u'%s (automatically converted to Markdown)' % comment
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
    return str(int(timestamp)) + " 0200".decode("UTF-8")


def convert_code(text):
    """ replace code blocks (very primitive)

    >>> convert_code(u"\\nTest\\n\\n{{{\\n#!sh\\nCode paragraph\\n}}}\\n\\nTest\\n")
    u'\\nTest\\n\\n```sh\\nCode paragraph\\n```\\n\\nTest\\n'
    >>> convert_code(u"\\nTest\\n\\n{{{\\nCode paragraph\\n}}}\\n\\nTest\\n")
    u'\\nTest\\n\\n\\n    Code paragraph\\n\\n\\nTest\\n'

    """
    result = u""
    start = False
    running = False
    original = text
    indent = u""
    for line in text.splitlines():
        if line.strip() == u"{{{":
            start = True
            running = True
        elif start:
            start = False
            if line.startswith("#!"):
                result += u"```" + line.replace("#!", "") + os.linesep
            else:
                indent = u"    "
                result += os.linesep + indent + line + os.linesep
        elif line.strip() == u"}}}" and running:
            running = False
            if indent:
                indent = u""
                result += os.linesep
            else:
                result += u"```" + os.linesep
        else:
            result += indent + line + os.linesep
    if running:
        # something went wrong; don't touch the text.
        return original
    return result


re_macro = re.compile(r'\[{2}(\w+)\]{2}')
re_inlinecode = re.compile(r'\{\{\{([^\n]+?)\}\}\}')
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
    u'# One\\n## Two\\n### Three\\n#### Four\\n'
    >>> format_text(u"Paragraph with ''italic'' and '''bold'''.")
    u'Paragraph with *italic* and **bold**.\\n'
    >>> format_text(u"Example with [wiki:a/b one link].")
    u'Example with [[one link|a/b]].\\n'
    >>> format_text(u"Beispiel mit [http://blog.fefe.de Fefes Blog] Link.")
    u'Beispiel mit [[Fefes Blog|http://blog.fefe.de]] Link.\\n'
    >>> format_text(u"Beispiel mit CamelCase Link.")
    u'Beispiel mit [[CamelCase]] Link.\\n'
    >>> format_text(u"Beispiel ohne !CamelCase Link.")
    u'Beispiel ohne CamelCase Link.\\n'
    >>> format_text(u"Test {{{inline code}}}\\n\\nand more {{{inline code}}}.")
    u'Test `inline code`\\n\\nand more `inline code`.\\n'
    >>> format_text(u"\\n * one\\n * two\\n")
    u'\\n* one\\n* two\\n'
    >>> format_text(u"\\n 1. first\\n 2. second\\n")
    u'\\n1. first\\n2. second\\n'
    >>> format_text(u"There is a [[macro]] here.")
    u'There is a (XXX macro: "macro") here.\n'
    """
    # TODO: ticket: and source: links are not yet handled
    text = convert_code(text)
    text = re_macro.sub(r'(XXX macro: "\1")', text)
    text = re_inlinecode.sub(r'`\1`', text)
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
            yield {
                "page": format_page(revision[0]),
                "version": revision[1],
                "time": format_time(revision[2]),
                "user": format_user(revision),
                "ip": revision[4],
                "text": revision[5],
                "comment": format_comment(revision, final=False),
            }
        latest = db.execute('select name, max(version), time, author, ipnr, text, comment from wiki where name is ?',
                            [page]).fetchall()[0]
        yield {
            "page": format_page(latest[0]),
            "version": latest[1],
            "time": format_time(latest[2]),
            "user": format_user(latest),
            "ip": latest[4],
            "text": format_text(latest[5]),
            "comment": format_comment(latest, final=True),
        }


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