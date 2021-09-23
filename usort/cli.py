# Copyright (c) Facebook, Inc. and its affiliates.
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import sys
from functools import wraps
from pathlib import Path
from typing import Any, Callable, List, Sequence

import click
from moreorless.click import echo_color_unified_diff

from usort.translate import render_node

from . import __version__
from .api import usort_path, usort_stdin
from .config import Config
from .sorting import sortable_blocks
from .util import get_timings, print_timings, try_parse, Timing

BENCHMARK = False


def print_benchmark(timings: Sequence[Timing]) -> None:
    if BENCHMARK:
        print_timings(click.echo, timings=timings)


def usort_command(fn: Callable[..., int]) -> Callable[..., None]:
    """
    Run wrapped command, print timings if --benchmark, and exit with return code
    """

    @wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> None:
        exit_code = fn(*args, **kwargs) or 0
        if BENCHMARK:
            print_timings(click.echo, timings=get_timings())
        sys.exit(exit_code)

    return wrapper


@click.group()
@click.version_option(__version__, "--version", "-V")
@click.option("--benchmark", is_flag=True, help="Output benchmark timing info")
def main(benchmark: bool) -> None:
    global BENCHMARK
    BENCHMARK = benchmark


@main.command()
@click.option("--multiples", is_flag=True, help="Only show files with multiple blocks")
@click.option("--debug", is_flag=True, help="Show internal information")
@click.argument("filenames", nargs=-1)
@usort_command
def list_imports(multiples: bool, debug: bool, filenames: List[str]) -> int:
    """
    Troubleshoot sorting behavior and show import blocks
    """
    # This is used to debug the sort keys on the various lines, and understand
    # where the barriers are that produce different blocks.

    for f in filenames:
        config = Config.find(Path(f))
        mod = try_parse(Path(f))
        try:
            blocks = sortable_blocks(mod.body, config)
        except Exception as e:
            print("Exception", f, e)
            continue

        if multiples and len(blocks) < 2:
            continue

        click.secho(f"{f} {len(blocks)} blocks:", fg="yellow")
        for b in blocks:
            print(f"  body[{b.start_idx}:{b.end_idx}]")
            sorted_imports = sorted(b.imports)
            if debug:
                for imp in b.imports:
                    print(
                        f"    {sorted_imports.index(imp)} {imp} "
                        f"({imp.config.category(imp.stem or '')})"
                    )
            else:
                print("Formatted:")
                print("[[[")
                for imp in sorted_imports:
                    assert imp.node is not None
                    print(render_node(imp.node), end="")
                print("]]]")

    return 0


@main.command()
@click.argument("filenames", nargs=-1)
@usort_command
def check(filenames: List[str]) -> int:
    """
    Check imports for one or more path
    """
    if not filenames:
        raise click.ClickException("Provide some filenames")

    return_code = 0
    for f in filenames:
        path = Path(f)
        for result in usort_path(path, write=False):
            if result.error:
                click.echo(f"Error sorting {result.path}: {result.error}")
                return_code |= 1

            if result.content != result.output:
                click.echo(f"Would sort {result.path}")
                return_code |= 2

            print_benchmark(result.timings)

    return return_code


@main.command()
@click.argument("filenames", nargs=-1)
@usort_command
def diff(filenames: List[str]) -> int:
    """
    Output diff of changes for one or more path
    """
    if not filenames:
        raise click.ClickException("Provide some filenames")

    return_code = 0
    for f in filenames:
        path = Path(f)
        for result in usort_path(path, write=False):
            if result.error:
                click.echo(f"Error sorting {result.path}: {result.error}")
                return_code |= 1

            if result.content != result.output:
                assert result.encoding is not None
                echo_color_unified_diff(
                    result.content.decode(result.encoding),
                    result.output.decode(result.encoding),
                    result.path.as_posix(),
                )

            print_benchmark(result.timings)

    return return_code


@main.command()
@click.argument("filenames", nargs=-1)
@usort_command
def format(filenames: List[str]) -> int:
    """
    Format one or more paths

    This is intended to sort nodes separated by barriers, and that's it.
    We don't format them (aside from moving comments).  Black does the rest.
    When in doubt leave lines alone.
    """
    if not filenames:
        raise click.ClickException("Provide some filenames")

    if filenames[0].strip() == "-":
        success = usort_stdin()
        return 0 if success else 1

    return_code = 0
    for f in filenames:
        path = Path(f)
        for result in usort_path(path, write=True):
            if result.error:
                click.echo(f"Error sorting {result.path}: {result.error}")
                return_code |= 1
                continue

            if result.content != result.output:
                click.echo(f"Sorted {result.path}")

            print_benchmark(result.timings)

    return return_code


if __name__ == "__main__":
    main()
