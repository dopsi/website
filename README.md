# dopsi-site

Small static-site generator for RST files. Configuration is in `config.toml` and project metadata + environment management is kept in `pyproject.toml`.

Quick start (using `pixi` as environment manager):

1. Install `pixi` (if you don't have it):

```bash
python -m pip install --user pipx
pipx ensurepath
pipx install pixi
```

2. Create the environment via `pixi` (refer to your `pixi` docs):

```bash
# Example (pixi-specific commands may vary):
pixi install
```

3. Run the generator (after installing dependencies into the environment):

```bash
python -m pip install -e .
generate --config config.toml
```

Dry run to validate git discovery without rendering:

```bash
python scripts/generate.py --config config.toml --skip-render
```

Edit `config.toml` to point `repo_url` at your repository and adjust `branch` if necessary.
