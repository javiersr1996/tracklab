"""The one thing dbt-duckdb cannot do on its own: create the directory it writes into.

Every silver model is materialised `external`, which is a ``COPY ... TO
'<silver_dir>/<model>/data.parquet'``. DuckDB creates missing directories for a
partitioned copy but not for a plain one, and dbt-duckdb does not create them
either, so on a clean clone the first model of the run dies with `Cannot open
file`. Nothing in dbt's Jinja can touch the filesystem, and a DuckDB scalar
function cannot help either: registering one pulls in numpy, which this project
does not depend on and will not start depending on to call mkdir.

So the gap is closed where dbt-duckdb designed it to be closed, in a plugin
registered in profiles.yml:

    plugins:
      - module: tracklab.silver.dbt_plugin
        config:
          silver_dir: data/silver
          models_dir: dbt/models/silver

One directory per silver model, taken from the model files themselves rather
than from a list that would have to be kept in step: the models added by tasks
11 and 12 get their directory from the same rule, and the only thing this plugin
assumes is the layout convention of tasks/todo.md, which is also what
dbt_project.yml writes into each model's `location`. A model that is not
materialised external just gets an empty directory it never uses.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dbt.adapters.duckdb.plugins import BasePlugin

DEFAULT_SILVER_DIR = "data/silver"
DEFAULT_MODELS_DIR = "dbt/models/silver"


def ensure_model_dirs(silver_dir: Path, models_dir: Path) -> list[Path]:
    """Create one directory under `silver_dir` per `.sql` model in `models_dir`.
    Returns them sorted, so a caller (or a test) can see what it made."""
    made = []
    for model in sorted(models_dir.glob("*.sql")):
        path = silver_dir / model.stem
        path.mkdir(parents=True, exist_ok=True)
        made.append(path)
    return made


class Plugin(BasePlugin):
    def initialize(self, plugin_config: dict[str, Any]) -> None:
        silver_dir = Path(str(plugin_config.get("silver_dir", DEFAULT_SILVER_DIR)))
        models_dir = Path(str(plugin_config.get("models_dir", DEFAULT_MODELS_DIR)))
        ensure_model_dirs(silver_dir, models_dir)
