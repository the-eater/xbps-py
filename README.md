# xbps-py

A set of simple tools to help with xbps package maintenance

## `./fix_submodules.py [template]`

Will resolve submodules from github archive do the following
 
- add github archives of submodules to `destfiles`
- add checksums of all `destfiles`
- add a `post_extract` which moves the extracted submodules to the correct folder
- add `_commit_hash_${project}="${commit-hash}"` for non-automated maintenance