"""Where the optional integration tests find the source knowledge base.

LEGAL_KIT_WIKI is the topic root. LEGAL_KIT_BUILD_REFS is the path to the base's table module
(build_refs.py); without it the module is looked up as output/projects/*/code/build_refs.py under the
topic and used when exactly one is found. Without both, the integration tests are skipped.
"""

import os
from pathlib import Path

WIKI = os.environ.get("LEGAL_KIT_WIKI")


def _find_build_refs():
    explicit = os.environ.get("LEGAL_KIT_BUILD_REFS")
    if explicit:
        return explicit
    if WIKI:
        found = sorted(Path(WIKI).glob("output/projects/*/code/build_refs.py"))
        if len(found) == 1:
            return str(found[0])
    return None


BUILD_REFS = _find_build_refs()
SKIP_REASON = "LEGAL_KIT_WIKI (and LEGAL_KIT_BUILD_REFS, when the table module is not under the topic) is not set"
