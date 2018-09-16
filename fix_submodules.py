#!/usr/bin/env python3
import sys
from xbps import TemplateParser
import configparser
import regex
import requests
import os
from hashlib import sha256

env = configparser.ConfigParser()
env['env'] = {}
for (key, v) in os.environ.items():
    env['env'][key] = v

if os.path.exists('.env'):
    env.read_string('[env]\n' + open('.env').read())

env = env['env']

request_config = {}

if 'GITHUB_TOKEN' in env:
    request_config['auth'] = tuple(env['GITHUB_TOKEN'].split(':'))

REGEX_GITHUB_RELEASE = regex.compile(
    r"^https://github.com/(?P<entity>[^/]+)/(?P<project>[^/]+)/archive/(?P<ref>.+).tar.gz$"
)
REGEX_GITHUB = regex.compile(
    r"https://github.com/(?P<entity>[^/]+)/(?P<project>[^/]+).git"
)
REGEX_GITHUB_TREE = regex.compile(
    r"https://api.github.com/repos/(?P<entity>[^/]+)/(?P<project>[^/]+)/git/trees/[0-9a-f]+"
)

TEMPLATE_GITMODULES = "https://raw.githubusercontent.com/{entity}/{project}/{ref}/.gitmodules"
TEMPLATE_GITHUB_CONTENTS = "https://api.github.com/repos/{entity}/{project}/contents/{path}?ref={ref}"
TEMPLATE_GITHUB_ARCHIVE = "https://github.com/{entity}/{project}/archive/{ref}.tar.gz"

TEMPLATE_POST_EXTRACT = """\trmdir {path};
\tmv -T {sourcedir} {path};
"""

with open(sys.argv[1]) as f:
    template = f.read()

ts = TemplateParser()

ts.consume(template)

distfiles = ts.get_expanded('distfiles')

if distfiles is None:
    print("Can't resolve distfiles")
    exit(1)

distfiles = distfiles.strip().split("\n")

if len(distfiles) == 0:
    print("No distfiles found")
    exit(1)

match = REGEX_GITHUB_RELEASE.match(distfiles[0])

if match is None:
    print("First dist file isn't a github release, no support for that yet")
    exit(1)

details = {
    'entity': match.group('entity'),
    'project': match.group('project'),
    'ref': match.group('ref')
}

gitmodules = requests.get(TEMPLATE_GITMODULES.format(**details), **request_config)

if gitmodules.status_code == 404:
    print("No .gitmodules found, so no submodules exist")
    exit(1)

config = configparser.ConfigParser()
config.read_string(gitmodules.content.decode(), '.ini')

submodules = []

commit_hashes = []
new_distfiles = [ts.get('distfiles').split("\n")[0]]
checksum = [sha256(requests.get(ts.get_expanded('distfiles').split("\n")[0]).content).hexdigest()]

post_extract = 'post_extract() {\n'

for (name, section) in config.items():
    if name.strip()[0:10] != 'submodule ':
        continue

    suburl = TEMPLATE_GITHUB_CONTENTS.format(path=section['path'], **details)

    submodule = requests.get(suburl, **request_config)

    if submodule.status_code != 200:
        print("Submodule '{}' can't be resolved with github [status={}, url={}]".format(section['path'],
                                                                                        submodule.status_code, suburl))
        continue

    subdetails = submodule.json()

    submoduletree = requests.get(subdetails['git_url'], **request_config)

    if submoduletree.status_code != 200:
        print("Submodule tree '{}' can't be resolved with github [status={}, url={}]".format(section['path'],
                                                                                             submoduletree.status_code, subdetails['git_url']))
        continue

    subtreematch = REGEX_GITHUB_TREE.match(submoduletree.json()['url'])

    if subtreematch is None:
        print("Submodule tree '{}' can't be resolved with github [status={}, url={}]".format(section['path'],
                                                                                             submoduletree.status_code,
                                                                                             subdetails['git_url']))
        continue

    url_details = REGEX_GITHUB.match(section['url'])

    sub = {
        'path': section['path'],
        'sha': subdetails['sha'],
        'entity': url_details.group('entity'),
        'project': url_details.group('project'),
        'varname': url_details.group('project').replace('-', '_').lower(),
        'actual_project': subtreematch.group('project'),
    }

    sub['commit_hash_varname'] = '_commit_hash_' + sub['varname']

    submodules.append(sub)

    if ts.get(sub['commit_hash_varname']) is None:
        commit_hashes.append((TemplateParser.TYPE_WS, "\n"))
        commit_hashes.append((TemplateParser.TYPE_KV, sub['commit_hash_varname'], sub['sha'], True))
    else:
        ts.set(sub['commit_hash_varname'], sub['sha'], True)

    new_distfiles.append(TEMPLATE_GITHUB_ARCHIVE.format(ref='${' + sub['commit_hash_varname'] + '}', **sub) + '>' + sub[
        'varname'] + '.tgz')

    url = TEMPLATE_GITHUB_ARCHIVE.format(ref=sub['sha'], **sub)
    tar = requests.get(url)
    checksum.append(sha256(tar.content).hexdigest())

    post_extract += TEMPLATE_POST_EXTRACT.format(path='./' + sub['path'],
                                                 sourcedir='"../{}-${{{}}}"'.format(sub['actual_project'],
                                                                                    sub['commit_hash_varname']))

post_extract += '}'


ts.insert_after(commit_hashes, 'revision')
ts.set('distfiles', "\n".join(new_distfiles), True)
ts.set('checksum', "\n".join(checksum), True)


if ts.get_func('post_extract') is None:
    ts.insert_after([(TemplateParser.TYPE_WS, "\n\n"), (TemplateParser.TYPE_FUNC, post_extract, 'post_extract')],
                    'checksum')
else:
    ts.set_func('post_extract', post_extract)

print(ts.write())
