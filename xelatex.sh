#!/bin/sh
# Build cv.tex to cv.pdf.
#
# This used to be a macOS BasicTeX setup: `brew install --cask basictex` plus a
# hand-maintained `tlmgr install` list (adjustbox, tcolorbox, collectbox, ucs,
# environ, trimspaces, titling, enumitem, rsfs, sourcesanspro, ...) that had to
# be kept in sync with whatever the templates happened to \usepackage, ending in
# a `docker run csmith/awesome-cv-builder`. Tectonic fetches exactly the packages
# a document asks for and caches them, so neither half is needed any more.
#
#   macOS:  brew install tectonic
#   Linux:  see DEPLOY.md, or https://tectonic-typesetting.github.io/install.html
set -e

tectonic -X compile "${1:-cv.tex}"
