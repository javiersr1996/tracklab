"""Dagster definitions: the pipeline's four steps as assets (task 15).

Load with ``dagster ... -m tracklab.dagster_defs`` from ``pipeline/``, like every
other command: the manifest, the dbt project and the data root are relative to it.
"""

from tracklab.dagster_defs.definitions import defs

__all__ = ["defs"]
